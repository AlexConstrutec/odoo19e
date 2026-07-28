"""Clasificación de reportes financieros basada en el campo nativo `account_type` de
`account.account`, en vez de códigos de cuenta o prefijos de `account.group` hardcodeados.

(nivel1, etiqueta_nivel1, etiqueta_nivel2, signo) por cada account_type. `signo` invierte el
saldo contable (naturalmente negativo para cuentas de pasivo/patrimonio/ingreso) para mostrarlo
como positivo en los reportes, igual que hacía el módulo original.
"""
from collections import OrderedDict

ACCOUNT_TYPE_INFO = {
    'asset_cash': ('activo', 'ACTIVO CORRIENTE', 'Caja y Bancos', 1),
    'asset_receivable': ('activo', 'ACTIVO CORRIENTE', 'Cuentas por Cobrar', 1),
    'asset_current': ('activo', 'ACTIVO CORRIENTE', 'Otros Activos Corrientes', 1),
    'asset_prepayments': ('activo', 'ACTIVO CORRIENTE', 'Gastos Pagados por Anticipado', 1),
    'asset_non_current': ('activo', 'ACTIVO NO CORRIENTE', 'Otros Activos No Corrientes', 1),
    'asset_fixed': ('activo', 'ACTIVO NO CORRIENTE', 'Propiedad, Planta y Equipo', 1),
    'liability_payable': ('pasivo', 'PASIVO CORRIENTE', 'Cuentas por Pagar', -1),
    'liability_credit_card': ('pasivo', 'PASIVO CORRIENTE', 'Tarjetas de Crédito', -1),
    'liability_current': ('pasivo', 'PASIVO CORRIENTE', 'Otros Pasivos Corrientes', -1),
    'liability_non_current': ('pasivo', 'PASIVO NO CORRIENTE', 'Pasivo No Corriente', -1),
    'equity': ('patrimonio', 'PATRIMONIO', 'Capital y Reservas', -1),
    'equity_unaffected': ('patrimonio', 'PATRIMONIO', 'Resultados de Ejercicios Anteriores', -1),
    'income': ('ingreso', 'INGRESOS', 'Ingresos Ordinarios', -1),
    'income_other': ('ingreso', 'INGRESOS', 'Otros Ingresos', -1),
    'expense_direct_cost': ('costo', 'COSTOS', 'Costo de Ventas', 1),
    'expense': ('gasto', 'GASTOS', 'Gastos de Operación', 1),
    'expense_other': ('gasto', 'GASTOS', 'Otros Gastos', 1),
    'expense_depreciation': ('gasto', 'GASTOS', 'Depreciaciones y Amortizaciones', 1),
    'off_balance': (None, None, None, 1),
}

BALANCE_SHEET_TYPES = [t for t, info in ACCOUNT_TYPE_INFO.items() if info[0] in ('activo', 'pasivo', 'patrimonio')]
INCOME_STATEMENT_TYPES = [t for t, info in ACCOUNT_TYPE_INFO.items() if info[0] in ('ingreso', 'costo', 'gasto')]
NIVEL1_ORDER = ['ACTIVO CORRIENTE', 'ACTIVO NO CORRIENTE', 'PASIVO CORRIENTE', 'PASIVO NO CORRIENTE',
                'PATRIMONIO', 'INGRESOS', 'COSTOS', 'GASTOS']


def account_type_info(account_type):
    return ACCOUNT_TYPE_INFO.get(account_type, (None, None, None, 1))


def get_balances_by_account(env, company_id, date_to, date_from=None, account_types=None, extra_domain=None):
    """{account.account: saldo} agregado desde el inicio de los tiempos (si date_from es None,
    típico de un Balance General) o en un rango de fechas (típico de un Estado de Resultados)."""
    domain = [('company_id', '=', company_id), ('date', '<=', date_to), ('parent_state', '=', 'posted')]
    if date_from:
        domain.append(('date', '>=', date_from))
    if account_types:
        domain.append(('account_id.account_type', 'in', account_types))
    if extra_domain:
        domain += extra_domain
    grouped = env['account.move.line']._read_group(domain, ['account_id'], ['balance:sum'])
    return {account: balance for account, balance in grouped if account}


def build_report_tree(env, company_id, date_to, date_from=None, account_types=None, extra_domain=None):
    """{etiqueta_nivel1: {etiqueta_nivel2: [(account, saldo_con_signo), ...]}}, en el orden de NIVEL1_ORDER."""
    balances = get_balances_by_account(env, company_id, date_to, date_from, account_types, extra_domain)
    tree = OrderedDict((label, OrderedDict()) for label in NIVEL1_ORDER)
    for account, balance in balances.items():
        if not balance:
            continue
        _, nivel1, nivel2, sign = account_type_info(account.account_type)
        if not nivel1:
            continue
        tree[nivel1].setdefault(nivel2, []).append((account, balance * sign))
    return OrderedDict((label, groups) for label, groups in tree.items() if groups)


def compute_resultado_ejercicio(env, company_id, date_from, date_to):
    """Utilidad/pérdida del ejercicio: ingresos menos costos y gastos del período, calculado en
    vivo a partir de account_type (no depende de que exista una cuenta contable fija de
    'resultado del ejercicio' como en el módulo original)."""
    lines = env['account.move.line'].search([
        ('company_id', '=', company_id), ('date', '>=', date_from), ('date', '<=', date_to),
        ('parent_state', '=', 'posted'), ('account_id.account_type', 'in', INCOME_STATEMENT_TYPES),
    ])
    return -sum(lines.mapped('balance'))
