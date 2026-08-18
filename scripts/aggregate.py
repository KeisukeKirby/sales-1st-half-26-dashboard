#!/usr/bin/env python3
"""Aggregate canonical records.json into the JSON payload consumed by the dashboard.

Every dimension is broken down by month (in addition to its H1 total) so the
dashboard can re-slice any figure into an arbitrary period (a single month,
Q1, Q2, or the full half) entirely client-side, without re-running this script.
"""
import json
from collections import defaultdict

records = json.load(open('/tmp/claude-0/-home-user-sales-1st-half-26-dashboard/7c7fe66c-960c-5108-be91-c1dc0972813f/scratchpad/records.json'))
# 2025 and 2024 full-year actuals -- merged in for YoY comparison and the
# Overall tab's yearly-summary panel. Only the Jan-Jun 2025 subset (PREV_MONTHS)
# is used for per-key monthly breakdowns (monthly_out); the rest of both years
# rides along harmlessly and is summed separately below for full-year totals.
records += json.load(open('/tmp/claude-0/-home-user-sales-1st-half-26-dashboard/7c7fe66c-960c-5108-be91-c1dc0972813f/scratchpad/records_2025.json'))
records += json.load(open('/tmp/claude-0/-home-user-sales-1st-half-26-dashboard/7c7fe66c-960c-5108-be91-c1dc0972813f/scratchpad/records_2024.json'))

MONTHS = ['2026-01','2026-02','2026-03','2026-04','2026-05','2026-06']
PREV_MONTHS = ['2025-01','2025-02','2025-03','2025-04','2025-05','2025-06']  # same 6 calendar months, prior year
H1_2024 = [f'2024-{m:02d}' for m in range(1, 7)]  # same 6 calendar months, two years prior
# union used only when serializing per-key monthly breakdowns (monthly_out) -- includes
# H1 2024 too so every store/model/VFF-shoe breakdown can support a 2-year-back
# comparison, not just last year's.
ALL_MONTHS = MONTHS + PREV_MONTHS + H1_2024


# Store -> channel-group mapping, used dashboard-wide (Overall tab, By Store tab,
# and the VFF Shoes tab's channel-share view all share this single scheme now).
# 直営実店舗 is ONLY the two company-run standalone shops; Coollabo and the VFF
# cart are mall corners inside Central properties so they roll into Central百貨店内
# alongside the department-store locations; Siam Discovery and Thaniya each get
# their own dedicated category rather than being lumped into a generic "retail"
# bucket (Thaniya carries no VFF shoe sales at all, but still gets its own
# category for the general store/brand/payment breakdowns).
STORE_GROUP = {
    'K Village': 'directly_operated', 'Paradise Park': 'directly_operated',
    'Central Ladprao 3F (Coollabo)': 'central_dept', 'VFF Cart LP': 'central_dept',
    'Central Chidlom': 'central_dept', 'Central Chidlom Online': 'central_dept',
    'Central World (CDS)': 'central_dept', 'Central Lardprao (Dept.)': 'central_dept',
    'Central Eastville': 'central_dept',
    'Siam Discovery': 'siam_discovery',
    'Thaniya': 'thaniya',
    'Online': 'online', 'Event': 'event',
    'BFT Consignment': 'consignment', 'EDV Consignment': 'consignment',
}
GROUP_LABEL = {
    'directly_operated': '直営実店舗', 'central_dept': 'Central百貨店内', 'online': 'オンライン',
    'event': 'イベント', 'consignment': '委託販売', 'siam_discovery': 'Siam Discovery', 'thaniya': 'Thaniya',
}
GENDER_LABEL = {'Women': '女性', 'Men': '男性', 'Unisex': 'ユニセックス'}

def new_acc():
    return {'amount': 0.0, 'qty': 0.0, 'orders': set()}

def ser(acc):
    return {'amount': round(acc['amount'], 2), 'qty': round(acc['qty'], 1),
            'orders': len(acc['orders']) if isinstance(acc['orders'], set) else acc['orders']}

def monthly_out(acc_by_key_month):
    """{key: {month: acc}} -> {key: {month: {amount,qty,orders}}}, every month present
    (both the current H1 2026 months AND the prior-year H1 2025 months, so the client
    can sum either set with the same sumMonthly() helper to compute YoY for any period)."""
    return {k: {m: ser(months.get(m, new_acc())) for m in ALL_MONTHS} for k, months in acc_by_key_month.items()}

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
vff_shoe_store_month = defaultdict(lambda: defaultdict(new_acc))           # raw store name -> month (individual stores; the dashboard derives the channel-group rollup client-side via STORE_GROUP, same as everywhere else)
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
        add(vff_shoe_store_month[store][month])
        if model_c:
            add(vff_shoe_model_month[model_c][month])
        g = r.get('gender') or 'Unisex'
        add(vff_shoe_gender_month[g][month])

def sum_months(acc_by_month, months=MONTHS):
    total = new_acc()
    for m in months:
        a = acc_by_month.get(m, new_acc())
        total['amount'] += a['amount']
        total['qty'] += a['qty']
        total['orders'] |= a['orders']
    return total

# ---------------------------------------------------------------- build output
out = {'months': MONTHS, 'prev_months': PREV_MONTHS}

# ---- KPI: give the client the monthly series; it derives any period's totals by summing.
out['monthly_overall'] = [
    {'month': m, **ser(overall_month[m])} for m in MONTHS
]
# prior-year (H1 2025) equivalent series, for the summary section's YoY badges.
out['monthly_overall_prev'] = [
    {'month': m, **ser(overall_month[m])} for m in PREV_MONTHS
]
# two-years-back (H1 2024) equivalent series, for the Overall tab's detail
# table (01 全体サマリー) and other 2-year-back comparisons.
out['monthly_overall_2024h1'] = [
    {'month': m, **ser(overall_month[m])} for m in H1_2024
]
_h1_total = sum_months(overall_month)
_h1_prev_total = sum_months(overall_month, PREV_MONTHS)
out['kpi'] = {
    'total_amount': round(_h1_total['amount'], 2),
    'total_qty': round(_h1_total['qty'], 1),
    'total_orders': len(_h1_total['orders']),
    'avg_ticket': round(_h1_total['amount'] / len(_h1_total['orders']), 2) if _h1_total['orders'] else None,
    'period': '2026-01-01 ~ 2026-06-30',
    'last_year': {
        'total_amount': round(_h1_prev_total['amount'], 2),
        'total_qty': round(_h1_prev_total['qty'], 1),
        'total_orders': len(_h1_prev_total['orders']),
        'avg_ticket': round(_h1_prev_total['amount'] / len(_h1_prev_total['orders']), 2) if _h1_prev_total['orders'] else None,
        'period': '2025-01-01 ~ 2025-06-30',
    },
}

# ---- stores
stores_out = []
for store in store_month.keys():
    h1 = sum_months(store_month[store])
    s = ser(h1)
    s['store'] = store
    s['group'] = STORE_GROUP.get(store, 'other')
    s['avg_ticket'] = round(h1['amount'] / len(h1['orders']), 2) if h1['orders'] else None
    s['monthly'] = {m: ser(store_month[store].get(m, new_acc())) for m in ALL_MONTHS}
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
    # H1 2025 / H1 2024 equivalents of the overall total series -- lets the
    # detail table's 売上金額/合計 summary rows compare against prior years,
    # same as store_monthly/model_monthly already can via monthly_out().
    'monthly_prev': [{'month': m, **ser(vff_shoe_by_month[m])} for m in PREV_MONTHS],
    'monthly_2024h1': [{'month': m, **ser(vff_shoe_by_month[m])} for m in H1_2024],
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
