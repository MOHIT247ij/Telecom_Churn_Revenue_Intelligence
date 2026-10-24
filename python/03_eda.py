"""
03_eda.py
---------
Exploratory data analysis - churn drivers & segment diagnostics.
Saves charts to outputs/charts/ and a segment churn table to outputs/reports/.
"""
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter
import viz_style as vs

vs.apply()
ROOT = Path(__file__).resolve().parents[1]
PROC, CH, REP = ROOT / "data/processed", ROOT / "outputs/charts", ROOT / "outputs/reports"
CH.mkdir(parents=True, exist_ok=True)

cust = pd.read_csv(PROC / "customers_clean.csv", parse_dates=["join_date", "churn_date"])
tickets = pd.read_csv(PROC / "support_tickets_clean.csv", parse_dates=["ticket_date"])
usage = pd.read_csv(PROC / "network_usage_clean.csv")

# enrich with ticket & network aggregates
t_agg = tickets.groupby("customer_id").agg(ticket_count=("ticket_id", "count"),
                                           avg_csat=("csat_score", "mean"))
n_agg = usage.groupby("customer_id").agg(avg_drop_rate=("call_drop_rate_pct", "mean"),
                                         active_months=("usage_month", "nunique"))
cust = cust.join(t_agg, on="customer_id").join(n_agg, on="customer_id")
cust["ticket_count"] = cust["ticket_count"].fillna(0)
cust["tickets_per_month"] = cust["ticket_count"] / cust["active_months"].clip(lower=1)   # exposure-adjusted
overall = cust["churn_flag"].mean()


def rate_bar(col, fname, title, order=None, horizontal=True):
    g = cust.groupby(col, observed=True)["churn_flag"].agg(["mean", "count"])
    if order is not None:
        g = g.reindex(order)
    elif horizontal:
        g = g.sort_values("mean")
    fig, ax = plt.subplots(figsize=(8, 0.5 * len(g) + 1.6))
    if horizontal:
        bars = ax.barh(g.index.astype(str), g["mean"], color=vs.BLUE, height=0.6)
        ax.axvline(overall, color=vs.INK2, lw=1, ls="--")
        ax.text(overall, len(g) - 0.4, f" avg {overall:.0%}", color=vs.INK2, fontsize=9)
        ax.xaxis.set_major_formatter(PercentFormatter(1, 0))
        ax.grid(axis="y", visible=False)
        for b, v, n in zip(bars, g["mean"], g["count"]):
            ax.text(v + 0.005, b.get_y() + b.get_height() / 2, f"{v:.1%}  (n={n:,})",
                    va="center", fontsize=9, color=vs.INK)
        ax.set_xlim(0, g["mean"].max() * 1.35)
        ax.set_xlabel("Churn rate")
    else:
        bars = ax.bar(g.index.astype(str), g["mean"], color=vs.BLUE, width=0.6)
        ax.axhline(overall, color=vs.INK2, lw=1, ls="--")
        ax.yaxis.set_major_formatter(PercentFormatter(1, 0))
        ax.grid(axis="x", visible=False)
        for b, v in zip(bars, g["mean"]):
            ax.text(b.get_x() + b.get_width() / 2, v + 0.006, f"{v:.1%}", ha="center", fontsize=9)
        ax.set_ylabel("Churn rate")
    ax.set_title(title)
    fig.savefig(CH / fname); plt.close(fig)
    return g


segments = {}
segments["contract_type"] = rate_bar("contract_type", "01_churn_by_contract.png", "Churn rate by contract type")
segments["tenure_band"] = rate_bar("tenure_band", "02_churn_by_tenure.png", "Churn rate by tenure band",
                                   order=["0-6 M", "7-12 M", "13-24 M", "25-48 M", "48+ M"], horizontal=False)
segments["circle"] = rate_bar("circle", "03_churn_by_circle.png", "Churn rate by telecom circle")
segments["payment_method"] = rate_bar("payment_method", "04_churn_by_payment.png", "Churn rate by payment method")
segments["charge_band"] = rate_bar("charge_band", "05_churn_by_charge_band.png", "Churn rate by monthly charge (₹)",
                                   order=["< 300", "300-600", "600-1000", "1000+"], horizontal=False)
cust["ticket_bucket"] = pd.cut(cust["tickets_per_month"], [-0.01, 0.1, 0.25, 0.5, 1.0, 99],
                               labels=["< 0.1", "0.1-0.25", "0.25-0.5", "0.5-1", "1+"])
segments["ticket_bucket"] = rate_bar("ticket_bucket", "06_churn_by_tickets.png",
                                     "Churn rate by support tickets per active month",
                                     order=["< 0.1", "0.1-0.25", "0.25-0.5", "0.5-1", "1+"], horizontal=False)
segments["service_type"] = rate_bar("service_type", "07_churn_by_service.png", "Churn rate by service type")
segments["network_type"] = rate_bar("network_type", "08_churn_by_network.png", "Churn rate by network type")

