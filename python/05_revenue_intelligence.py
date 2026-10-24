"""
05_revenue_intelligence.py
--------------------------
Revenue analytics layer: MRR, ARPU, subscriber movement, revenue churn,
collection efficiency, cohort retention, CLV by segment, Pareto & revenue-at-risk.

Outputs (outputs/reports/): monthly_kpis.csv, cohort_retention.csv, clv_by_segment.csv,
                            revenue_at_risk_by_circle.csv
Charts  (outputs/charts/) : 17-23
"""
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter, PercentFormatter
import viz_style as vs

vs.apply()
ROOT = Path(__file__).resolve().parents[1]
PROC, CH, REP = ROOT / "data/processed", ROOT / "outputs/charts", ROOT / "outputs/reports"
GROSS_MARGIN = 0.40

cust = pd.read_csv(PROC / "customers_clean.csv", parse_dates=["join_date", "churn_date", "cohort_month"])
bill = pd.read_csv(PROC / "billing_clean.csv", parse_dates=["bill_month"])
pred = pd.read_csv(REP / "churn_predictions.csv")
bill = bill.merge(cust[["customer_id", "service_type", "circle", "monthly_charges"]], on="customer_id")

# ------------------------------------------------------------------ monthly KPIs
months = sorted(bill.bill_month.unique())
cust["churn_month"] = cust.churn_date.dt.to_period("M").dt.to_timestamp()
cust["join_month"] = cust.join_date.dt.to_period("M").dt.to_timestamp()
rows = []
for m in months:
    m = pd.Timestamp(m)
    b = bill[bill.bill_month == m]
    opening = ((cust.join_month < m) & (cust.churn_month.isna() | (cust.churn_month >= m))).sum()
    new = (cust.join_month == m).sum()
    churned = (cust.churn_month == m).sum()
    rows.append({
        "month": m.date(), "opening_subscribers": opening, "new_subscribers": new,
        "churned_subscribers": churned, "closing_subscribers": opening + new - churned,
        "churn_rate": churned / max(opening, 1),
        "mrr": b.amount_billed.sum(), "collected": b.amount_paid.sum(),
        "collection_efficiency": b.amount_paid.sum() / b.amount_billed.sum(),
        "late_payment_rate": (b.payment_status == "Paid Late").mean(),
        "billed_subscribers": b.customer_id.nunique(),
        "churned_mrr": cust.loc[cust.churn_month == m, "monthly_charges"].sum(),
        "new_mrr": cust.loc[cust.join_month == m, "monthly_charges"].sum(),
    })
k = pd.DataFrame(rows)
k["arpu"] = k.mrr / k.billed_subscribers
k["mrr_growth_pct"] = k.mrr.pct_change()
k["net_subscriber_adds"] = k.new_subscribers - k.churned_subscribers
k["cumulative_revenue_lost"] = k.churned_mrr.cumsum()
k.round(4).to_csv(REP / "monthly_kpis.csv", index=False)
k["month"] = pd.to_datetime(k["month"])

# Chart 17: MRR trend
fig, ax = plt.subplots(figsize=(10, 4))
ax.plot(k.month, k.mrr, color=vs.BLUE, marker="o", ms=4, label="Billed (MRR)")
ax.plot(k.month, k.collected, color=vs.AQUA, marker="o", ms=4, label="Collected")
ax.yaxis.set_major_formatter(FuncFormatter(vs.inr)); ax.legend(loc="upper left")
ax.set_ylim(0, k.mrr.max() * 1.15)
ax.set_title("Monthly recurring revenue - billed vs collected")
fig.savefig(CH / "17_mrr_trend.png"); plt.close(fig)

# Chart 18: ARPU trend (separate chart - never dual axis)
fig, ax = plt.subplots(figsize=(10, 3.6))
ax.plot(k.month, k.arpu, color=vs.BLUE, marker="o", ms=4)
ax.axvline(pd.Timestamp("2024-07-01"), color=vs.ORANGE, lw=1, ls="--")
ax.text(pd.Timestamp("2024-07-10"), k.arpu.min() * 1.005, "tariff hike", fontsize=9, color=vs.INK)
ax.yaxis.set_major_formatter(FuncFormatter(lambda x, _: f"₹{x:.0f}"))
ax.set_title("ARPU (average revenue per user) per month")
fig.savefig(CH / "18_arpu_trend.png"); plt.close(fig)

