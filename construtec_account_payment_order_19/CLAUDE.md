

## Prioridad de la requisición (estrellas) y etiqueta al Gerente Financiero (2026-10-29)

Pedido del usuario: un campo de prioridad con el widget de estrellas de los tickets, y que una requisición de prioridad más alta
etiquete al puesto de Gerente Financiero en el grupo de notificación.

- `prioridad` (Selection `0` Baja / `1` Media / `2` Alta / `3` Muy Alta, default `1`, widget `priority`): en el formulario junto a la
  fecha, columna de la lista, filtro "Prioridad Muy Alta" y agrupar por Prioridad. Se edita libremente en Borrador; después de enviar,
  solo en Enterprise (`es_procesador`).
- Viaja a Enterprise al enviar (`_prepare_sync_vals()`), y un cambio hecho allá regresa a Community con el pull de estado
  (`_pull_payment_order_status()` la pide y compara). Un cambio hecho en Community después de enviar no viaja (por eso es de solo lectura).
- La etiqueta en WhatsApp vive en `construtec_whatsapp_alterno_notify_19` (ver su CLAUDE.md). Versión 19.0.1.27.0.
- Verificado en `construtec_test` (Community 12 comprobaciones). **No verificado en el navegador.**

## Diario con tarjeta de crédito y pregunta al Aplicar (2026-11-05)

Pedido del usuario (Enterprise): el diario de la requisición debe aceptar diarios de tipo **Tarjeta de crédito** además de Banco, y
mostrar solo los diarios de la compañía de la requisición; y al presionar **Aplicar**, preguntar si Odoo debe generar el pago.

- `journal_id` (vista): en Anticipo Viáticos / Materiales el dominio pasó de `type = bank` a `type in (bank, credit)`; para los demás
  tipos sigue sin restricción de tipo. En todos los casos se filtra por `company_id` de la requisición (la compañía actual del usuario
  al crearla) y se quitó "Crear" del desplegable.
- `action_aplicar()` ahora valida lo básico y abre el asistente `account.payment.order.aplicar.wizard` (Sí / No / Cancelar). La lógica
  de siempre vive en `_aplicar(crear_pago)`: **Sí** = igual que antes (valida diario, beneficiario, cuenta de anticipos; crea el pago,
  en borrador para Materiales y confirmado para los demás); **No** = solo pasa a Aplicado, deja nota en el chatter y no pide
  diario/beneficiario/cuenta. El pago se registra después con "Crear Pago" o agregándolo en Pagos.
- Versión 19.0.1.28.0. Verificado en `construtec_bankrec_test` (clon de Enterprise, shell + rollback): tarjeta de crédito + Sí crea 1
  pago (en proceso) con el diario de tarjeta; banco + No aplica sin pagos. **No verificado en el navegador.**

## Materiales bloqueado después del Fin de intervención de Compras (2026-11-05)

Pedido del usuario (caso RP/0521): las líneas de la pestaña Materiales (`material_line_ids`) se editan en Borrador y en Gestión de
Compras, y quedan **bloqueadas desde que Compras presiona "Fin de intervención de Compras"**. Antes seguían editables en estado
Aplicado; ahora el One2many es de solo lectura en cualquier estado distinto de `borrador`/`en_compras` (vista, `readonly=` del campo).
Para volver a editar hay que usar "Pasar a Gestión de Compras" (desde Aprobado). Solo bloquea la interfaz: el código (importar
cotización, Orden de Compra, sincronización) sigue escribiendo las líneas como antes. Versión 19.0.1.29.0.

