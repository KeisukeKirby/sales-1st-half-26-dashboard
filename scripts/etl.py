#!/usr/bin/env python3
"""
ETL for Barefoot Inc sales dashboard (Jan-Jun 2026).
Consolidates 16 source files into canonical transaction records, then aggregates.
"""
import openpyxl, csv, re, json
from collections import defaultdict, Counter
from datetime import datetime, date

SRC = "/root/.claude/uploads/7c7fe66c-960c-5108-be91-c1dc0972813f/"

records = []  # each: dict(store, category, channel, date(YYYY-MM-DD), month(YYYY-MM),
              #            brand, model, qty, amount, order_id, payment)
issues = []   # data-quality notes to surface

def note(msg):
    issues.append(msg)
    print("NOTE:", msg)

# ---------------------------------------------------------------- helpers
def parse_dmy(s):
    """Parse a D/M/YYYY (day-first, verified across all files so far) string date."""
    if not s:
        return None
    s = str(s).strip()
    m = re.match(r'^(\d{1,2})/(\d{1,2})/(\d{4})$', s)
    if not m:
        return None
    d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        return date(y, mo, d)
    except ValueError:
        return None

def to_date(v):
    if isinstance(v, (date, datetime)):
        return v.date() if isinstance(v, datetime) else v
    return parse_dmy(v)

def num(v):
    if v is None or v == '':
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).replace(',', '').strip())
    except ValueError:
        return 0.0

BRAND_PREFIX = {
    'VFF': 'VFF', 'BFJ': 'BFJ', 'CP': 'Coolcore', 'CC': 'Coolcore',
    'OLN': 'Oleno', 'MTB': 'TabiRela',
    'KK': 'Others', 'SW': 'Others', 'KA': 'Others', 'LN': 'Others', 'TUB': 'Others',
}
OTHERS_SUBBRAND_PREFIX = {'KK': 'Klean Kanteen', 'SW': 'Swans', 'KA': 'Knockaround', 'LN': 'LUNA', 'TUB': 'Tube'}
NON_PRODUCT_PREFIX = {'DC', 'CON', 'P'}  # DC=discount line, CON=consignment doc ref, P=misc asset-sale income (non-product)

def normalize_channel(v):
    if not v:
        return None
    s = str(v).strip()
    if not s:
        return None
    if s.startswith('Shopee'):
        return 'Shopee'
    return s

def normalize_payment(v):
    """Map raw Payment channel text to Cash / Credit Card / QR per confirmed business rule:
       Cash->Cash, credit card (any bank)->Credit Card, KBANK & bank-transfer (เงินโอน)->QR."""
    if not v:
        return None
    s = str(v).strip()
    if not s:
        return None
    if s == 'Cash':
        return 'Cash'
    if 'บัตรเครดิต' in s or 'เครดิต' in s.lower() or 'credit' in s.lower():
        return 'Credit Card'
    if s == 'KBANK' or 'เงินโอน' in s:
        return 'QR Code'
    return 'Other'

def classify_by_code(code):
    if not code:
        return None, None
    m = re.match(r'^[A-Za-z]+', str(code))
    prefix = m.group(0) if m else str(code)
    if prefix in NON_PRODUCT_PREFIX:
        return 'EXCLUDE', None
    brand = BRAND_PREFIX.get(prefix)
    sub = OTHERS_SUBBRAND_PREFIX.get(prefix)
    return brand, sub

def model_from_name(name):
    """Generic model label for ANY brand: full product name up to the first '(',
    e.g. 'VFF V-Soul', 'CP Arm Sleeves', 'Marugo TabiRela', 'BFJ Socks', 'Oleno Ultimate'.
    Kept brand-prefixed (not stripped) so top/bottom-model rankings read the same way
    across every source file."""
    if not name:
        return 'Other'
    return str(name).split('(')[0].strip()

