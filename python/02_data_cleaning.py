"""
02_data_cleaning.py
-------------------
ETL / data-quality layer.  Reads data/raw/*, applies documented cleaning rules,
writes analysis-ready tables to data/processed/ and a DQ audit report to
outputs/reports/data_quality_report.csv

Cleaning rules
    R1  Remove exact & key-level duplicate customers
    R2  Standardise gender labels (M / male / MALE -> Male ...)
    R3  Trim + title-case city names
    R4  Invalid ages (<18 or >100) -> NaN, then impute median by circle
    R5  total_charges blank strings -> numeric; impute from billing table
    R6  Missing payment_method -> mode within service_type
    R7  Negative usage -> absolute value
    R8  Type casting (dates, numerics) and derived flags
"""
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW, PROC, REP = ROOT / "data/raw", ROOT / "data/processed", ROOT / "outputs/reports"
PROC.mkdir(parents=True, exist_ok=True); REP.mkdir(parents=True, exist_ok=True)

log = []
def audit(rule, desc, rows):
    log.append({"rule": rule, "description": desc, "rows_affected": int(rows)})
    print(f"[{rule}] {desc:<55} {rows:>6,}")

cust = pd.read_csv(RAW / "customers.csv")
plans = pd.read_csv(RAW / "plans.csv")
billing = pd.read_csv(RAW / "billing.csv", parse_dates=["bill_month"])
tickets = pd.read_csv(RAW / "support_tickets.csv", parse_dates=["ticket_date"])
usage = pd.read_csv(RAW / "network_usage.csv", parse_dates=["usage_month"])
audit("R0", "Raw customer rows loaded", len(cust))

# R1 duplicates
before = len(cust)
cust = cust.drop_duplicates().drop_duplicates(subset="customer_id", keep="first")
audit("R1", "Duplicate customer rows removed", before - len(cust))

# R2 gender
g_map = {"m": "Male", "male": "Male", "f": "Female", "female": "Female"}
bad = ~cust["gender"].isin(["Male", "Female"])
cust["gender"] = cust["gender"].str.strip().str.lower().map(g_map)
audit("R2", "Gender labels standardised", bad.sum())

# R3 city
bad = cust["city"] != cust["city"].str.strip().str.title()
cust["city"] = cust["city"].str.strip().str.title()
audit("R3", "City names trimmed / title-cased", bad.sum())

# R4 age
invalid = (cust["age"] < 18) | (cust["age"] > 100)
cust.loc[invalid, "age"] = np.nan
missing = cust["age"].isna().sum()
cust["age"] = cust["age"].fillna(cust.groupby("circle")["age"].transform("median")).round().astype(int)
cust["senior_citizen"] = (cust["age"] >= 60).astype(int)
audit("R4", f"Invalid ages nulled ({invalid.sum()}) + imputed (total)", missing)

# R5 total_charges
cust["total_charges"] = pd.to_numeric(cust["total_charges"].astype(str).str.strip().replace("", np.nan),
                                      errors="coerce")
miss = cust["total_charges"].isna()
bill_total = billing.groupby("customer_id")["amount_billed"].sum()
cust.loc[miss, "total_charges"] = cust.loc[miss, "customer_id"].map(bill_total)
audit("R5", "Blank total_charges recovered from billing", miss.sum())

# R6 payment method
miss = cust["payment_method"].isna()
cust["payment_method"] = cust["payment_method"].fillna(
    cust.groupby("service_type")["payment_method"].transform(lambda s: s.mode().iat[0]))
audit("R6", "Missing payment_method imputed (mode by service)", miss.sum())

# R7 negative usage
neg = cust["avg_monthly_data_gb"] < 0
cust["avg_monthly_data_gb"] = cust["avg_monthly_data_gb"].abs()
audit("R7", "Negative data usage corrected", neg.sum())

# R8 types + derived columns
cust["join_date"] = pd.to_datetime(cust["join_date"])
cust["churn_date"] = pd.to_datetime(cust["churn_date"])
cust["churn_flag"] = (cust["churn"] == "Yes").astype(int)
cust = cust.merge(plans[["plan_id", "plan_name", "plan_tier", "monthly_fee"]], on="plan_id", how="left")
cust["tenure_band"] = pd.cut(cust["tenure_months"], [0, 6, 12, 24, 48, 999],
                             labels=["0-6 M", "7-12 M", "13-24 M", "25-48 M", "48+ M"])
cust["age_band"] = pd.cut(cust["age"], [17, 25, 35, 45, 60, 100],
                          labels=["18-25", "26-35", "36-45", "46-60", "60+"])
cust["charge_band"] = pd.cut(cust["monthly_charges"], [0, 300, 600, 1000, 99999],
                             labels=["< 300", "300-600", "600-1000", "1000+"])
cust["addon_count"] = (cust[["ott_bundle", "device_protection", "intl_roaming", "priority_support"]]
                       == "Yes").sum(axis=1)
cust["cohort_month"] = cust["join_date"].dt.to_period("M").dt.to_timestamp()
audit("R8", "Types cast & derived features added", len(cust))

# billing / tickets checks
billing["days_late"] = billing["days_late"].fillna(-1).astype(int)   # -1 = unpaid
billing["outstanding"] = (billing["amount_billed"] - billing["amount_paid"]).round(2)
orphan = ~billing["customer_id"].isin(cust["customer_id"])
audit("R9", "Orphan billing rows (FK check)", orphan.sum())
billing = billing[~orphan]
tickets["resolved_flag"] = (tickets["resolved"] == "Yes").astype(int)

# null summary after cleaning
nulls = cust.drop(columns=["churn_date", "churn_reason"]).isna().sum().sum()
audit("QC", "Remaining nulls (excl. churn_date/reason)", nulls)

cust.to_csv(PROC / "customers_clean.csv", index=False)
billing.to_csv(PROC / "billing_clean.csv", index=False)
tickets.to_csv(PROC / "support_tickets_clean.csv", index=False)
usage.to_csv(PROC / "network_usage_clean.csv", index=False)
plans.to_csv(PROC / "plans_clean.csv", index=False)
pd.DataFrame(log).to_csv(REP / "data_quality_report.csv", index=False)
print(f"\nClean customers: {len(cust):,} | churn rate {cust.churn_flag.mean():.1%}")
