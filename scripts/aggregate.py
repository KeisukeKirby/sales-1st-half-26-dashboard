#!/usr/bin/env python3
"""Aggregate canonical records.json into the JSON payload consumed by the dashboard.

Every dimension is broken down by month (in addition to its H1 total) so the
dashboard can re-slice any figure into an arbitrary period (a single month,
Q1, Q2, or the full half) entirely client-side, without re-running this script.
"""
import json
from collections import defaultdict

records = json.load(open('/tmp/claude-0/-home-user-sales-1st-half-26-dashboard/7c7fe66c-960c-5108-be91-c1dc0972813f/scratchpad/records.json'))

MONTHS = ['2026-01','2026-02','2026-03','2026-04','2026-05','2026-06']

STORE_GROUP = {
    'K Village': 'retail', 'Thaniya': 'retail', 'Paradise Park': 'retail',
    'Central Ladprao 3F (Coollabo)': 'retail', 'VFF Cart LP': 'retail', 'Siam Discovery': 'retail',
    'Central Chidlom': 'central_dept', 'Central Chidlom Online': 'central_dept',
    'Central World (CDS)': 'central_dept', 'Central Lardprao (Dept.)': 'central_dept',
    'Central Eastville': 'central_dept',
    'Online': 'online', 'Event': 'event',
    'BFT Consignment': 'consignment', 'EDV Consignment': 'consignment',
}
GROUP_LABEL = {
    'retail': '実店舗', 'central_dept': 'Central百貨店内', 'online': 'オンライン',
    'event': 'イベント', 'consignment': '委託販売',
}

# Channel split requested specifically for the "VFF shoes only" section -- distinct
# from STORE_GROUP above (which the rest of the dashboard still uses). 直営実店舗 is
# ONLY the two company-run standalone shops; Coollabo and the VFF cart are mall
# corners inside Central properties so they roll into Central百貨店; Thaniya and
# Event each get their own bucket (Thaniya carries no VFF shoe sales at all).
CHANNEL5 = {
    'Online': 'オンラインストア',
    'BFT Consignment': '委託販売(オフライン)', 'EDV Consignment': '委託販売(オフライン)',
    'K Village': '直営実店舗', 'Paradise Park': '直営実店舗',
    'Central Ladprao 3F (Coollabo)': 'Central百貨店', 'VFF Cart LP': 'Central百貨店',
    'Central Chidlom': 'Central百貨店', 'Central Chidlom Online': 'Central百貨店',
    'Central World (CDS)': 'Central百貨店', 'Central Lardprao (Dept.)': 'Central百貨店',
    'Central Eastville': 'Central百貨店',
    'Siam Discovery': 'Siam Discovery',
    'Thaniya': 'Thaniya',
    'Event': 'イベント',
}
GENDER_LABEL = {'Women': '女性', 'Men': '男性', 'Unisex': 'ユニセックス'}

def new_acc():
    return {'amount': 0.0, 'qty': 0.0, 'orders': set()}

def ser(acc):
    return {'amount': round(acc['amount'], 2), 'qty': round(acc['qty'], 1),
            'orders': len(acc['orders']) if isinstance(acc['orders'], set) else acc['orders']}

def monthly_out(acc_by_key_month):
    """{key: {month: acc}} -> {key: {month: {amount,qty,orders}}}, every month present."""
    return {k: {m: ser(months.get(m, new_acc())) for m in MONTHS} for k, months in acc_by_key_month.items()}

# ---------------------------------------------------------------- model-name casing normalization
# Different source files render the same model with different casing
# ("VFF KSO EVO" vs "VFF Kso Evo") -- collapse by uppercase key, keep whichever casing
# variant carries the most revenue as the canonical display label.
_casing_amount = defaultdict(lambda: defaultdict(float))
for r in records:
    if r['model']:
        _casing_amount[r['model'].upper()][r['model']] += r['amount']