# name-based classification for Siam Discovery (no product codes) -- normalized to the
# same brand-prefixed naming convention used by every other (code-based) source file.
NAME_VFF_KEYWORDS = ['V-SOUL','V-RUN','V-TREK','V-ALPHA','V-TRAIN','V-AQUA','KSO','BREEZANDAL',
                      'SPIDRWALK','SCRAMKEY','TRAILOPE','GROUNDSPLAY','GRASPIFIER','SOCKS MINI CREW',
                      'SOCKS CREW','SOCKS HIGH CREW','HIGH CREW','CVT HEMP','KMD','VFF']
def classify_by_name(name):
    if not name:
        return None, None, 'Other'
    n = str(name).upper()
    base = n.split('(')[0].strip().title()
    if 'BFJ' in n:
        return 'BFJ', None, base
    if n.startswith('OLENO') or n.startswith('OLN'):
        return 'Oleno', None, base
    if n.startswith('TABI'):
        return 'TabiRela', None, ('Marugo ' + base if not base.upper().startswith('MARUGO') else base)
    for kw in NAME_VFF_KEYWORDS:
        if kw in n:
            return 'VFF', None, ('VFF ' + base if not base.upper().startswith('VFF') else base)
    return 'Unknown', None, base

# VFF shoe / non-shoe (socks, furoshiki-wrap accessories with no numeric size, etc.)
# classifier, plus gender inference. VFF footwear codes/names always carry a size token
# shaped like an optional single gender letter + a number in the last parenthesized
# group -- "(BK,W37)" (code) or "(W37, Baby Blue)" (name) -- e.g. W37=Women's 37,
# M43=Men's 43, U/no-letter=Unisex. Sock-type items use letter-only sizing (S/M/L/XL)
# with no digits, which this pattern deliberately does not match.
VFF_SIZE_TOKEN_RE = re.compile(r'^([MWUmwu]?)(\d+)$')
def vff_shoe_gender(text):
    if not text:
        return False, None
    s = str(text)
    m = re.search(r'\(([^()]*)\)', s)
    if m:
        for token in (p.strip() for p in m.group(1).split(',')):
            gm = VFF_SIZE_TOKEN_RE.match(token)
            if gm:
                g = gm.group(1).upper()
                return True, ('Women' if g == 'W' else 'Men' if g == 'M' else 'Unisex')
    # fallback for malformed source codes missing the comma/closing paren
    # (seen in Central_Total_Department, e.g. "VFF02(TTBKM42" instead of
    # "VFF02(TTBK,M42)") -- look for a trailing gender-letter + size at the
    # very end of the string.
    fm = re.search(r'([MWUmwu])(\d{2,3})\)?\s*$', s)
    if fm:
        g = fm.group(1).upper()
        return True, ('Women' if g == 'W' else 'Men' if g == 'M' else 'Unisex')
    return False, None

def add_record(store, category, date_, brand, model, sub, qty, amount, order_id,
                channel=None, payment=None, entity=None, vff_source_text=None):
    if date_ is None:
        return
    if brand == 'EXCLUDE':
        return
    is_shoe, gender = (False, None)
    if brand == 'VFF':
        is_shoe, gender = vff_shoe_gender(vff_source_text)
    records.append(dict(
        store=store, category=category, date=date_.isoformat(),
        month=date_.strftime('%Y-%m'), brand=brand or 'Unknown', model=model,
        is_vff_shoe=is_shoe, gender=gender,
        sub=sub, qty=qty, amount=amount, order_id=order_id,
        channel=channel, payment=payment, entity=entity,
    ))

