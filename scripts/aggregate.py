#!/usr/bin/env python3
"""Aggregate canonical records.json into the JSON payload consumed by the dashboard."""
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

# 5-way channel split requested specifically for the "VFF shoes only" section --
# distinct from STORE_GROUP above (which the rest of the dashboard still uses).
# Event is folded into 直営実店舗 since it's company staff selling at a temporary
# venue, operationally the same as the other directly-run touchpoints.
CHANNEL5 = {
    'Online': 'オンラインストア',
    'BFT Consignment': '委託販売(オフライン)', 'EDV Consignment': '委託販売(オフライン)',
    'K Village': '直営実店舗', 'Thaniya': '直営実店舗', 'Paradise Park': '直営実店舗',
    'Central Ladprao 3F (Coollabo)': '直営実店舗', 'VFF Cart LP': '直営実店舗', 'Event': '直営実店舗',
    'Central Chidlom': 'Central百貨店', 'Central Chidlom Online': 'Central百貨店',
    'Central World (CDS)': 'Central百貨店', 'Central Lardprao (Dept.)': 'Central百貨店',
    'Central Eastville': 'Central百貨店',
    'Siam Discovery': 'Siam Discovery',
}
GENDER_LABEL = {'Women': '女性', 'Men': '男性', 'Unisex': 'ユニセックス'}

def new_acc():
    return {'amount': 0.0, 'qty': 0.0, 'orders': set()}

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

# ---------------------------------------------------------------- store-level
store_acc = defaultdict(new_acc)
store_month = defaultdict(lambda: defaultdict(new_acc))
store_brand = defaultdict(lambda: defaultdict(new_acc))
store_payment = defaultdict(lambda: defaultdict(new_acc))

overall_month = defaultdict(new_acc)
overall_brand = defaultdict(new_acc)
vff_model = defaultdict(new_acc)
others_sub = defaultdict(new_acc)
online_channel = defaultdict(new_acc)
online_channel_month = defaultdict(lambda: defaultdict(new_acc))
event_payment = defaultdict(new_acc)
brand_month = defaultdict(lambda: defaultdict(new_acc))
model_overall = defaultdict(new_acc)
brand_model = defaultdict(lambda: defaultdict(new_acc))

# VFF shoes only (excludes VFF socks/furoshiki-without-size etc.)
vff_shoe_month = defaultdict(new_acc)
vff_shoe_channel = defaultdict(new_acc)
vff_shoe_channel_month = defaultdict(lambda: defaultdict(new_acc))
vff_shoe_model = defaultdict(new_acc)
vff_shoe_gender = defaultdict(new_acc)
vff_shoe_total = new_acc()

for r in records:
    store, month, brand = r['store'], r['month'], r['brand']
    amt, qty = r['amount'], r['qty']
    oid = r['order_id']

    store_acc[store]['amount'] += amt
    store_acc[store]['qty'] += qty
    if oid:
        store_acc[store]['orders'].add(oid)

    store_month[store][month]['amount'] += amt
    store_month[store][month]['qty'] += qty
    if oid:
        store_month[store][month]['orders'].add(oid)

    store_brand[store][brand]['amount'] += amt
    store_brand[store][brand]['qty'] += qty

    overall_month[month]['amount'] += amt
    overall_month[month]['qty'] += qty
    if oid:
        overall_month[month]['orders'].add((store, oid))

    overall_brand[brand]['amount'] += amt
    overall_brand[brand]['qty'] += qty

    brand_month[brand][month]['amount'] += amt
    brand_month[brand][month]['qty'] += qty

    model_c = canon_model(r['model'])
    if brand == 'VFF' and model_c:
        vff_model[model_c]['amount'] += amt
        vff_model[model_c]['qty'] += qty

    if model_c:
        model_overall[model_c]['amount'] += amt
        model_overall[model_c]['qty'] += qty
        brand_model[brand][model_c]['amount'] += amt
        brand_model[brand][model_c]['qty'] += qty

    if brand == 'Others' and r['sub']:
        others_sub[r['sub']]['amount'] += amt
        others_sub[r['sub']]['qty'] += qty

    if store == 'Online' and r['channel']:
        online_channel[r['channel']]['amount'] += amt
        online_channel[r['channel']]['qty'] += qty
        online_channel_month[r['channel']][month]['amount'] += amt

    if r['payment']:
        store_payment[store][r['payment']]['amount'] += amt
        store_payment[store][r['payment']]['qty'] += qty
        if store == 'Event':
            event_payment[r['payment']]['amount'] += amt
            event_payment[r['payment']]['qty'] += qty

    if brand == 'VFF' and r.get('is_vff_shoe'):
        vff_shoe_total['amount'] += amt
        vff_shoe_total['qty'] += qty
        vff_shoe_month[month]['amount'] += amt
        vff_shoe_month[month]['qty'] += qty
        ch5 = CHANNEL5.get(store, store)
        vff_shoe_channel[ch5]['amount'] += amt
        vff_shoe_channel[ch5]['qty'] += qty
        vff_shoe_channel_month[ch5][month]['qty'] += qty
        if model_c:
            vff_shoe_model[model_c]['amount'] += amt
            vff_shoe_model[model_c]['qty'] += qty
        g = r.get('gender') or 'Unisex'
        vff_shoe_gender[g]['amount'] += amt
        vff_shoe_gender[g]['qty'] += qty

def ser(acc):
    return {'amount': round(acc['amount'], 2), 'qty': round(acc['qty'], 1),
            'orders': len(acc['orders']) if isinstance(acc['orders'], set) else acc['orders']}

# ---------------------------------------------------------------- build output
out = {}