# Chart 19: subscriber movement
fig, ax = plt.subplots(figsize=(10, 4))
w = 12
ax.bar(k.month - pd.Timedelta(days=7), k.new_subscribers, width=w, color=vs.BLUE, label="New")
ax.bar(k.month + pd.Timedelta(days=7), -k.churned_subscribers, width=w, color=vs.ORANGE, label="Churned")
ax.plot(k.month, k.net_subscriber_adds, color=vs.INK, lw=1.5, marker="o", ms=3, label="Net adds")
ax.axhline(0, color=vs.INK2, lw=0.8)
ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.08), ncol=3)
ax.set_title("Subscriber movement - gross adds vs churn")
fig.savefig(CH / "19_subscriber_movement.png"); plt.close(fig)

# ------------------------------------------------------------------ cohort retention
coh = cust[cust.join_month >= "2024-01-01"].copy()
coh["cohort_q"] = coh.join_month.dt.to_period("Q").astype(str)
horizon = list(range(0, 22, 3))
ret = {}
for q, g in coh.groupby("cohort_q"):
    start = g.join_month.min()
    vals = []
    for h in horizon:
        if start + pd.DateOffset(months=h) > pd.Timestamp("2025-12-01"):
            vals.append(np.nan); continue
        alive = g.churn_month.isna() | (g.churn_month > g.join_month + pd.DateOffset(months=h))
        vals.append(alive.mean())
    ret[q] = vals
ret = pd.DataFrame(ret, index=[f"M{h}" for h in horizon]).T
ret.round(4).to_csv(REP / "cohort_retention.csv")
fig, ax = plt.subplots(figsize=(9, 4.5))
im = ax.imshow(ret.values, cmap=vs.SEQ_CMAP, vmin=0.4, vmax=1, aspect="auto"); ax.grid(False)
ax.set_xticks(range(len(horizon)), ret.columns); ax.set_yticks(range(len(ret)), ret.index)
for (i, j), v in np.ndenumerate(ret.values):
    if not np.isnan(v):
        ax.text(j, i, f"{v:.0%}", ha="center", va="center", fontsize=8.5,
                color="white" if v > 0.75 else vs.INK)
ax.set_xlabel("Months since joining"); ax.set_title("Cohort retention - quarterly acquisition cohorts")
fig.colorbar(im, ax=ax, format=PercentFormatter(1, 0), shrink=0.8)
fig.savefig(CH / "20_cohort_retention.png"); plt.close(fig)

# ------------------------------------------------------------------ CLV by segment
# monthly churn hazard per segment = churners / customer-months of exposure
exp = bill.groupby("customer_id").size().rename("exposure_months")
cust = cust.join(exp, on="customer_id")
seg = cust.groupby(["service_type", "contract_type"]).agg(
    customers=("customer_id", "count"), churners=("churn_flag", "sum"),
    exposure=("exposure_months", "sum"), arpu=("monthly_charges", "mean")).reset_index()
seg["monthly_churn_rate"] = seg.churners / seg.exposure
seg["expected_lifetime_m"] = (1 / seg.monthly_churn_rate).clip(upper=120)
seg["clv"] = seg.arpu * GROSS_MARGIN * seg.expected_lifetime_m
seg.round(4).sort_values("clv", ascending=False).to_csv(REP / "clv_by_segment.csv", index=False)
s = seg.sort_values("clv"); s["label"] = s.service_type + " | " + s.contract_type
fig, ax = plt.subplots(figsize=(9, 4.8))
bars = ax.barh(s.label, s.clv, color=vs.BLUE, height=0.6)
for b_, v in zip(bars, s.clv):
    ax.text(v, b_.get_y() + b_.get_height() / 2, f"  {vs.inr(v)}", va="center", fontsize=9)
