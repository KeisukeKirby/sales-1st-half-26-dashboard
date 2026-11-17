"""Barefoot Inc. -> partner invoice reports -> DATA.bft_partners.

Shown as a reference block on the channel tab (05). These invoices are
Barefoot Inc.'s wholesale to a partner; whether the dashboard's existing
"BFT Consignment" figures already contain them has not been checked
against the source, so the block is never added to any dashboard total.

Run after aggregate.py: this script writes the 'bft_partners' key into
data/dashboard_data.json and re-embeds DATA into dashboard.html/index.html.

Input: data/raw/bft_partners/<Partner>.xlsx, the accounting system's
"Invoice Report" (Show details) export. The partner name is the file stem.
Layout: one row per product line; the invoice-level discount and the
discounted ex-VAT / VAT-incl totals sit on the invoice's first row only
(No VAT + VAT 0% + VAT 7% = discounted ex-VAT base; Grand Total = incl VAT).
Each invoice's discounted ex-VAT base is split over its lines by their
pre-VAT list amount, so line amounts always sum back to the invoice.
"""
import json
import re
from collections import OrderedDict
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT / 'data' / 'raw' / 'bft_partners'
DATA_JSON = ROOT / 'data' / 'dashboard_data.json'
HTMLS = [ROOT / 'dashboard.html', ROOT / 'index.html']

BRAND_PREFIX = {
    'VFF': 'VFF', 'CP': 'Coolcore', 'CC': 'Coolcore', 'OLN': 'Oleno', 'BFJ': 'BFJ',
    'MTB': 'TabiRela', 'TBO': 'Tabio', 'KC': 'Tabio', 'SW': 'Swans', 'KA': 'Knockaround',
    'VV': 'Vivo', 'KK': 'Klean Kanteen', 'LN': 'LUNA', 'AQ': 'AQOZ', 'KE': 'KEEN',
}


def num(v):
    if v in (None, ''):
        return 0.0
    return float(str(v).replace(',', '')) if not isinstance(v, (int, float)) else float(v)


def read_report(path):
    rows = list(openpyxl.load_workbook(path, read_only=True, data_only=True).worksheets[0].iter_rows(values_only=True))
    hi = next(i for i, r in enumerate(rows) if r and r[1] == 'Document No.')  # header row below the report banner
    ix = {h.strip(): i for i, h in enumerate(rows[hi]) if isinstance(h, str)}
    # 'VAT Amount' and 'WHT' appear twice (line and invoice level); take the invoice-level columns by position
    pos = {h: i for i, h in enumerate(rows[hi]) if h}
    exported = next((str(r[0]).split(':', 1)[1].strip() for r in rows[:hi] if r and str(r[0]).startswith('Export Date')), '')
    inv = OrderedDict()
    for r in rows[hi + 1:]:
        if not r or not r[ix['Document No.']]:
            continue
        no = r[ix['Document No.']]
        i = inv.setdefault(no, {'date': r[ix['Issue Date']], 'status': r[ix['Status']], 'lines': [], 'net': None, 'grand': None})
        if r[pos['Grand Total']] not in (None, ''):
            i['net'] = num(r[pos['No VAT']]) + num(r[pos['VAT 0%']]) + num(r[pos['VAT 7%']])
            i['grand'] = num(r[pos['Grand Total']])
        i['lines'].append(r)
    invoices, lines = [], []
    for no, i in inv.items():
        d, m, y = str(i['date']).split('/')
        month = f'{y}-{m}'
        list_total = sum(num(r[ix['Pre-VAT Amount']]) for r in i['lines'])
        ratio = (i['net'] / list_total) if list_total else 0.0
        invoices.append([no, month, i['status'], round(i['net'], 2), round(i['grand'], 2), round(list_total, 2)])
        for r in i['lines']:
            code = str(r[ix['Product/Service  Code']] or r[ix.get('Product/Service Code', ix['Product/Service  Code'])] or '')
            m_ = re.match(r'^[A-Za-z]+', code)
            brand = BRAND_PREFIX.get(m_.group(0) if m_ else '', 'Others')
            model = str(r[ix['Product/Service Name']]).split('(')[0].strip()
            lines.append([month, brand, model, num(r[ix['Quantity']]), round(num(r[ix['Pre-VAT Amount']]) * ratio, 4)])
    return {'source': path.name, 'exported': exported, 'invoices': invoices, 'lines': lines}


def main():
    out = {}
    for path in sorted(SRC_DIR.glob('*.xlsx')):
        rep = read_report(path)
        # aggregate lines to month x brand x model so the dashboard stays small
        agg = {}
        for month, brand, model, q, a in rep['lines']:
            k = (month, brand, model)
            agg[k] = [agg.get(k, [0, 0])[0] + q, agg.get(k, [0, 0])[1] + a]
        rep['lines'] = [[*k, round(v[0]), round(v[1], 4)] for k, v in sorted(agg.items())]  # 4 dp so lines still sum to invoices
        net = sum(i[3] for i in rep['invoices'])
        assert abs(net - sum(l[4] for l in rep['lines'])) < 0.05, f'{path.name}: line split does not add up to invoices'
        out[path.stem] = rep
        print(f'{path.stem}: {len(rep["invoices"])} invoices, ex-VAT {net:,.2f}, months {rep["invoices"][0][1]}..{rep["invoices"][-1][1]}')
    data = json.loads(DATA_JSON.read_text(encoding='utf-8'))
    data['bft_partners'] = out
    DATA_JSON.write_bytes(json.dumps(data, ensure_ascii=False, indent=1).encode('utf-8'))  # keep LF on Windows
    line = 'const DATA = ' + json.dumps(data, ensure_ascii=False, separators=(',', ':')) + ';'
    for h in HTMLS:
        src = h.read_text(encoding='utf-8')
        new, n = re.subn(r'^const DATA = .*;$', lambda _: line, src, count=1, flags=re.M)
        assert n == 1, f'{h.name}: DATA line not found'
        h.write_bytes(new.encode('utf-8'))


if __name__ == '__main__':
    main()