_total_amount = round(sum(v['amount'] for v in store_acc.values()), 2)
_total_qty = round(sum(v['qty'] for v in store_acc.values()), 1)
_total_orders = sum(len(v['orders']) for v in store_acc.values())
out['kpi'] = {
    'total_amount': _total_amount,
    'total_qty': _total_qty,
    'total_orders': _total_orders,
    'avg_ticket': round(_total_amount / _total_orders, 2) if _total_orders else None,
    'period': '2026-01-01 ~ 2026-06-30',
    # last-year figures are not yet available (2025 H1 data not received) -- kept as an
    # explicit null block so the dashboard's YoY badges stay wired up and light up
    # automatically the moment this is filled in, instead of needing new UI code later.
    'last_year': None,
}

stores_out = []
for store, acc in store_acc.items():
    s = ser(acc)
    s['store'] = store
    s['group'] = STORE_GROUP.get(store, 'other')
    s['avg_ticket'] = round(acc['amount'] / len(acc['orders']), 2) if acc['orders'] else None
    s['monthly'] = {m: ser(store_month[store].get(m, new_acc())) for m in MONTHS}
    s['brand'] = {b: ser(v) for b, v in store_brand[store].items()}
    if store_payment[store]:
        pay = {p: ser(v) for p, v in store_payment[store].items()}
        pay_total = sum(v['amount'] for v in store_payment[store].values())
        s['payment'] = pay
        s['payment_total'] = round(pay_total, 2)
    stores_out.append(s)
stores_out.sort(key=lambda x: -x['amount'])
out['stores'] = stores_out
out['group_label'] = GROUP_LABEL

out['monthly_overall'] = [
    {'month': m, 'amount': round(overall_month[m]['amount'], 2), 'qty': round(overall_month[m]['qty'], 1),
     'orders': len(overall_month[m]['orders'])}
    for m in MONTHS
]

out['brand_overall'] = [
    {'brand': b, **ser(v)} for b, v in sorted(overall_brand.items(), key=lambda x: -x[1]['amount'])
]
out['brand_monthly'] = {
    b: [{'month': m, 'amount': round(brand_month[b][m]['amount'], 2), 'qty': round(brand_month[b][m]['qty'], 1)}
        for m in MONTHS]
    for b in overall_brand.keys()
}

out['vff_models'] = [
    {'model': m, **ser(v)} for m, v in sorted(vff_model.items(), key=lambda x: -x[1]['amount'])
]

_models_sorted = sorted(model_overall.items(), key=lambda x: -x[1]['amount'])
out['model_top10'] = [{'model': m, **ser(v)} for m, v in _models_sorted[:10]]
out['model_bottom10'] = [{'model': m, **ser(v)} for m, v in _models_sorted[-10:][::-1]]
out['model_count'] = len(model_overall)

out['brand_models'] = {
    b: [{'model': m, **ser(v)} for m, v in sorted(models.items(), key=lambda x: -x[1]['amount'])]
    for b, models in brand_model.items()
}

out['others_sub'] = [
    {'brand': b, **ser(v)} for b, v in sorted(others_sub.items(), key=lambda x: -x[1]['amount'])
]

out['online_channel'] = [
    {'channel': c, **ser(v), 'monthly': {m: round(online_channel_month[c].get(m, new_acc())['amount'], 2) for m in MONTHS}}
    for c, v in sorted(online_channel.items(), key=lambda x: -x[1]['amount'])
]

_shoe_models_sorted = sorted(vff_shoe_model.items(), key=lambda x: -x[1]['qty'])
out['vff_shoes'] = {
    'note': 'VFFブランドのうちシューズのみ（ソックス・Furoshiki等の非シューズ商品は除く）。'
            'サイズ表記（W=女性/M=男性/U=ユニセックス）から性別区分を推定',
    'total_qty': round(vff_shoe_total['qty'], 1),
    'total_amount': round(vff_shoe_total['amount'], 2),
    'monthly': [
        {'month': m, 'qty': round(vff_shoe_month[m]['qty'], 1), 'amount': round(vff_shoe_month[m]['amount'], 2)}
        for m in MONTHS
    ],
    'channel_share': [
        {'channel': c, **ser(v)} for c, v in sorted(vff_shoe_channel.items(), key=lambda x: -x[1]['qty'])
    ],
    'model_ranking_by_qty': [{'model': m, **ser(v)} for m, v in _shoe_models_sorted],
    'gender': [
        {'gender': GENDER_LABEL.get(g, g), **ser(v)}
        for g, v in sorted(vff_shoe_gender.items(), key=lambda x: -x[1]['qty'])
    ],
}

event_pay_total = sum(v['amount'] for v in event_payment.values())
out['payment_overall'] = {
    'note': '決済方法データがあるのは「イベント」カテゴリのみ（他の店舗・チャネルには決済方法の記録がありません）',
    'coverage_amount': round(event_pay_total, 2),
    'breakdown': [{'method': p, **ser(v)} for p, v in sorted(event_payment.items(), key=lambda x: -x[1]['amount'])],
}

with open('/tmp/claude-0/-home-user-sales-1st-half-26-dashboard/7c7fe66c-960c-5108-be91-c1dc0972813f/scratchpad/dashboard_data.json', 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, indent=None)

print("KPI:", out['kpi'])
print("Stores:", len(out['stores']))
print("Brand overall:", out['brand_overall'])
print("VFF models:", len(out['vff_models']))
print("Online channels:", [c['channel'] for c in out['online_channel']])
print("Payment coverage amount:", out['payment_overall']['coverage_amount'])
import os
print("Output size (KB):", os.path.getsize('/tmp/claude-0/-home-user-sales-1st-half-26-dashboard/7c7fe66c-960c-5108-be91-c1dc0972813f/scratchpad/dashboard_data.json')/1024)
