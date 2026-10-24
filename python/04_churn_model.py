"""
04_churn_model.py
-----------------
Churn prediction model + business-driven targeting.

Pipeline
    1. Feature engineering (customer + billing + tickets + network usage)
    2. Train / test split (stratified, 80/20)
    3. Models compared with 5-fold CV: Logistic Regression, Random Forest, Gradient Boosting
    4. Best model -> test metrics, ROC, confusion matrix, permutation importance
    5. Profit-curve threshold: pick the cut-off that maximises retention-campaign ROI
    6. Score ACTIVE customers -> churn probability, risk tier, revenue at risk, next-best action

Outputs
    outputs/reports/model_comparison.csv, feature_importance.csv, profit_curve.csv
    outputs/reports/churn_predictions.csv     (consumed by SQL + Power BI)
    outputs/models/churn_model.pkl
"""
from pathlib import Path
import numpy as np
import pandas as pd
import joblib
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter, FuncFormatter
from sklearn.model_selection import train_test_split, StratifiedKFold, cross_val_score, cross_val_predict
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier, HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.metrics import (roc_auc_score, roc_curve, precision_score, recall_score, f1_score,
                             accuracy_score, confusion_matrix, average_precision_score)
import viz_style as vs

vs.apply()
SEED = 42
# Parallel workers. Default 1 = safe on laptops (Windows spawns a full process per worker,
# which can cause MemoryError). Faster machines: set N_JOBS=4 before running.
import os
N_JOBS = int(os.environ.get("N_JOBS", "1"))
ROOT = Path(__file__).resolve().parents[1]
PROC, CH, REP = ROOT / "data/processed", ROOT / "outputs/charts", ROOT / "outputs/reports"
MOD = ROOT / "outputs/models"; MOD.mkdir(parents=True, exist_ok=True)

# Business assumptions for the retention campaign (documented in README)
OFFER_COST = 300          # ₹ cost per customer contacted (discount / data bonus / call-centre time)
SAVE_RATE = 0.30          # share of true churners retained by the offer
GROSS_MARGIN = 0.40       # telecom EBITDA-style margin on revenue
SAVED_MONTHS = 12         # months of revenue retained when a churner is saved

# ------------------------------------------------------------------ 1. features
cust = pd.read_csv(PROC / "customers_clean.csv", parse_dates=["join_date", "churn_date"])
bill = pd.read_csv(PROC / "billing_clean.csv", parse_dates=["bill_month"])
tick = pd.read_csv(PROC / "support_tickets_clean.csv")
use = pd.read_csv(PROC / "network_usage_clean.csv", parse_dates=["usage_month"])

b = bill[bill.payment_status != "Unpaid"]          # 'Unpaid' only happens at exit -> leakage, excluded
b_agg = b.groupby("customer_id").agg(
    late_payment_ratio=("payment_status", lambda s: (s == "Paid Late").mean()),
    avg_days_late=("days_late", "mean"),
    bill_volatility=("amount_billed", "std"))

t_agg = tick.groupby("customer_id").agg(
    ticket_count=("ticket_id", "count"), avg_csat=("csat_score", "mean"),
    avg_resolution_hrs=("resolution_hours", "mean"),
    unresolved_tickets=("resolved_flag", lambda s: (s == 0).sum()),
    network_tickets=("category", lambda s: s.isin(["Network / Coverage", "Slow Data Speed",
                                                   "Broadband Outage"]).sum()))

use = use.sort_values(["customer_id", "usage_month"])
def trend(g):
    if len(g) < 4:
        return 1.0
    return g["data_used_gb"].tail(2).mean() / max(g["data_used_gb"].head(len(g) - 2).mean(), 0.1)
u_agg = use.groupby("customer_id").agg(avg_drop_rate=("call_drop_rate_pct", "mean"),
                                       avg_speed_mbps=("avg_speed_mbps", "mean"),
                                       avg_voice_min=("voice_minutes", "mean"),
                                       active_months=("usage_month", "nunique"))