# ================================================================== brand-prefix numeric-code -> model lookup
# Central_Total_Department uses short codes like "VFF08"/"BFJ01"/"OLN05" instead of the
# "VFF0008"/"BFJ0001"/"OLN0005"-style codes used elsewhere. Build a (prefix, normalized-numeric)
# -> model-name table from the well-labeled files (product name is present) so short-code files
# can be backfilled, for every brand prefix -- not just VFF.
CODE_TO_MODEL = {}
def _scan_codes(fn, sheet, header_row_idx, code_key, name_key):
    wb = openpyxl.load_workbook(fn, data_only=True, read_only=True)
    ws = wb[sheet]
    rows = list(ws.iter_rows(values_only=True))
    header = rows[header_row_idx]
    idx = {h: i for i, h in enumerate(header) if h}
    for r in rows[header_row_idx + 1:]:
        if not any(r):
            continue
        code = r[idx.get(code_key)] if code_key in idx else None
        name = r[idx.get(name_key)] if name_key in idx else None
        if not code:
            continue
        m = re.match(r'^([A-Za-z]+)0*(\d+)', str(code).upper())
        if not m:
            continue
        prefix, num_code = m.group(1), int(m.group(2))
        model = model_from_name(name)
        key = (prefix, num_code)
        if model and model not in ('Other',) and key not in CODE_TO_MODEL:
            CODE_TO_MODEL[key] = model

_scan_codes(SRC + 'a0d9bc79-Sales_K_village_JanJun_26.xlsx', 'Orders', 1, 'Product code', 'Product name')
_scan_codes(SRC + '835c1952-Sales_Thaniya_JanJun_26.xlsx', 'Orders', 1, 'Product code', 'Product name')
_scan_codes(SRC + 'cf220ee8-BFT_Shopee_Lazada_Facebook_JanJun_26.xlsx', 'Orders', 1, 'Product code', 'Product name')
_scan_codes(SRC + '2932d908-Sales_Paradies_Park_JanJun_26.xlsx', 'Orders', 1, 'Product code', 'Product name')
print(f"Built brand code->model lookup with {len(CODE_TO_MODEL)} entries")

# ================================================================== 1. VFF Cart LP (csv)
def load_vff_cart_lp():
    fn = SRC + 'fdc407d1-Sale_VFF_Cart_LP_01062026.csv'
    with open(fn, encoding='utf-8-sig') as f:
        rows = list(csv.reader(f))
    header = rows[0]
    for r in rows[1:]:
        if not any(c.strip() for c in r if c):
            continue
        order_id, dt, sku, item, qty, net = r[0], r[1], r[2], r[3], r[4], r[5]
        d = parse_dmy(dt)
        brand, sub = classify_by_code(sku)
        model = model_from_name(item)
        add_record('VFF Cart LP', 'store', d, brand, model, sub, num(qty), num(net), order_id, vff_source_text=sku)
load_vff_cart_lp()

# ================================================================== generic "Orders" schema loader
def load_orders_style(fn, sheet, store_label, category, header_row_idx=1,
                       has_channel=False, has_payment_channel=False,
                       is_online_split=False, entity=None):
    wb = openpyxl.load_workbook(fn, data_only=True, read_only=True)
    ws = wb[sheet]
    rows = list(ws.iter_rows(values_only=True))
    header = rows[header_row_idx]
    idx = {h: i for i, h in enumerate(header) if h}
    data = rows[header_row_idx + 1:]

    # order-level fields (Sales channel / Payment channel) are only populated on an
    # order's first line in these exports; forward-fill them per order_id first.
    order_channel, order_payment = {}, {}
    if has_channel or has_payment_channel:
        for r in data:
            if not any(r):
                continue
            oid = r[idx.get('Sales order No.')]
            if not oid:
                continue
            if has_channel and 'Sales channel' in idx and r[idx['Sales channel']] and oid not in order_channel:
                order_channel[oid] = r[idx['Sales channel']]
            if has_payment_channel and 'Payment channel' in idx and r[idx['Payment channel']] and oid not in order_payment:
                order_payment[oid] = r[idx['Payment channel']]

    n = 0
    for r in data:
        if not any(r):
            continue
        pc = r[idx.get('Product code')]
        if not pc:
            continue  # skip order-level-only rows (no product on this line)
        d = to_date(r[idx.get('Date')])
        if d is None:
            continue
        qty = num(r[idx.get('Quantity')])
        amt = num(r[idx.get('Total amount')])
        order_id = r[idx.get('Sales order No.')]
        brand, sub = classify_by_code(pc)
        pname = r[idx.get('Product name')]
        model = model_from_name(pname)
        channel = normalize_channel(order_channel.get(order_id)) if has_channel else None
        payment_raw = order_payment.get(order_id) if has_payment_channel else None
        payment = normalize_payment(payment_raw)
        store = store_label
        cat = category
        if is_online_split:
            store = 'Online'
            cat = 'online'
        add_record(store, cat, d, brand, model, sub, qty, amt, order_id, channel=channel,
                    payment=payment, entity=entity, vff_source_text=pc)
        n += 1
    print(f"loaded {n} rows from {fn.split('/')[-1]} -> {store_label}")

