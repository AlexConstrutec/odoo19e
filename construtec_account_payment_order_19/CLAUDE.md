

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

## F3: costo del empleado por mes, día y hora; grupo "Costos de personal" (2026-11-17)
- **Grupo** `group_costos_personal` ("Costos de personal"): el único que lee `costo_mensual`, `costo_dia` y `costo_hora` del empleado y los parámetros de la compañía. Ni un Jefe de equipo los lee. El módulo solo crea el grupo (con admin/root); **los usuarios se asignan a mano en cada base**.
- **Cálculo (solo en Enterprise)**: mensual = sueldo base (`wage`) + bonificación incentivo + `wage` x cargas patronales (12.67 %: IGSS 10.67 + IRTRA 1 + INTECAP 1) + `wage` x provisiones (29.16 %: aguinaldo 8.33 + bono 14 8.33 + indemnización 8.33 + vacaciones 4.17); día = mensual / 22; hora = día / 8. Porcentajes y divisores editables en la compañía (pestaña "Costo de personal", solo el grupo). La bonificación la suma `construtec_hr_employee_19` (gancho `_costo_bonificacion()`).
- **Community nunca calcula**: el pull de empleados trae los tres montos. Solo se piden si Enterprise los tiene **y** el usuario de integración pertenece al grupo (`fields_get` no lista campos de un grupo ajeno): si no, no rompe, simplemente no llegan. **El usuario de integración de la sincronización debe estar en el grupo "Costos de personal" de Enterprise.**
- **Corrección de F2:** la distribución analítica del departamento ya no es un compute (cada sincronización reescribía el mismo departamento y pisaba la distribución propia del empleado). Ahora la toma en `create()` y solo cuando el departamento **realmente cambia** en `write()`.
- Versiones: shared Community 19.0.1.32.0 / Enterprise 19.0.1.33.0; `construtec_hr_employee_19` 19.0.1.1.0 (ahora depende del módulo compartido).
- **Pendiente (decisión del usuario):** costos directos del ticket con días/horas x tarifa. El portal muestra al cliente el `monto` de las líneas comunicadas y el flujo "comunicar" lo lee con el usuario que lo ejecuta: ocultarlo a los Jefes y calcularlo desde el costo salarial lo rompería y expondría el costo interno al cliente.

## El bloqueo de planes analíticos no debe frenar la creación de cuentas (2026-11-17)
`construtec_analytic_plan_lock_19` bloquea que **una persona** cree planes. Pero la alta rápida de "Ubicación" desde un ticket intentaba crear sola el plan genérico "Proyectos (sin plan de origen)" (que no existía en producción) y el bloqueo hacía fallar la creación de la **cuenta**.
- **Ticket (`construtec_helpdesk_field_service`)**: la cuenta nueva usa el plan **existente** "UBICACION CLIENTE" (comparación `=ilike`); si no existe, el genérico si ya existe; solo como último recurso se crea el genérico levantando el bloqueo (`construtec_allow_plan_create`).
- **Sincronización (módulo compartido)**: crear un plan para replicar el que ya existe del otro lado (`_sync_analytic_accounts_from_enterprise`, `create_analytic_account_from_community`) es una creación automática del sistema y también levanta el bloqueo. Un usuario creando un plan a mano sigue bloqueado.

## Relleno de la distribución analítica de empleados sin ella (2026-11-17)
En producción de Enterprise 73 de 74 empleados activos estaban sin distribución, aunque 8 departamentos ya la tenían: la herencia solo ocurre al elegir/cambiar el departamento, no a quien ya estaba en él cuando se capturó la distribución.
- **Migración** (`19.0.1.34.0` Enterprise / `19.0.1.33.0` Community): rellena a toda versión de empleado SIN distribución propia con la de su departamento. Idempotente; **nunca pisa una existente**.
- **`hr.department.write()`**: al capturar o cambiar la distribución de un departamento se rellena a sus empleados que no tienen (los que ya tienen no se tocan).
- **Acción de la lista de empleados** "Heredar distribución analítica del departamento" (`action_heredar_distribucion_departamento`, grupo RR.HH.): lo mismo para los seleccionados; avisa cuántos no tienen departamento.
- Un empleado **sin departamento** no puede heredar nada: hay que asignarle departamento primero.