u_agg["usage_trend"] = use.groupby("customer_id")[["data_used_gb"]].apply(trend)

df = cust.join(b_agg, on="customer_id").join(t_agg, on="customer_id").join(u_agg, on="customer_id")
df["ticket_count"] = df["ticket_count"].fillna(0)
df["unresolved_tickets"] = df["unresolved_tickets"].fillna(0)
df["network_tickets"] = df["network_tickets"].fillna(0)
df["avg_csat"] = df["avg_csat"].fillna(df["avg_csat"].median())
df["avg_resolution_hrs"] = df["avg_resolution_hrs"].fillna(0)
df["bill_volatility"] = df["bill_volatility"].fillna(0)
df["tickets_per_month"] = df["ticket_count"] / df["active_months"].clip(lower=1)
df["charge_per_gb"] = df["monthly_charges"] / df["avg_monthly_data_gb"].clip(lower=0.5)
df["is_new_customer"] = (df["tenure_months"] <= 6).astype(int)

NUM = ["age", "tenure_months", "monthly_charges", "discount_pct", "addon_count", "avg_monthly_data_gb",
       "late_payment_ratio", "avg_days_late", "tickets_per_month", "avg_csat",
       "avg_resolution_hrs", "unresolved_tickets", "network_tickets", "avg_drop_rate", "avg_speed_mbps",
       "avg_voice_min", "usage_trend", "charge_per_gb", "is_new_customer", "senior_citizen"]
CAT = ["gender", "partner", "dependents", "circle", "city_tier", "acquisition_channel", "service_type",
       "plan_tier", "network_type", "contract_type", "payment_method", "paperless_billing", "ott_bundle",
       "device_protection", "intl_roaming", "priority_support", "multi_line"]
X, y = df[NUM + CAT], df["churn_flag"]
df[["customer_id"] + NUM + CAT + ["churn_flag"]].to_csv(PROC / "model_features.csv", index=False)

X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, stratify=y, random_state=SEED)

def prep(scale):
    return ColumnTransformer([
        ("num", StandardScaler() if scale else "passthrough", NUM),
        ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), CAT)])

models = {
    "Logistic Regression": Pipeline([("prep", prep(True)),
                                     ("clf", LogisticRegression(max_iter=2000, C=0.5,
                                                                class_weight="balanced"))]),
    "Random Forest": Pipeline([("prep", prep(False)),
                               ("clf", RandomForestClassifier(n_estimators=400, max_depth=12,
                                                              min_samples_leaf=5, class_weight="balanced",
                                                              n_jobs=N_JOBS, random_state=SEED))]),
    "Gradient Boosting": Pipeline([("prep", prep(False)),
                                   ("clf", HistGradientBoostingClassifier(learning_rate=0.05, max_iter=400,
                                                                          max_leaf_nodes=31,
                                                                          l2_regularization=1.0,
                                                                          random_state=SEED))]),
}

# ------------------------------------------------------------------ 2-3. compare
cv = StratifiedKFold(5, shuffle=True, random_state=SEED)
rows, probs = [], {}
for name, m in models.items():
    cv_auc = cross_val_score(m, X_tr, y_tr, cv=cv, scoring="roc_auc", n_jobs=N_JOBS)
    m.fit(X_tr, y_tr)
    p = m.predict_proba(X_te)[:, 1]; pred = (p >= 0.5).astype(int)
    probs[name] = p
    rows.append({"model": name, "cv_auc_mean": cv_auc.mean(), "cv_auc_std": cv_auc.std(),
                 "test_auc": roc_auc_score(y_te, p), "test_pr_auc": average_precision_score(y_te, p),
                 "accuracy": accuracy_score(y_te, pred), "precision": precision_score(y_te, pred),
                 "recall": recall_score(y_te, pred), "f1": f1_score(y_te, pred)})
    print(f"{name:<20} CV AUC {cv_auc.mean():.3f} ± {cv_auc.std():.3f} | test AUC {rows[-1]['test_auc']:.3f}")