MODEL_CANON = {
    upper_key: max(variants.items(), key=lambda kv: kv[1])[0]
    for upper_key, variants in _casing_amount.items()
}
def canon_model(m):
    return MODEL_CANON.get(m.upper(), m) if m else m

# ---------------------------------------------------------------- accumulators
# every "_month" accumulator is {key: {month: acc}}; totals are summed from these.
store_month = defaultdict(lambda: defaultdict(new_acc))                    # store -> month
store_brand_month = defaultdict(lambda: defaultdict(lambda: defaultdict(new_acc)))   # store -> brand -> month
store_payment_month = defaultdict(lambda: defaultdict(lambda: defaultdict(new_acc))) # store -> method -> month

overall_month = defaultdict(new_acc)                                       # month
brand_month = defaultdict(lambda: defaultdict(new_acc))                    # brand -> month
model_month = defaultdict(lambda: defaultdict(new_acc))                    # model (all brands) -> month
brand_model_month = defaultdict(lambda: defaultdict(lambda: defaultdict(new_acc)))   # brand -> model -> month
others_sub_month = defaultdict(lambda: defaultdict(new_acc))               # sub-brand -> month
online_channel_month = defaultdict(lambda: defaultdict(new_acc))           # channel -> month
event_payment_month = defaultdict(lambda: defaultdict(new_acc))            # method -> month (Event store only)

vff_shoe_by_month = defaultdict(new_acc)                                   # month (VFF shoes overall)
vff_shoe_channel_month = defaultdict(lambda: defaultdict(new_acc))         # channel5 -> month
vff_shoe_store_month = defaultdict(lambda: defaultdict(new_acc))           # raw store name -> month (individual stores, not channel5-grouped)
vff_shoe_model_month = defaultdict(lambda: defaultdict(new_acc))           # model (VFF shoes only) -> month
vff_shoe_gender_month = defaultdict(lambda: defaultdict(new_acc))          # gender -> month

for r in records:
    store, month, brand = r['store'], r['month'], r['brand']
    amt, qty = r['amount'], r['qty']
    # order numbering is only unique WITHIN a store's own scheme (two different
    # stores can independently produce the same order id) -- qualify by store so
    # every accumulator's order count, not just the store-scoped ones, is correct.
    oid = (store, r['order_id']) if r['order_id'] else None

    def add(acc, oid=oid):
        acc['amount'] += amt
        acc['qty'] += qty
        if oid:
            acc['orders'].add(oid)

    add(store_month[store][month])
    add(store_brand_month[store][brand][month])
    add(overall_month[month])
    add(brand_month[brand][month])

    model_c = canon_model(r['model'])
    if model_c:
        add(model_month[model_c][month])
        add(brand_model_month[brand][model_c][month])

    if brand == 'Others' and r['sub']:
        add(others_sub_month[r['sub']][month])

    if store == 'Online' and r['channel']:
        add(online_channel_month[r['channel']][month])

    if r['payment']:
        add(store_payment_month[store][r['payment']][month])
        if store == 'Event':
            add(event_payment_month[r['payment']][month])

    if brand == 'VFF' and r.get('is_vff_shoe'):
        add(vff_shoe_by_month[month])
        ch5 = CHANNEL5.get(store, store)
        add(vff_shoe_channel_month[ch5][month])
        add(vff_shoe_store_month[store][month])
        if model_c:
            add(vff_shoe_model_month[model_c][month])
        g = r.get('gender') or 'Unisex'
        add(vff_shoe_gender_month[g][month])

def sum_months(acc_by_month):
    total = new_acc()
    for m in MONTHS:
        a = acc_by_month.get(m, new_acc())
        total['amount'] += a['amount']
        total['qty'] += a['qty']
        total['orders'] |= a['orders']
    return total

# ---------------------------------------------------------------- build output
out = {'months': MONTHS}