## Costeo F1: costo real en cascada, sin IVA (2026-11-17)
- `costo_facturas` ahora es la **base sin IVA** (`amount_untaxed_signed`) de las facturas publicadas. `facturas_con_iva` guarda el total con IVA solo para comparar contra los pagos.
- `costo_pagos` (nuevo): pagos de la requisición en proceso o pagados, en moneda de la compañía. Un anticipo aplicado cuenta aquí como **costo provisional**.
- `costo_real` = **facturas (sin IVA) si las hay; si no, pagos**; más traslados. Nunca suma pagos y facturas (son el mismo dinero).
- `costo_por_justificar` = pagado - facturado (con IVA), solo si ya hay facturas. Positivo: anticipo sin justificar; negativo: falta pagar.
- Community no calcula nada de esto: el pull trae `costo_pagos` y `facturas_con_iva` (solo si Enterprise ya los tiene: `fields_get`, así el orden de despliegue no importa). Después de desplegar, correr **Ajustes > Sincronizar ahora** para que Community vea los montos.
- Versiones: Community 19.0.1.30.0, Enterprise 19.0.1.31.0 (cada lado lleva su propia numeración). La migración recalcula todas las requisiciones.

## Envíos duplicados Community -> Enterprise: idempotencia y aviso único (2026-11-17)
- **Qué pasó (RP/0585, RP/0565, RP/0569):** Enterprise creaba una requisición nueva en cada envío del mismo `external_ref` (doble clic en Enviar, o reenvío tras "Volver a borrador"). Community consulta por número, recibía varias filas y su estado saltaba de una a otra (en compras <-> enviado), y cada salto a "Enviado" repetía el aviso de WhatsApp.
- **Enterprise (`create()` -> `_filtrar_envios_duplicados()`):** lock por número (`pg_advisory_xact_lock`) para serializar envíos simultáneos; si ya hay una copia viva ya atendida (En compras, Aprobada, Aplicada, Liquidada) no se crea otra y se devuelve esa; si la copia viva sigue en Enviado se cancela (con nota) y la nueva ocupa su lugar. Solo aplica con rol Procesador y `origin='synced'`.
- **Community (`_pull_payment_order_status()`):** con varias copias del mismo número se queda con la de estado más avanzado (`_elegir_copia_remota()`), a igualdad la que ya conoce (`enterprise_record_id`). Así los duplicados ya existentes dejan de provocar saltos.
- **Aviso:** `construtec_whatsapp_19._notify_estado_pull()` nunca avisa "Enviado" (solo sale desde `action_submit()`).
- Las copias duplicadas que ya existen en Enterprise (RP/1448; RP/1346; RP/1354 a RP/1357) no se limpian solas: rechazarlas o cancelarlas a mano.

## Distribución analítica del departamento, heredada por el empleado (2026-11-17, F2)
- `hr.department` hereda `analytic.mixin` (campo `analytic_distribution`, widget analítico en su formulario). En el módulo compartido para que exista **igual en Enterprise y Community** (`construtec_hr_employee_19` es solo de Enterprise).
- `hr.version` (donde vive el departamento del empleado en Odoo 19) hereda el mismo mixin. En Enterprise `hr_payroll_account` ya lo declaraba; en Community no hay nómina, así que se declara aquí con el mismo grupo (`hr.group_hr_user`).
- **Herencia:** al elegir o cambiar el departamento, la versión toma la distribución del departamento (`_compute_analytic_distribution`, depende solo de `department_id`). Es editable. Si el departamento no tiene distribución, se conserva la que el empleado ya tenía. Si luego cambia la distribución del departamento, **no** se pisan las de los empleados.
- **Ficha del empleado:** en Enterprise la muestra la pestaña de nómina; en Community, la pestaña Trabajo (`muestra_distribucion_analitica`, falso si hay nómina, evita duplicarla). Ambas piden el grupo "Contabilidad analítica".
- **Community:** `_sync_department_distributions()` (al final de "Sincronizar empleados") trae la distribución de cada departamento de Enterprise. Las claves son ids de cuentas de Enterprise y se traducen con `enterprise_analytic_ref`; si falta alguna cuenta, ese departamento se omite. Rellena solo a los empleados **sin** distribución propia.
- Versiones: Community 19.0.1.31.0, Enterprise 19.0.1.32.0.