# 2. BFT online (original)
load_orders_style(SRC + 'cf220ee8-BFT_Shopee_Lazada_Facebook_JanJun_26.xlsx', 'Orders',
                   'Online', 'online', has_channel=True, is_online_split=True, entity='BFT')
# 3. BFT_EVENT_3
load_orders_style(SRC + '2514cf15-BFT_EVENT_3.xlsx', 'Orders (2)', 'Event', 'event', has_channel=True)
# 4. Paradise Park
load_orders_style(SRC + '2932d908-Sales_Paradies_Park_JanJun_26.xlsx', 'Orders',
                   'Paradise Park', 'store', has_channel=True)
# 5. Thaniya
load_orders_style(SRC + '835c1952-Sales_Thaniya_JanJun_26.xlsx', 'Orders', 'Thaniya', 'store')
# 6. K Village
load_orders_style(SRC + 'a0d9bc79-Sales_K_village_JanJun_26.xlsx', 'Orders', 'K Village', 'store')
# 7-9. Event files with payment channel (47-col schema); reuse loader (Product code / Date / etc. keys match)
load_orders_style(SRC + '9c5663cd-EDV_EVENT_1.xlsx', 'Orders', 'Event', 'event',
                   has_channel=True, has_payment_channel=True)
load_orders_style(SRC + '7abc0f65-BFT_EVENT_2.xlsx', 'Orders', 'Event', 'event',
                   has_channel=True, has_payment_channel=True)
load_orders_style(SRC + '0165b670-BFT_EVENT_1.xlsx', 'Orders', 'Event', 'event',
                   has_channel=True, has_payment_channel=True)

# ================================================================== Central LP 3F (Thai headers)
def load_central_lp3f():
    fn = SRC + '4106a54d-Sales_Central_LP_3F_JanJun_26.xlsx'
    wb = openpyxl.load_workbook(fn, data_only=True, read_only=True)
    ws = wb['รายการขาย']
    rows = list(ws.iter_rows(values_only=True))
    header = rows[1]
    idx = {h: i for i, h in enumerate(header) if h}
    data = rows[2:]
    n = 0
    for r in data:
        if not any(r):
            continue
        pc = r[idx['รหัสสินค้า']]
        if not pc:
            continue
        d = to_date(r[idx['วันที่ทำรายการ']])
        if d is None:
            continue
        qty = num(r[idx['จำนวน']])
        amt = num(r[idx['ราคารวม']])
        order_id = r[idx['รายการ']]
        brand, sub = classify_by_code(pc)
        pname = r[idx['ชื่อสินค้า']]
        model = model_from_name(pname)
        add_record('Central Ladprao 3F (Coollabo)', 'store', d, brand, model, sub, qty, amt, order_id, vff_source_text=pc)
        n += 1
    print(f"loaded {n} rows -> Central Ladprao 3F")
load_central_lp3f()

