# CLAUDE.md

`construtec_portal_ledger_request_19`: **solo Enterprise** (2026-10-15). El contador externo, que no tiene usuario
interno, entra al portal (`/my/libro-mayor`), elige **empresa, fecha inicio y fecha fin**, y le llega por correo el
**Libro Mayor de Enterprise en Excel** (el mismo XLSX que da el botón de exportar del reporte).

`depends`: `portal`, `mail`, `account_reports` (por `account_reports.general_ledger_report`).

## Por qué así y no darle acceso al reporte

Un usuario portal no puede abrir reportes del backend, y si se le asigna un grupo de contabilidad Odoo lo convierte
en usuario interno, que se cobra. Mostrar el reporte en el portal con `sudo()` se parecería a esquivar la licencia.
Enviar un archivo generado equivale a que alguien de contabilidad lo exporte y lo mande, así que **el portal nunca
muestra datos contables**: solo el formulario y el estado de las solicitudes.

## Qué hace

- **`res.users.ledger_portal_company_ids`** (pestaña "Portal: Libro Mayor" en el formulario del usuario, solo
  `base.group_erp_manager`): empresas que ese usuario puede pedir. Vacío = no ve la tarjeta y `/my/libro-mayor` da
  404. Es independiente de `company_ids`.
- **`construtec.ledger.request`**: una fila por solicitud. Guarda usuario, `email_to` congelado (el correo del
  contacto al momento de pedirlo; nunca uno escrito en el portal), empresa, fechas, estado
  (`pendiente`/`enviado`/`error`), error y adjunto. Menú *Contabilidad → Informes → Solicitudes de Libro Mayor
  (portal)* (`account.group_account_manager`), con botón **Reintentar** para las que tienen error. El portal no tiene
  ACL sobre el modelo: todo pasa por el controlador con `sudo()`.
- **Validaciones (servidor, `_portal_create_request`)**: la empresa debe estar en `ledger_portal_company_ids`, inicio ≤
  fin, rango < 366 días, fin no futura, el contacto debe tener correo y hay un máximo de 10 solicitudes en 24 h.
- **Cron** (`cron_process_ledger_requests`, cada 10 min, más un `_trigger()` al crear la solicitud): genera el XLSX con
  `with_company(company).with_context(allowed_company_ids=[company])` y comprueba que `get_report_company_ids()` sea
  exactamente esa empresa. Solo incluye asientos publicados (`all_entries: False`). Adjunta el archivo a la solicitud
  y manda un `mail.mail` con `send()` inmediato. Si el SMTP falla, la solicitud queda en `error` con el motivo.
  Cada solicitud corre en su propio savepoint, así que una mala no traba la cola.
- `email_from` = parámetro del sistema `construtec_portal_ledger_request_19.email_from` (por defecto
  `alex.martinez@construtecasesores.com`, `noupdate`), con el nombre de la empresa solicitada como nombre visible. Si
  el parámetro está vacío, se usa el correo de la empresa o, si no hay, el del usuario del cron.
  **Por qué:** en producción (`construtecasesores.odoo.com`) el único servidor de salida es Outlook ("Outlook Sal"),
  que inicia sesión con esa cuenta y rechaza cualquier otro From con `554 5.2.252 SendAsDenied`. La primera
  solicitud real (2026-10-15, MYR) falló así: MYR no tenía correo y el remitente cayó en
  `notifications@construtecasesores.odoo.com`. Si se cambia el servidor de salida, hay que cambiar el parámetro.

## Configurar al contador

1. Crear el usuario como **Portal** (o invitar el contacto al portal), con correo en su contacto.
2. En su ficha de usuario → pestaña **Portal: Libro Mayor**, agregar las empresas.

## Verificado (2026-10-15, clon de `construtec_test`, con rollback, base borrada después)

- La instalación por `button_immediate_install()` en `odoo-bin shell` queda limpia.
- Se crearon dos empresas con plan contable y un asiento publicado en cada una. El XLSX de A trae solo el asiento de A
  y el de B solo el de B. Un rango que no incluye la fecha del asiento no lo trae.
- Se rechazan: empresa no autorizada, fechas invertidas, rango > 366 días, fecha futura, valores basura, contacto sin
  correo y la 11.ª solicitud en 24 h.
- Sin SMTP local la solicitud queda en `error` con el motivo. Con `send` simulado queda en `enviado`, con adjunto,
  asunto y cuerpo correctos, y el nombre del contacto se escapa en el HTML. **Reintentar** vuelve a `pendiente`.
- El usuario portal recibe `AccessError` si intenta leer el modelo directo.
- **No verificado**: el render real de `/my/libro-mayor` en el navegador, porque el modo servidor de `odoo-bin` no
  arranca en esta máquina. Las plantillas sí pasaron la validación al instalar.
