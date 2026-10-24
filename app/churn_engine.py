"""
churn_engine.py
---------------
Scoring + explainability engine used by the Streamlit app.

    prepare(df)   -> clean any uploaded customer CSV into model-ready features
                     (missing columns are filled with a 'typical customer' default)
    score(X)      -> churn probability, risk tier, revenue at risk, next-best action
    explain(X)    -> per-customer reason codes: how much each driver adds to / removes
                     from churn risk versus a typical retained customer

Explainability method (model-agnostic, no extra library):
    for each driver f:  contribution_f = P(churn | x) - P(churn | x with f set to baseline)
    baseline = median / most common value among RETAINED customers.
    Positive contribution = this attribute pushes the customer towards churn.
"""
from pathlib import Path
import re
import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = ROOT / "outputs/models/churn_model.pkl"
FEATURES_PATH = ROOT / "data/processed/model_features.csv"

# interpretable drivers: key -> (features swapped together, label, format of primary feature, direction)
# direction: +1 = higher value is riskier, -1 = lower value is riskier, 0 = categorical.
# Correlated features are swapped as one group so the model never sees an impossible combination,
# and a numeric driver is only reported as a RISK reason when its value is on the risky side.
DRIVERS = {
    "contract_type": (["contract_type"], "Contract type", "{}", 0),
    "tenure_months": (["tenure_months", "is_new_customer"], "Tenure", "{:.0f} months", -1),
    "monthly_charges": (["monthly_charges", "charge_per_gb"], "Monthly charges", "₹{:,.0f}", +1),
    "tickets_per_month": (["tickets_per_month", "network_tickets", "unresolved_tickets", "avg_resolution_hrs"],
                          "Support tickets / month", "{:.2f}", +1),
    "avg_csat": (["avg_csat"], "Customer satisfaction (CSAT)", "{:.1f} / 5", -1),
    "avg_drop_rate": (["avg_drop_rate", "avg_speed_mbps"], "Call-drop rate", "{:.1f}%", +1),
    "late_payment_ratio": (["late_payment_ratio", "avg_days_late"], "Late payments", "{:.0%} of bills", +1),
    "usage_trend": (["usage_trend", "avg_voice_min"], "Recent data usage vs normal", "{:.0%}", -1),
    "payment_method": (["payment_method"], "Payment method", "{}", 0),
    "service_type": (["service_type", "plan_tier", "network_type"], "Service type", "{}", 0),
    "circle": (["circle", "city_tier"], "Circle", "{}", 0),
    "acquisition_channel": (["acquisition_channel"], "Acquisition channel", "{}", 0),
    "priority_support": (["priority_support", "addon_count"], "Priority support", "{}", 0),
}

# common alternative column names people use in their own files
ALIASES = {
    "customerid": "customer_id", "cust_id": "customer_id", "id": "customer_id",
    "tenure": "tenure_months", "monthlycharges": "monthly_charges", "monthly_charge": "monthly_charges",
    "contract": "contract_type", "paymentmethod": "payment_method", "payment": "payment_method",
    "csat": "avg_csat", "csat_score": "avg_csat", "drop_rate": "avg_drop_rate", "call_drop_rate": "avg_drop_rate",
    "region": "circle", "state": "circle", "service": "service_type", "churned": "churn", "exited": "churn",
    "data_gb": "avg_monthly_data_gb", "avg_data_gb": "avg_monthly_data_gb",
}