# ================================================================== BFT consignment (with trap-row guard)
def load_consignment(fn, sheet, store_label):
    wb = openpyxl.load_workbook(fn, data_only=True, read_only=True)
    ws = wb[sheet]
    rows = list(ws.iter_rows(values_only=True))
    header = rows[1]
    idx = {h: i for i, h in enumerate(header) if h}
    data = rows[2:]
    n = 0
    for r in data:
        if not any(r):
            continue
        doc = r[idx['เลขที่เอกสาร']]
        pc = r[idx['รหัสสินค้า/บริการ']]
        if not doc or not pc:
            continue  # guards against the trailing "รวม" total row (blank doc & product code)
        d = parse_dmy(r[idx['วันที่ออก']])
        if d is None:
            continue
        qty = num(r[idx['Quantity']])
        # 'Amount' = invoice-level net total, present only on first product row of each invoice
        amt_col = r[idx['Amount']]
        amt = num(amt_col) if amt_col not in (None, '') else 0.0
        brand, sub = classify_by_code(pc)
        pname = r[idx['ชื่อสินค้า/บริการ']]
        model = model_from_name(pname)
        add_record(store_label, 'consignment', d, brand, model, sub, qty, amt, doc, vff_source_text=pc)
        n += 1
    print(f"loaded {n} rows -> {store_label}")
load_consignment(SRC + 'c49fbb57-BFT_consignment__JanJun_26.xlsx', 'รายงานใบแจ้งหนี้', 'BFT Consignment')

# ================================================================== EDV consignment (no header row, positional)
def load_edv_consignment():
    fn = SRC + '21cdb27d-EDV_consignment__JanJun_26.xlsx'
    wb = openpyxl.load_workbook(fn, data_only=True, read_only=True)
    ws = wb['รายการขาย']
    data = list(ws.iter_rows(values_only=True))
    # positional indices validated against EDV_EVENT_1 schema in the exploration phase
    COL = {'order': 2, 'date': 12, 'amount': 29, 'prodcode': 39, 'prodname': 40, 'qty': 41, 'total': 44}
    n = 0
    for r in data:
        if not any(r):
            continue
        order = r[COL['order']]
        pc = r[COL['prodcode']]
        if not order or not pc:
            continue
        d = parse_dmy(r[COL['date']])
        if d is None:
            continue
        qty = num(r[COL['qty']])
        amt_col = r[COL['amount']]
        amt = num(amt_col) if amt_col not in (None, '') else 0.0
        brand, sub = classify_by_code(pc)
        pname = r[COL['prodname']]
        model = model_from_name(pname)
        add_record('EDV Consignment', 'consignment', d, brand, model, sub, qty, amt, order, vff_source_text=pc)
        n += 1
    print(f"loaded {n} rows -> EDV Consignment")
load_edv_consignment()

# ================================================================== Siam Discovery (name-based classification)
def load_siam_discovery():
    fn = SRC + 'd7e7cac8-Sales_Siam_Dis_JanJun_26.xlsx'
    wb = openpyxl.load_workbook(fn, data_only=True, read_only=True)
    ws = wb['Sheet1']
    rows = list(ws.iter_rows(values_only=True))
    data = rows[1:]
    n = 0
    for i, r in enumerate(data):
        if not r or not r[1]:
            continue  # blank Item = zero-sales placeholder day
        d = to_date(r[0])
        item = r[1]
        qty = num(r[2])
        net = num(r[3])
        brand, sub, model = classify_by_name(item)
        add_record('Siam Discovery', 'store', d, brand, model, sub,
                    qty, net, f'SIAMDIS-{i}', vff_source_text=item)
        n += 1
    print(f"loaded {n} rows -> Siam Discovery")
load_siam_discovery()