# monthly churn trend with tariff-hike annotation
ch = cust.dropna(subset=["churn_date"]).copy()
monthly = ch.groupby(ch["churn_date"].dt.to_period("M")).size()
monthly.index = monthly.index.to_timestamp()
fig, ax = plt.subplots(figsize=(10, 4))
ax.plot(monthly.index, monthly.values, color=vs.BLUE, marker="o", ms=4)
ax.axvspan(pd.Timestamp("2024-06-20"), pd.Timestamp("2024-09-25"), color=vs.ORANGE, alpha=0.10, lw=0)
ax.text(pd.Timestamp("2024-06-25"), monthly.max() * 1.12, "July-24 tariff hike\n(+15% mobile)",
        fontsize=9, color=vs.INK)
ax.axvspan(pd.Timestamp("2025-03-20"), pd.Timestamp("2025-05-25"), color=vs.ORANGE, alpha=0.10, lw=0)
ax.text(pd.Timestamp("2025-03-25"), monthly.max() * 1.12, "Competitor\n5G launch", fontsize=9, color=vs.INK)
ax.set_title("Customers churned per month"); ax.set_ylabel("Churned customers")
ax.set_ylim(0, monthly.max() * 1.30)
fig.savefig(CH / "09_monthly_churn_trend.png"); plt.close(fig)

# churn reasons
r = ch["churn_reason"].value_counts().sort_values()
fig, ax = plt.subplots(figsize=(8, 4))
bars = ax.barh(r.index, r.values, color=vs.BLUE, height=0.6)
for b, v in zip(bars, r.values):
    ax.text(v + 5, b.get_y() + b.get_height() / 2, f"{v:,} ({v / r.sum():.0%})", va="center", fontsize=9)
ax.set_xlim(0, r.max() * 1.25); ax.grid(axis="y", visible=False)
ax.set_title("Top churn reasons (exit survey)"); ax.set_xlabel("Churned customers")
fig.savefig(CH / "10_churn_reasons.png"); plt.close(fig)

# network quality: drop rate retained vs churned
fig, ax = plt.subplots(figsize=(8, 4))
bins = np.linspace(0, 8, 41)
ax.hist(cust.loc[cust.churn_flag == 0, "avg_drop_rate"], bins=bins, color=vs.RETAINED, alpha=0.75,
        label="Retained", density=True, edgecolor=vs.SURFACE, linewidth=0.6)
ax.hist(cust.loc[cust.churn_flag == 1, "avg_drop_rate"], bins=bins, color=vs.CHURNED, alpha=0.75,
        label="Churned", density=True, edgecolor=vs.SURFACE, linewidth=0.6)
ax.set_title("Call-drop rate distribution: churned vs retained")
ax.set_xlabel("Average call-drop rate (%)"); ax.set_ylabel("Density"); ax.legend()
fig.savefig(CH / "11_drop_rate_distribution.png"); plt.close(fig)

# correlation with churn
num_cols = ["tenure_months", "monthly_charges", "age", "addon_count", "discount_pct",
            "avg_monthly_data_gb", "tickets_per_month", "avg_csat", "avg_drop_rate", "senior_citizen"]
corr = cust[num_cols + ["churn_flag"]].corr()["churn_flag"].drop("churn_flag").sort_values()
fig, ax = plt.subplots(figsize=(8, 4.5))
colors = [vs.BLUE if v < 0 else vs.ORANGE for v in corr.values]
ax.barh(corr.index, corr.values, color=colors, height=0.6)
ax.axvline(0, color=vs.INK2, lw=0.8); ax.grid(axis="y", visible=False)
for i, v in enumerate(corr.values):
    ax.text(v + (0.005 if v >= 0 else -0.005), i, f"{v:+.2f}", va="center",
            ha="left" if v >= 0 else "right", fontsize=9)
ax.set_xlim(corr.min() - 0.08, corr.max() + 0.08)
ax.set_title("Correlation of numeric features with churn")
ax.set_xlabel("Pearson r  (orange = raises churn, blue = protects)")
fig.savefig(CH / "12_feature_correlation.png"); plt.close(fig)

# segment table export
rows = []
for dim, g in segments.items():
    for k, v in g.iterrows():
        rows.append({"dimension": dim, "segment": k, "customers": int(v["count"]),
                     "churn_rate": round(v["mean"], 4), "lift_vs_avg": round(v["mean"] / overall, 2)})
pd.DataFrame(rows).to_csv(REP / "segment_churn_analysis.csv", index=False)

print(f"Overall churn rate: {overall:.1%}")
print("Highest-risk segments (lift >= 1.3):")
seg = pd.DataFrame(rows)
print(seg[seg.lift_vs_avg >= 1.3].sort_values("lift_vs_avg", ascending=False).to_string(index=False))