class ChurnEngine:
    def __init__(self, model_path=MODEL_PATH, features_path=FEATURES_PATH):
        b = joblib.load(model_path)
        self.model, self.threshold, self.features = b["model"], float(b["threshold"]), b["features"]
        self.hi_cut = max(self.threshold + 0.20, 0.55)
        ref = pd.read_csv(features_path)
        self.num = [c for c in self.features if pd.api.types.is_numeric_dtype(ref[c])]
        self.cat = [c for c in self.features if c not in self.num]
        healthy = ref[ref.churn_flag == 0] if "churn_flag" in ref else ref
        self.baseline = {c: (healthy[c].median() if c in self.num else healthy[c].mode().iat[0])
                         for c in self.features}
        self.categories = {c: sorted(ref[c].dropna().unique().tolist()) for c in self.cat}
        self.reference = ref

    # ---------------------------------------------------------------- prepare
    @staticmethod
    def _norm(col):
        c = re.sub(r"[^0-9a-zA-Z]+", "_", str(col)).strip("_").lower()
        return ALIASES.get(c.replace("_", ""), ALIASES.get(c, c))

    def prepare(self, raw: pd.DataFrame):
        """Return (model-ready X, display frame, info dict)."""
        df = raw.copy()
        df.columns = [self._norm(c) for c in df.columns]
        df = df.loc[:, ~df.columns.duplicated()]
        info = {"rows": len(df), "provided": [], "defaulted": [], "derived": []}

        if "customer_id" not in df:
            df["customer_id"] = [f"UPL{i + 1:06d}" for i in range(len(df))]
            info["derived"].append("customer_id")

        # derived helpers if the raw counts are given
        if "tickets_per_month" not in df and "ticket_count" in df:
            months = df["active_months"] if "active_months" in df else df.get("tenure_months", 12)
            df["tickets_per_month"] = pd.to_numeric(df["ticket_count"], errors="coerce") / \
                pd.to_numeric(months, errors="coerce").clip(lower=1)
            info["derived"].append("tickets_per_month")
        for c in self.num:
            if c in df:
                df[c] = pd.to_numeric(df[c], errors="coerce")
        if "tenure_months" in df and "is_new_customer" not in df:
            df["is_new_customer"] = (df["tenure_months"] <= 6).astype(int)
            info["derived"].append("is_new_customer")
        if "monthly_charges" in df and "charge_per_gb" not in df:
            gb = df["avg_monthly_data_gb"] if "avg_monthly_data_gb" in df else self.baseline["avg_monthly_data_gb"]
            df["charge_per_gb"] = df["monthly_charges"] / pd.Series(gb, index=df.index).clip(lower=0.5)
            info["derived"].append("charge_per_gb")
        if "senior_citizen" not in df and "age" in df:
            df["senior_citizen"] = (df["age"] >= 60).astype(int)
            info["derived"].append("senior_citizen")

        for c in self.features:
            if c in df and c not in info["derived"]:
                info["provided"].append(c)
            if c not in df:
                df[c] = self.baseline[c]
                info["defaulted"].append(c)
            else:
                df[c] = df[c].fillna(self.baseline[c])
        for c in self.cat:
            df[c] = df[c].astype(str).str.strip()

        # actual churn label if the user has it
        if "churn" in df and "churn_flag" not in df:
            df["churn_flag"] = df["churn"].astype(str).str.strip().str.lower().isin(["1", "yes", "true", "y"]).astype(int)
        if "churn_flag" in df:
            df["churn_flag"] = pd.to_numeric(df["churn_flag"], errors="coerce").fillna(0).astype(int)

        # display bands
        df["tenure_band"] = pd.cut(df["tenure_months"], [-1, 6, 12, 24, 48, 9999],
                                   labels=["0-6 M", "7-12 M", "13-24 M", "25-48 M", "48+ M"]).astype(str)
        df["charge_band"] = pd.cut(df["monthly_charges"], [-1, 300, 600, 1000, 1e9],
                                   labels=["< 300", "300-600", "600-1000", "1000+"]).astype(str)
        info["coverage"] = len(info["provided"]) / len(self.features)
        return df[self.features], df, info

    # ---------------------------------------------------------------- score
    def predict(self, X):
        return self.model.predict_proba(X[self.features])[:, 1]

    def tier(self, p):
        return np.select([p >= self.hi_cut, p >= self.threshold], ["High", "Medium"], "Low")

    @staticmethod
    def action(r):
        if r["risk_tier"] == "Low":
            return "Upsell / Loyalty Rewards"
        if r["avg_drop_rate"] > 3 or r["network_tickets"] >= 3:
            return "Network Escalation + Data Bonus"
        if r["avg_csat"] < 3.2 or r["unresolved_tickets"] > 0:
            return "Priority Care Callback"
        if r["contract_type"] in ("Month-to-Month", "Prepaid (No Contract)"):
            return "Lock-in Offer: 12M Contract @10% Off"
        if r["monthly_charges"] > 1000:
            return "Plan Right-sizing"
        return "Personalised Retention Discount"

    def score(self, X, prob=None):
        out = X.copy()
        out["churn_probability"] = self.predict(X) if prob is None else np.asarray(prob)
        out["risk_tier"] = self.tier(out["churn_probability"].values)
        out["annual_revenue"] = out["monthly_charges"] * 12
        out["revenue_at_risk"] = out["annual_revenue"] * out["churn_probability"]
        out["next_best_action"] = out.apply(self.action, axis=1)
        return out

    # ---------------------------------------------------------------- explain
    def _drivers(self):
        return {k: ([f for f in v[0] if f in self.features],) + v[1:] for k, v in DRIVERS.items()
                if v[0][0] in self.features}

    def _swap(self, X, feats):
        Z = X.copy()
        for f in feats:
            Z[f] = self.baseline[f]
        return Z

    def contributions(self, X):
        """DataFrame (rows x drivers) of churn-probability contributions vs a typical retained customer."""
        X = X[self.features].reset_index(drop=True)
        drv = self._drivers()
        p = self.predict(X)
        stacked = pd.concat([self._swap(X, v[0]) for v in drv.values()], ignore_index=True)
        p_swap = self.predict(stacked).reshape(len(drv), len(X)).T
        C = pd.DataFrame(p[:, None] - p_swap, columns=list(drv))
        # keep numeric drivers only when the value sits on the risky side of the baseline
        for k, (feats, _, _, direction) in drv.items():
            if direction:
                risky = (X[feats[0]] - self.baseline[feats[0]]) * direction > 0
                C.loc[~risky & (C[k] > 0), k] = 0.0
                C.loc[risky & (C[k] < 0), k] = 0.0
        return C

    def describe(self, X, i, k):
        feats, label, fmt, _ = self._drivers()[k]
        v = X.iloc[i][feats[0]]
        try:
            return f"{label}: {fmt.format(v)}"
        except (ValueError, TypeError):
            return f"{label}: {v}"

    def reasons(self, X, top=3, min_effect=0.01):
        """Top risk drivers per customer as readable strings + their effect on churn probability."""
        X = X[self.features].reset_index(drop=True)
        C = self.contributions(X)
        vals, cols = C.values, C.columns
        rows = []
        for i in range(len(X)):
            r = {}
            for k, j in enumerate([j for j in np.argsort(-vals[i]) if vals[i, j] >= min_effect][:top]):
                r[f"reason_{k + 1}"] = self.describe(X, i, cols[j])
                r[f"effect_{k + 1}"] = vals[i, j]
            rows.append(r)
        out = pd.DataFrame(rows, index=range(len(X)))
        names = [f"{p}_{k}" for k in range(1, top + 1) for p in ("reason", "effect")]
        out = out.reindex(columns=names)
        out["reason_1"] = out["reason_1"].fillna("No strong risk driver")
        return out, C

    def template(self, n=50, seed=7):
        """Sample upload file built from the reference data."""
        cols = ["customer_id"] + self.features + ["churn_flag"]
        return self.reference.sample(n, random_state=seed)[cols].reset_index(drop=True)