# ================================================================== EDV online (Shopee/Lazada/etc.)
def load_simple_online(fn, store_label, category, entity=None):
    wb = openpyxl.load_workbook(fn, data_only=True, read_only=True)
    ws = wb['รายการขาย']
    rows = list(ws.iter_rows(values_only=True))
    header = rows[0]
    idx = {h: i for i, h in enumerate(header) if h}
    data = rows[1:]
    n = 0
    for r in data:
        if not any(r):
            continue
        sku = r[idx['SKU']]
        if not sku:
            continue
        d = to_date(r[idx['Sale Date']])
        if d is None:
            continue
        qty = num(r[idx['Sales Quantity']])
        amt = num(r[idx['Net']])
        order_id = r[idx['No.']]
        channel = normalize_channel(r[idx['Channel']])
        brand, sub = classify_by_code(sku)
        item = r[idx['Item']]
        model = model_from_name(item)
        add_record(store_label, category, d, brand, model, sub, qty, amt, order_id, channel=channel,
                    entity=entity, vff_source_text=sku)
        n += 1
    print(f"loaded {n} rows -> {store_label}")
    return set(str(r[idx['No.']]).strip() for r in data if any(r) and r[idx.get('No.')])

edv_online_orders = load_simple_online(SRC + 'a024894a-EDV_Shopee_Lazada_Facebook_JanJun_26.xlsx',
                                        'Online', 'online', entity='EDV')

# ================================================================== BFT merged file: only non-overlapping 13 orders
def load_bft_merged_new_only():
    fn = SRC + '6de07263-BFT_Shopee_Lazada_Facebook_Paradise_Event_JanJun_26.xlsx'
    wb = openpyxl.load_workbook(fn, data_only=True, read_only=True)
    ws = wb['รายการขาย']
    rows = list(ws.iter_rows(values_only=True))
    header = rows[0]
    idx = {h: i for i, h in enumerate(header) if h}
    data = rows[1:]

    # recompute known-old order id sets to determine which orders are "new"
    def get_orders(fn2, sheet2, colname, header_idx=1):
        wb2 = openpyxl.load_workbook(fn2, data_only=True, read_only=True)
        ws2 = wb2[sheet2]
        rows2 = list(ws2.iter_rows(values_only=True))
        header2 = rows2[header_idx]
        idx2 = {h: i for i, h in enumerate(header2) if h}
        orders = set()
        for r in rows2[header_idx + 1:]:
            if not any(r):
                continue
            v = r[idx2[colname]]
            if v:
                orders.add(str(v).strip())
        return orders

    old_online = get_orders(SRC + 'cf220ee8-BFT_Shopee_Lazada_Facebook_JanJun_26.xlsx', 'Orders', 'Sales order No.')
    old_paradise = get_orders(SRC + '2932d908-Sales_Paradies_Park_JanJun_26.xlsx', 'Orders', 'Sales order No.')
    old_event1 = get_orders(SRC + '0165b670-BFT_EVENT_1.xlsx', 'Orders', 'Sales order No.')
    old_event2 = get_orders(SRC + '7abc0f65-BFT_EVENT_2.xlsx', 'Orders', 'Sales order No.')
    old_event3 = get_orders(SRC + '2514cf15-BFT_EVENT_3.xlsx', 'Orders (2)', 'Sales order No.')
    union_old = old_online | old_paradise | old_event1 | old_event2 | old_event3

    n = 0
    seen_in_this_file = set()
    for r in data:
        if not any(r):
            continue
        onum = str(r[idx['No.']]).strip()
        if onum in union_old:
            continue  # already counted via the original per-store files
        sku = r[idx['SKU']]
        if not sku:
            continue
        d = to_date(r[idx['Sale Date']])
        if d is None:
            continue
        qty = num(r[idx['Sales Quantity']])
        amt = num(r[idx['Net']])
        channel = normalize_channel(r[idx['Channel']])
        warehouse = r[idx['warehouse']]
        brand, sub = classify_by_code(sku)
        item = r[idx['Item']]
        model = model_from_name(item)
        if warehouse == 'Paradise Park':
            add_record('Paradise Park', 'store', d, brand, model, sub, qty, amt, onum, channel=channel, vff_source_text=sku)
        else:
            add_record('Online', 'online', d, brand, model, sub, qty, amt, onum, channel=channel, vff_source_text=sku)
        n += 1
    print(f"loaded {n} rows (non-duplicate only) -> BFT merged supplemental")
load_bft_merged_new_only()

