# construtec_bank_reconciliation_19

Conciliación bancaria mensual por diario de banco, en el formato que usaba Diamante Gerencial
(pedido de Sheny de Arreola, Gerente Financiera, 2026-10; propuesta en el doc "Propuesta:
Conciliación bancaria en Odoo"). Enterprise-only. `depends: account, account_check_printing, mail`.

## Por qué no usa el conciliador nativo de Odoo

Decisión explícita del usuario (2026-10-22). En Odoo 19 cada `account.bank.statement.line`
**crea su propio asiento** (banco contra cuenta de suspenso) y el widget ofrece casar contra
facturas, con lo que el pago ya registrado queda duplicado o sin uso. Aquí el objetivo es otro:
controlar si cada cheque/transferencia/depósito ya registrado **ya lo aplicó el banco**.

Por eso el estado de cuenta vive en un modelo propio sin asientos
(`construtec.bank.statement.line`) y el empate es solo una fila en la tabla de relación
`construtec_bank_line_aml_rel` (línea del banco <-> `account.move.line` de la cuenta de banco del
diario). Nunca se escribe sobre apuntes publicados. Lo único que genera contabilidad son los
ajustes (comisión / interés ganado / interés debitado / otra nota) del asistente de ajuste.

## Modelos

- `construtec.bank.reconciliation`: una por diario y mes (`unique(journal_id, date_from)`).
  Estados Borrador -> Hecho -> Revisado -> Autorizado (Revisado/Autorizado/Reabrir: solo
  `account.group_account_manager`). Los totales y las partidas pendientes
  (`construtec.bank.reconciliation.item`) se recalculan con `action_refresh()` solo en Borrador y
  quedan **congelados** al cerrar: cambios posteriores no alteran un mes cerrado (fue la queja con el
  reporte de Odoo 16, que recalculaba y usaba listas a nivel de clase).
- Fórmula (a la fecha de corte `date_to`):
  `saldo conciliado = saldo banco - pagos en circulación + depósitos en tránsito + débitos del banco no registrados - créditos del banco no registrados`;
  `diferencia = saldo según libros (mayor de la cuenta de banco) - saldo conciliado`.
  Un apunte está en circulación a una fecha si no tiene línea del banco con fecha <= corte; una
  línea del banco está "no registrada" si no tiene apunte con fecha <= corte.
- `action_done` exige: estado de cuenta importado, saldo final = saldo inicial + movimientos (o
  justificación), cero notas del banco del mes sin registrar, y diferencia cero.
- `account.journal.bank_rec_start_date` + `bank_rec_opening_line_ids`: los apuntes anteriores al
  inicio se consideran conciliados salvo los marcados como en circulación al arranque. Sin fecha de
  inicio el diario no se controla (`construtec_bank_state = 'na'`).
- `account.payment.construtec_bank_state` (stored): En circulación / Pagado en banco / No aplica, con
  `construtec_bank_date`. Solo mira el apunte en la cuenta de banco del diario: **pagos en cuenta
  puente (outstanding account distinta del banco) quedan como No aplica** - pendiente si algún día se
  configura cuenta puente (hoy no se usa en producción; se revisó 2026-10-22).
- Cuentas de ajuste por empresa en Ajustes > Contabilidad (`res.company.bank_rec_*`). Odoo no trae
  cuentas nativas de intereses. En producción Construtec: 630103 / 460101 / 630101; MYR: 630103
  (creada 2026-10-22).

## Empate automático (`_auto_match`)

En orden, y solo si la regla deja exactamente un candidato con el mismo monto:
1. No. de cheque del pago (`check_number`, sin ceros a la izquierda) = documento del banco.
2. La referencia del banco aparece en nombre/ref del apunte o asiento, `memo` o `payment_reference`.
3. Monto único dentro de +/- `bank_rec_match_days` (default 15).
El empate manual (asistente) permite N líneas contra M apuntes si los totales cuadran (p. ej. un
débito de planilla que paga varias transferencias).

## Importación

`.xlsx` (openpyxl), `.xls` (xlrd) y `.csv` (prueba `;`, tab, `|`, `,` hasta encontrar encabezado -
el sniffer de csv falla con montos "1,000.00"). Detecta el encabezado por palabras (Fecha, Documento,
Descripción, Débito/Crédito o Monto, Saldo). Punto de vista del banco (Débito = retiro); opción
"Invertir" para archivos con punto de vista contable. **PDF todavía no**: falta un lector por banco
(se necesitan PDFs de ejemplo de cada banco); mientras, las líneas se pueden capturar a mano en la
pestaña Estado de cuenta.

## Reportes

QWeb PDF: "Conciliación Bancaria" (bloques Operaciones del banco / Operaciones internas, detalle de
cheques en circulación, depósitos en tránsito y notas no registradas, firmas Hecho/Revisado/Autorizado)
y "Movimiento de Cuenta" (saldo anterior, cargos, abonos, saldo), imitando los tres reportes de
Diamante que mandó Finanzas (BI 0920099215, agosto 2026).

## Bugs reales encontrados al grabar los videos instructivos (2026-10-23)

Los scripts por `odoo-bin shell` del Pass 1 nunca pasaron por la interfaz, y escondieron 2 bugs que
la grabación (Chrome headless contra un servidor local, clics reales) sacó a la luz:
- **`_default_date_from()` / `_default_date_to()` sin argumento**: Odoo llama `field.default(records)`,
  así que el botón "Nuevo" tronaba con `TypeError` (en shell siempre se pasaban las fechas). Ahora
  aceptan `records=None`.
- **`default_statement_line_id` del contexto se colaba al asiento de ajuste**: el botón "Ajuste" abre
  el asistente con ese default, y `account.move` tiene un campo nativo con el MISMO nombre
  (`statement_line_id` -> `account.bank.statement.line`), así que el asiento quedaba apuntando a una
  línea de extracto inexistente ("Registro faltante"). El asiento se crea ahora con
  `clean_context()`. Ojo con cualquier `default_*` nuevo cuyo nombre coincida con un campo de
  `account.move`/`account.move.line`.
- Menores: etiquetas en inglés derivadas del nombre técnico ("Reconciliation", "Statement Line"), el
  resumen quedaba en 0.00 hasta "Recalcular" (ahora `create()` y los cambios de saldos/fechas/líneas
  recalculan), y el reporte decía "Expresado en Quetzal".

## Verificación

Probado 2026-10-22 en `construtec_bankrec_test` (clon de `construtec_enterprise_0509`) con scripts por
`odoo-bin shell` (rollback al final): empate por las 3 reglas, ajustes, cierre con diferencia 0,
bloqueo de mes cerrado, arrastre al mes siguiente, xlsx, empate manual 1 contra 2, deshacer ajuste.
Notas del entorno local: la base vieja necesitó agregar columnas faltantes y `-u` de los construtec_*;
el `unaccent.dll` de Postgres 18 local está bloqueado por la política de Windows, así que hubo que
borrar los índices `*_name_index` con unaccent en la base de prueba para poder crear asientos.