ax.xaxis.set_major_formatter(FuncFormatter(vs.inr)); ax.grid(axis="y", visible=False)
ax.set_xlim(0, s.clv.max() * 1.18)
ax.set_title("Customer lifetime value (gross margin) by segment")
fig.savefig(CH / "21_clv_by_segment.png"); plt.close(fig)

# ------------------------------------------------------------------ Pareto
rev = bill.groupby("customer_id").amount_billed.sum().sort_values(ascending=False)
cum = rev.cumsum() / rev.sum()
top20_share = cum.iloc[int(len(cum) * 0.2) - 1]
fig, ax = plt.subplots(figsize=(8, 4))
ax.plot(np.arange(1, len(cum) + 1) / len(cum), cum.values, color=vs.BLUE)
ax.axvline(0.2, color=vs.INK2, lw=1, ls="--"); ax.axhline(top20_share, color=vs.INK2, lw=1, ls="--")
ax.text(0.22, top20_share - 0.08, f"Top 20% customers = {top20_share:.0%} of revenue", fontsize=9)
ax.xaxis.set_major_formatter(PercentFormatter(1, 0)); ax.yaxis.set_major_formatter(PercentFormatter(1, 0))
ax.set_xlabel("Share of customers (ranked by revenue)"); ax.set_ylabel("Cumulative revenue share")
ax.set_title("Revenue concentration (Pareto)")
fig.savefig(CH / "22_revenue_pareto.png"); plt.close(fig)

# ------------------------------------------------------------------ revenue at risk by circle × tier
rar = pred.pivot_table(index="circle", columns="risk_tier", values="revenue_at_risk", aggfunc="sum").fillna(0)
rar = rar[[c for c in ["High", "Medium", "Low"] if c in rar.columns]]
rar["Total"] = rar.sum(axis=1); rar = rar.sort_values("Total")
rar.round(0).to_csv(REP / "revenue_at_risk_by_circle.csv")
fig, ax = plt.subplots(figsize=(9, 4.5))
left = np.zeros(len(rar))
tier_col = {"High": vs.ORANGE, "Medium": vs.YELLOW, "Low": vs.BLUE}
for t in ["High", "Medium", "Low"]:
    if t in rar:
        ax.barh(rar.index, rar[t], left=left, color=tier_col[t], height=0.6, label=f"{t} risk",
                edgecolor=vs.SURFACE, linewidth=2)
        left += rar[t].values
for i, v in enumerate(rar.Total):
    ax.text(v, i, f"  {vs.inr(v)}", va="center", fontsize=9)
ax.xaxis.set_major_formatter(FuncFormatter(vs.inr)); ax.grid(axis="y", visible=False)
ax.set_xlim(0, rar.Total.max() * 1.2); ax.legend(loc="lower right")
ax.set_title("Annual revenue at risk by circle (active customers)")
fig.savefig(CH / "23_revenue_at_risk_by_circle.png"); plt.close(fig)

# ------------------------------------------------------------------ headline numbers
total_rev = bill.amount_billed.sum()
print(f"Total billed revenue (24 M)    : ₹{total_rev:,.0f}")
print(f"MRR Jan-24 -> Dec-25           : ₹{k.mrr.iloc[0]:,.0f} -> ₹{k.mrr.iloc[-1]:,.0f}")
print(f"ARPU Jan-24 -> Dec-25          : ₹{k.arpu.iloc[0]:.0f} -> ₹{k.arpu.iloc[-1]:.0f}")
print(f"Avg monthly churn rate         : {k.churn_rate.mean():.2%}")
print(f"Monthly MRR lost to churn (sum): ₹{k.churned_mrr.sum():,.0f}")
print(f"Collection efficiency          : {bill.amount_paid.sum() / total_rev:.2%}")
print(f"Top-20% revenue share          : {top20_share:.1%}")
print(f"Revenue at risk (active, 12 M) : ₹{pred.revenue_at_risk.sum():,.0f}")
