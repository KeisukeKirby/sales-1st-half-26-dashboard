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

def new_acc():
    return {'amount': 0.0, 'qty': 0.0, 'orders': set()}

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

    if brand == 'VFF' and r['model']:
        vff_model[r['model']]['amount'] += amt
        vff_model[r['model']]['qty'] += qty

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

def ser(acc):
    return {'amount': round(acc['amount'], 2), 'qty': round(acc['qty'], 1),
            'orders': len(acc['orders']) if isinstance(acc['orders'], set) else acc['orders']}

# ---------------------------------------------------------------- build output
out = {}

out['kpi'] = {
    'total_amount': round(sum(v['amount'] for v in store_acc.values()), 2),
    'total_qty': round(sum(v['qty'] for v in store_acc.values()), 1),
    'total_orders': sum(len(v['orders']) for v in store_acc.values()),
    'period': '2026-01-01 ~ 2026-06-30',
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

out['others_sub'] = [
    {'brand': b, **ser(v)} for b, v in sorted(others_sub.items(), key=lambda x: -x[1]['amount'])
]

out['online_channel'] = [
    {'channel': c, **ser(v), 'monthly': {m: round(online_channel_month[c].get(m, new_acc())['amount'], 2) for m in MONTHS}}
    for c, v in sorted(online_channel.items(), key=lambda x: -x[1]['amount'])
]

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
