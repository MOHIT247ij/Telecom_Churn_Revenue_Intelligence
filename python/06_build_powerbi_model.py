"""
06_build_powerbi_model.py
-------------------------
Builds a Kimball-style STAR SCHEMA for Power BI in powerbi/model_data/

    Dimensions : dim_date, dim_customer, dim_plan, dim_geography
    Facts      : fact_billing, fact_usage, fact_tickets, fact_churn_predictions, fact_monthly_kpis

Relationships (all single-direction, many-to-one):
    fact_* [customer_id] -> dim_customer [customer_id]
    fact_billing [plan_id] -> dim_plan [plan_id]
    dim_customer [geo_key] -> dim_geography [geo_key]   (snowflake, kept simple)
    fact_billing [bill_month] / fact_usage [usage_month] / fact_tickets [ticket_date]
    / fact_monthly_kpis [month] -> dim_date [date]
"""
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PROC, REP = ROOT / "data/processed", ROOT / "outputs/reports"
OUT = ROOT / "powerbi/model_data"; OUT.mkdir(parents=True, exist_ok=True)

cust = pd.read_csv(PROC / "customers_clean.csv", parse_dates=["join_date", "churn_date"])
plans = pd.read_csv(PROC / "plans_clean.csv")
bill = pd.read_csv(PROC / "billing_clean.csv", parse_dates=["bill_month"])
use = pd.read_csv(PROC / "network_usage_clean.csv", parse_dates=["usage_month"])
tick = pd.read_csv(PROC / "support_tickets_clean.csv", parse_dates=["ticket_date"])
pred = pd.read_csv(REP / "churn_predictions.csv")
kpi = pd.read_csv(REP / "monthly_kpis.csv", parse_dates=["month"])

# ---------------- dim_date (with Indian financial year Apr-Mar)
d = pd.DataFrame({"date": pd.date_range("2019-01-01", "2025-12-31", freq="D")})
d["year"] = d.date.dt.year
d["quarter"] = "Q" + d.date.dt.quarter.astype(str)
d["month_num"] = d.date.dt.month
d["month_name"] = d.date.dt.strftime("%b")
d["year_month"] = d.date.dt.strftime("%Y-%m")
d["month_start"] = d.date.dt.to_period("M").dt.to_timestamp()
fy = np.where(d.month_num >= 4, d.year + 1, d.year)
d["fiscal_year"] = "FY" + pd.Series(fy).astype(str).str[-2:]
d["fiscal_quarter"] = "FQ" + (((d.month_num - 4) % 12) // 3 + 1).astype(str)
d["is_weekend"] = d.date.dt.dayofweek >= 5
d.to_csv(OUT / "dim_date.csv", index=False)

# ---------------- dim_geography
zone = {"Maharashtra": "West", "Gujarat": "West", "Delhi NCR": "North", "Uttar Pradesh": "North",
        "Karnataka": "South", "Tamil Nadu": "South", "Telangana": "South", "West Bengal": "East"}
geo = cust[["circle", "city", "city_tier"]].drop_duplicates().sort_values(["circle", "city"]).reset_index(drop=True)
geo.insert(0, "geo_key", [f"G{i+1:03d}" for i in range(len(geo))])
geo["zone"] = geo.circle.map(zone)
geo["country"] = "India"
geo.to_csv(OUT / "dim_geography.csv", index=False)

# ---------------- dim_customer
dc = cust.merge(geo[["geo_key", "circle", "city"]], on=["circle", "city"])
dim_customer = dc[["customer_id", "geo_key", "gender", "age", "age_band", "senior_citizen", "partner",
                   "dependents", "join_date", "acquisition_channel", "service_type", "plan_id", "network_type",
                   "contract_type", "payment_method", "paperless_billing", "ott_bundle", "device_protection",
                   "intl_roaming", "priority_support", "multi_line", "addon_count", "discount_pct",
                   "monthly_charges", "charge_band", "tenure_months", "tenure_band", "churn", "churn_flag",
                   "churn_date", "churn_reason"]].copy()
dim_customer["customer_status"] = np.where(dim_customer.churn_flag == 1, "Churned", "Active")
dim_customer.to_csv(OUT / "dim_customer.csv", index=False)

# ---------------- dim_plan
plans.to_csv(OUT / "dim_plan.csv", index=False)

# ---------------- facts
fb = bill.merge(cust[["customer_id", "plan_id"]], on="customer_id")
fb[["invoice_id", "customer_id", "plan_id", "bill_month", "amount_billed", "amount_paid", "outstanding",
    "payment_status", "days_late"]].to_csv(OUT / "fact_billing.csv", index=False)
use.to_csv(OUT / "fact_usage.csv", index=False)
tick.to_csv(OUT / "fact_tickets.csv", index=False)
pred.to_csv(OUT / "fact_churn_predictions.csv", index=False)
kpi.to_csv(OUT / "fact_monthly_kpis.csv", index=False)

for f in sorted(OUT.glob("*.csv")):
    print(f"{f.name:<30} {sum(1 for _ in open(f)) - 1:>8,} rows")