comp = pd.DataFrame(rows).round(4).sort_values("test_auc", ascending=False)
comp.to_csv(REP / "model_comparison.csv", index=False)
best_name = comp.iloc[0]["model"]; best = models[best_name]; p_best = probs[best_name]
print(f"\nBest model: {best_name}")

# ROC chart
fig, ax = plt.subplots(figsize=(6.5, 5.5))
for i, (name, p) in enumerate(probs.items()):
    fpr, tpr, _ = roc_curve(y_te, p)
    ax.plot(fpr, tpr, color=vs.PALETTE[i], label=f"{name} (AUC {roc_auc_score(y_te, p):.3f})")
ax.plot([0, 1], [0, 1], color=vs.INK2, lw=1, ls="--")
ax.set_xlabel("False positive rate"); ax.set_ylabel("True positive rate")
ax.set_title("ROC curve - model comparison (test set)"); ax.legend(loc="lower right")
fig.savefig(CH / "13_roc_curves.png"); plt.close(fig)

# ------------------------------------------------------------------ 5. profit-curve threshold
mc_te = X_te["monthly_charges"].values
value_saved = mc_te * SAVED_MONTHS * GROSS_MARGIN * SAVE_RATE
pc = []
for t in np.arange(0.05, 0.96, 0.01):
    tgt = p_best >= t
    tp = tgt & (y_te.values == 1)
    net = value_saved[tp].sum() - OFFER_COST * tgt.sum()
    pc.append({"threshold": round(t, 2), "customers_targeted": int(tgt.sum()), "churners_caught": int(tp.sum()),
               "precision": tp.sum() / max(tgt.sum(), 1), "recall": tp.sum() / y_te.sum(),
               "campaign_cost": OFFER_COST * tgt.sum(), "revenue_saved": value_saved[tp].sum(),
               "net_benefit": net})
pc = pd.DataFrame(pc)
pc.to_csv(REP / "profit_curve.csv", index=False)
best_t = float(pc.loc[pc.net_benefit.idxmax(), "threshold"])
print(f"Profit-optimal threshold: {best_t:.2f}  (net benefit on test set ₹{pc.net_benefit.max():,.0f})")

fig, ax = plt.subplots(figsize=(8, 4))
ax.plot(pc.threshold, pc.net_benefit, color=vs.BLUE)
ax.axvline(best_t, color=vs.ORANGE, lw=1.2, ls="--")
ax.text(best_t + 0.01, pc.net_benefit.max() * 0.92, f"optimal cut-off {best_t:.2f}", color=vs.INK, fontsize=9)
ax.axhline(0, color=vs.INK2, lw=0.8)
ax.yaxis.set_major_formatter(FuncFormatter(vs.inr))
ax.set_xlabel("Churn-probability threshold for targeting")
ax.set_ylabel("Net campaign benefit (test set)")
ax.set_title("Retention campaign profit curve")
fig.savefig(CH / "14_profit_curve.png"); plt.close(fig)

# confusion matrix at optimal threshold
pred_t = (p_best >= best_t).astype(int)
cm = confusion_matrix(y_te, pred_t)
fig, ax = plt.subplots(figsize=(5, 4.3))
ax.imshow(cm, cmap=vs.SEQ_CMAP); ax.grid(False)
for (i, j), v in np.ndenumerate(cm):
    ax.text(j, i, f"{v:,}", ha="center", va="center", fontsize=13,
            color="white" if v > cm.max() / 2 else vs.INK)
ax.set_xticks([0, 1], ["Pred: Stay", "Pred: Churn"]); ax.set_yticks([0, 1], ["Actual: Stay", "Actual: Churn"])
ax.set_title(f"Confusion matrix @ {best_t:.2f}")
fig.savefig(CH / "15_confusion_matrix.png"); plt.close(fig)
metrics_t = {"model": best_name, "threshold": best_t, "accuracy": accuracy_score(y_te, pred_t),
             "precision": precision_score(y_te, pred_t), "recall": recall_score(y_te, pred_t),
             "f1": f1_score(y_te, pred_t), "roc_auc": roc_auc_score(y_te, p_best)}