# ---- KPI: give the client the monthly series; it derives any period's totals by summing.
out['monthly_overall'] = [
    {'month': m, **ser(overall_month[m])} for m in MONTHS
]
_h1_total = sum_months(overall_month)
out['kpi'] = {
    'total_amount': round(_h1_total['amount'], 2),
    'total_qty': round(_h1_total['qty'], 1),
    'total_orders': len(_h1_total['orders']),
    'avg_ticket': round(_h1_total['amount'] / len(_h1_total['orders']), 2) if _h1_total['orders'] else None,
    'period': '2026-01-01 ~ 2026-06-30',
    # last-year figures are not yet available (2025 H1 data not received) -- kept as an
    # explicit null block so the dashboard's YoY badges stay wired up and light up
    # automatically the moment this is filled in, instead of needing new UI code later.
    'last_year': None,
}

# ---- stores
stores_out = []
for store in store_month.keys():
    h1 = sum_months(store_month[store])
    s = ser(h1)
    s['store'] = store
    s['group'] = STORE_GROUP.get(store, 'other')
    s['avg_ticket'] = round(h1['amount'] / len(h1['orders']), 2) if h1['orders'] else None
    s['monthly'] = {m: ser(store_month[store].get(m, new_acc())) for m in MONTHS}
    s['brand_monthly'] = monthly_out(store_brand_month[store])
    if store_payment_month[store]:
        s['payment_monthly'] = monthly_out(store_payment_month[store])
    stores_out.append(s)
stores_out.sort(key=lambda x: -x['amount'])
out['stores'] = stores_out
out['group_label'] = GROUP_LABEL

# ---- brand
out['brand_monthly'] = monthly_out(brand_month)

# ---- all-brand model ranking (Top10/Worst10 recomputed client-side per period)
out['model_monthly'] = monthly_out(model_month)

# ---- per-brand model detail (dropdown)
out['brand_model_monthly'] = {b: monthly_out(models) for b, models in brand_model_month.items()}

# ---- Others sub-brand
out['others_sub_monthly'] = monthly_out(others_sub_month)

# ---- online channel
out['online_channel_monthly'] = monthly_out(online_channel_month)

# ---- VFF shoes only
out['vff_shoes'] = {
    'note': 'VFFブランドのうちシューズのみ（ソックス・Furoshiki等の非シューズ商品は除く）。'
            'サイズ表記（W=女性/M=男性/U=ユニセックス）から性別区分を推定',
    'monthly': [{'month': m, **ser(vff_shoe_by_month[m])} for m in MONTHS],
    'channel_monthly': monthly_out(vff_shoe_channel_month),
    'store_monthly': monthly_out(vff_shoe_store_month),
    'model_monthly': monthly_out(vff_shoe_model_month),
    'gender_monthly': {GENDER_LABEL.get(g, g): v for g, v in monthly_out(vff_shoe_gender_month).items()},
}

# ---- payment (Event category only, currently the sole source with payment data)
out['payment_overall'] = {
    'note': '決済方法データがあるのは「イベント」カテゴリのみ（他の店舗・チャネルには決済方法の記録がありません）',
    'monthly': monthly_out(event_payment_month),
}

with open('/tmp/claude-0/-home-user-sales-1st-half-26-dashboard/7c7fe66c-960c-5108-be91-c1dc0972813f/scratchpad/dashboard_data.json', 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, indent=None)

print("KPI:", out['kpi'])
print("Stores:", len(out['stores']))
print("Brands:", list(out['brand_monthly'].keys()))
print("Models (all brands):", len(out['model_monthly']))
print("Online channels:", list(out['online_channel_monthly'].keys()))
print("VFF shoe models:", len(out['vff_shoes']['model_monthly']))
import os
print("Output size (KB):", os.path.getsize('/tmp/claude-0/-home-user-sales-1st-half-26-dashboard/7c7fe66c-960c-5108-be91-c1dc0972813f/scratchpad/dashboard_data.json')/1024)