# ================================================================== BFT_Central_Total_Department (monthly, split by Store Name)
def load_central_total_department():
    fn = SRC + '026d19bf-BFT_Central_Total_Department_JanJun_26.xlsx'
    wb = openpyxl.load_workbook(fn, data_only=True, read_only=True)
    ws = wb['Export']
    rows = list(ws.iter_rows(values_only=True))
    header = rows[0]
    idx = {h: i for i, h in enumerate(header) if h}
    data = rows[1:]
    MONTHS = {'Jan':1,'Feb':2,'Mar':3,'Apr':4,'May':5,'Jun':6}
    STORE_NAME_MAP = {
        'CHIDLOM': 'Central Chidlom',
        'CHIDLOM ONLINE': 'Central Chidlom Online',
        'CENTRAL WORLD-CDS': 'Central World (CDS)',
        'LARDPRAO': 'Central Lardprao (Dept.)',
        'EASTVILLE': 'Central Eastville',
    }
    n = 0
    for r in data:
        if not any(r):
            continue
        store = r[idx['Store Name']]
        cat = r[idx['Catalogue No.']]
        msd = r[idx['Month Sales Date']]
        if not store or not cat or not msd:
            continue
        mo, yr = str(msd).split('-')
        d = date(int(yr), MONTHS[mo], 1)  # first-of-month placeholder (source has no daily granularity)
        qty = num(r[idx['Sales Quantity']])
        amt = num(r[idx['Total Net Sales (Sales Amount)']])
        brand, sub = classify_by_code(cat)
        model = None
        mcode = re.match(r'^([A-Za-z]+)0*(\d+)', str(cat).upper())
        if mcode:
            model = CODE_TO_MODEL.get((mcode.group(1), int(mcode.group(2))), 'Other')
        store_label = STORE_NAME_MAP.get(store, f'Central {store.title()}')
        add_record(store_label, 'central_dept', d, brand, model, sub, qty, amt,
                   order_id=None, vff_source_text=cat)
        n += 1
    print(f"loaded {n} rows -> Central Total Department (5 stores)")
load_central_total_department()

# ================================================================== summary / sanity checks
print()
print("="*80)
print(f"TOTAL RECORDS: {len(records)}")
total_amt = sum(r['amount'] for r in records)
total_qty = sum(r['qty'] for r in records)
print(f"TOTAL AMOUNT (all categories): {total_amt:,.2f}")
print(f"TOTAL QTY (all categories): {total_qty:,.0f}")

by_store = defaultdict(lambda: {'amount':0.0,'qty':0.0,'orders':set()})
for r in records:
    by_store[r['store']]['amount'] += r['amount']
    by_store[r['store']]['qty'] += r['qty']
    if r['order_id']:
        by_store[r['store']]['orders'].add(r['order_id'])
print()
print(f"{'Store':40s} {'Amount':>15s} {'Qty':>8s} {'Orders':>8s}")
for store, v in sorted(by_store.items(), key=lambda x: -x[1]['amount']):
    print(f"{store:40s} {v['amount']:>15,.2f} {v['qty']:>8,.0f} {len(v['orders']):>8d}")

# brand totals
by_brand = defaultdict(lambda: {'amount':0.0,'qty':0.0})
for r in records:
    by_brand[r['brand']]['amount'] += r['amount']
    by_brand[r['brand']]['qty'] += r['qty']
print()
print("Brand totals:")
for b, v in sorted(by_brand.items(), key=lambda x: -x[1]['amount']):
    print(f"  {b:15s} amount={v['amount']:>14,.2f}  qty={v['qty']:>8,.0f}")

# save raw records
with open('/tmp/claude-0/-home-user-sales-1st-half-26-dashboard/7c7fe66c-960c-5108-be91-c1dc0972813f/scratchpad/records.json', 'w', encoding='utf-8') as f:
    json.dump(records, f, ensure_ascii=False)
print()
print("Saved", len(records), "records to records.json")