pd.DataFrame([metrics_t]).round(4).to_csv(REP / "final_model_metrics.csv", index=False)

# ------------------------------------------------------------------ 4. permutation importance
pi = permutation_importance(best, X_te, y_te, scoring="roc_auc", n_repeats=8, random_state=SEED, n_jobs=N_JOBS)
imp = pd.DataFrame({"feature": X_te.columns, "importance": pi.importances_mean, "std": pi.importances_std}) \
        .sort_values("importance", ascending=False)
imp.round(5).to_csv(REP / "feature_importance.csv", index=False)
top = imp.head(15).iloc[::-1]
fig, ax = plt.subplots(figsize=(8, 5.5))
ax.barh(top.feature, top.importance, color=vs.BLUE, height=0.6, xerr=top["std"],
        error_kw={"ecolor": vs.INK2, "lw": 0.8})
ax.grid(axis="y", visible=False)
ax.set_xlabel("Drop in ROC-AUC when feature is shuffled")
ax.set_title(f"Top churn drivers - permutation importance ({best_name})")
fig.savefig(CH / "16_feature_importance.png"); plt.close(fig)

# ------------------------------------------------------------------ 6. score active base
# Out-of-fold scoring: every customer is scored by a model that never saw them in training,
# so current (active) customers get honest, non-memorised probabilities.
df["oof_prob"] = cross_val_predict(best, X, y, cv=cv, method="predict_proba", n_jobs=N_JOBS)[:, 1]
best.fit(X, y)                                         # production model refit on full history
joblib.dump({"model": best, "threshold": best_t, "features": NUM + CAT}, MOD / "churn_model.pkl")
active = df[df.churn_flag == 0].copy()
active["churn_probability"] = active["oof_prob"].round(4)
hi_cut, med_cut = max(best_t + 0.20, 0.55), best_t   # GB is unweighted -> well-calibrated probs
active["risk_tier"] = np.select([active.churn_probability >= hi_cut, active.churn_probability >= med_cut],
                                ["High", "Medium"], "Low")
active["annual_revenue"] = (active.monthly_charges * 12).round(2)
active["revenue_at_risk"] = (active.annual_revenue * active.churn_probability).round(2)
exp_life = (1 / active.churn_probability.clip(0.02, 0.95)).clip(upper=60)   # months, capped at 5 yrs
active["predicted_clv"] = (active.monthly_charges * GROSS_MARGIN * exp_life * 12 / 12).round(2)

def next_best_action(r):
    if r.risk_tier == "Low":
        return "Upsell / Loyalty Rewards"
    if r.avg_drop_rate > 3 or r.network_tickets >= 3:
        return "Network Escalation + Data Bonus"
    if r.avg_csat < 3.2 or r.unresolved_tickets > 0:
        return "Priority Care Callback"
    if r.contract_type in ("Month-to-Month", "Prepaid (No Contract)"):
        return "Lock-in Offer: 12M Contract @10% Off"
    if r.monthly_charges > 1000:
        return "Plan Right-sizing"
    return "Personalised Retention Discount"
active["next_best_action"] = active.apply(next_best_action, axis=1)

out_cols = ["customer_id", "circle", "city", "service_type", "plan_name", "contract_type", "tenure_months",
            "monthly_charges", "avg_drop_rate", "tickets_per_month", "avg_csat", "late_payment_ratio",
            "churn_probability", "risk_tier", "annual_revenue", "revenue_at_risk", "predicted_clv",
            "next_best_action"]
active[out_cols].round(4).sort_values("churn_probability", ascending=False) \
      .to_csv(REP / "churn_predictions.csv", index=False)

summ = active.groupby("risk_tier").agg(customers=("customer_id", "count"),
                                       revenue_at_risk=("revenue_at_risk", "sum"))
print("\nActive base risk summary:\n", summ.round(0).to_string())
print(f"\nTotal annual revenue at risk: ₹{active.revenue_at_risk.sum():,.0f}")
