"""Lector local de estados de cuenta en PDF (sin servicios externos - decisión del usuario 2026-10-23).

Los PDF de banco son tablas visuales: el texto plano sale con las columnas revueltas. Aquí se usa
la POSICIÓN de cada renglón de texto (pdfminer): se ubica el encabezado de la tabla en cada página,
cada fila se ancla en el renglón que trae la fecha, y cada texto se asigna a la columna cuyo
encabezado está más cerca horizontalmente. Las descripciones de dos renglones (p. ej. Banrural:
"N/CREDITO TRANSFERENCIA" arriba y "ACH" abajo de la fila) se pegan a la fila más cercana.

Devuelve filas en el mismo formato que una hoja de Excel (primera fila = encabezado), para que el
asistente de importación use exactamente la misma detección de columnas que para .xlsx/.csv.

Plantillas por banco (`BANK_TEMPLATES`): solo agregan palabras de encabezado propias de cada banco y
la tolerancia vertical. Verificado contra un estado de cuenta real de Banrural (Movimientos de la
Cuenta, 2025). BI y G&T usan la detección genérica hasta tener un PDF de ejemplo.
"""
import io
import re
import unicodedata

DATE_RE = re.compile(r'^\d{1,2}[/-]\d{1,2}[/-]\d{2,4}$')

BANK_TEMPLATES = {
    'banrural': {
        'detect': ['movimientos de la cuenta', 'saldo disponible'],
        'row_tolerance': 9.0,
    },
    'generic': {
        'detect': [],
        'row_tolerance': 9.0,
    },
}


class BankPdfError(Exception):
    pass


def _norm(text):
    text = unicodedata.normalize('NFKD', str(text or '')).encode('ascii', 'ignore').decode()
    return re.sub(r'\s+', ' ', text).strip().lower()


def _text_lines(content):
    try:
        from pdfminer.high_level import extract_pages
        from pdfminer.layout import LAParams, LTTextLine
    except ImportError as exc:
        raise BankPdfError('El servidor no tiene la librería pdfminer para leer PDF.') from exc
    pages = []
    params = LAParams(char_margin=1.0, word_margin=0.1, line_margin=0.2)
    for page in extract_pages(io.BytesIO(content), laparams=params):
        items = []

        def walk(obj):
            if isinstance(obj, LTTextLine):
                text = obj.get_text().strip()
                if text:
                    items.append({'y': page.height - (obj.y0 + obj.y1) / 2, 'x0': obj.x0, 'x1': obj.x1,
                                  'xc': (obj.x0 + obj.x1) / 2, 'text': text})
            elif hasattr(obj, '__iter__'):
                for child in obj:
                    walk(child)
        walk(page)
        pages.append(items)
    return pages


def detect_bank(pages):
    head = _norm(' '.join(i['text'] for i in (pages[0] if pages else [])[:40]))
    for code, tpl in BANK_TEMPLATES.items():
        if tpl['detect'] and all(word in head for word in tpl['detect']):
            return code
    return 'generic'


def _find_header(items, keywords):
    """Encabezado = grupo de renglones casi a la misma altura con Fecha y Débito/Crédito o Monto."""
    by_y = sorted(items, key=lambda i: i['y'])
    for anchor in by_y:
        group = [i for i in by_y if abs(i['y'] - anchor['y']) <= 6]
        group.sort(key=lambda i: i['x0'])
        mapping = {}
        for key, words in keywords.items():
            for idx, item in enumerate(group):
                if idx in mapping.values():
                    continue
                if any(w in _norm(item['text']) for w in words):
                    mapping[key] = idx
                    break
        has_amounts = ('debit' in mapping and 'credit' in mapping) or 'amount' in mapping
        if 'date' in mapping and has_amounts:
            return group, mapping, max(i['y'] for i in group)
    return None


def parse_pdf(content, keywords):
    """Devuelve (codigo_banco, filas) con filas = [encabezado, fila1, ...] como en un Excel."""
    pages = _text_lines(content)
    bank = detect_bank(pages)
    tolerance = BANK_TEMPLATES[bank]['row_tolerance']
    keys = ['date', 'ref', 'name', 'debit', 'credit', 'amount', 'balance']
    labels = {'date': 'Fecha', 'ref': 'Documento', 'name': 'Descripcion', 'debit': 'Debito',
              'credit': 'Credito', 'amount': 'Monto', 'balance': 'Saldo'}
    header_keys = None
    rows = []
    for items in pages:
        found = _find_header(items, keywords)
        if not found:
            continue
        group, mapping, header_bottom = found
        header_ids = {id(i) for i in group}
        columns = [(item['xc'], next((k for k, idx in mapping.items() if idx == pos), None))
                   for pos, item in enumerate(group)]
        if header_keys is None:
            header_keys = [k for k in keys if k in mapping]
        date_xc = group[mapping['date']]['xc']
        body = [i for i in items if id(i) not in header_ids and i['y'] > header_bottom - 1]

        def column_of(item):
            return min(columns, key=lambda c: abs(c[0] - item['xc']))[1]

        anchors = sorted((i for i in body if DATE_RE.match(i['text']) and column_of(i) == 'date'
                          and abs(i['xc'] - date_xc) < 40), key=lambda i: i['y'])
        if not anchors:
            continue
        buckets = [[] for _ in anchors]
        for item in body:
            nearest = min(range(len(anchors)), key=lambda n: abs(anchors[n]['y'] - item['y']))
            if abs(anchors[nearest]['y'] - item['y']) > tolerance:
                continue
            buckets[nearest].append((column_of(item), item))
        for bucket in buckets:
            # Un renglón que empieza en la misma x que otro ya clasificado de la misma fila es su
            # continuación (p. ej. "ACH" debajo de "N/CREDITO TRANSFERENCIA", que empieza a la
            # izquierda del título de la columna Descripción).
            known = [(it['x0'], key) for key, it in bucket if key in header_keys]
            row = {k: [] for k in header_keys}
            for key, it in bucket:
                if key not in header_keys:
                    key = next((k for x0, k in known if abs(x0 - it['x0']) <= 2), None)
                if key in header_keys:
                    row[key].append(it)
            rows.append([' '.join(i['text'] for i in sorted(row[k], key=lambda i: (i['y'], i['x0'])))
                         for k in header_keys])
    if not header_keys:
        raise BankPdfError('No se encontró la tabla de movimientos en el PDF (encabezado con Fecha y '
                           'Débito/Crédito).')
    return bank, [[labels[k] for k in header_keys]] + rows
