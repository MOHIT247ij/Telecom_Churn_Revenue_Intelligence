"""
07_load_sql.py
--------------
1. Exports load-ready CSVs (exact table column order) to sql/load/
2. Builds the database from sql/01_schema.sql, loads data, creates sql/04 views
3. Executes all 30 queries in sql/03_analysis_queries.sql and saves each result
   to outputs/sql_results/Qnn.csv  (acts as an automated SQL test-suite)

Default target : SQLite file  outputs/telecom_churn.db   (zero setup)
MySQL target   : python 07_load_sql.py --mysql "mysql+pymysql://user:pwd@localhost/telecom_churn_db"
"""
import argparse, re, sqlite3, time
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PROC, REP, SQL = ROOT / "data/processed", ROOT / "outputs/reports", ROOT / "sql"
LOAD = SQL / "load"; LOAD.mkdir(exist_ok=True)
RES = ROOT / "outputs/sql_results"; RES.mkdir(parents=True, exist_ok=True)

ap = argparse.ArgumentParser()
ap.add_argument("--mysql", help="SQLAlchemy URL for MySQL target")
args = ap.parse_args()

# ------------------------------------------------------------------ 1. load-ready CSVs
period = lambda s: s.dt.year * 12 + s.dt.month
c = pd.read_csv(PROC / "customers_clean.csv", parse_dates=["join_date", "churn_date", "cohort_month"])
c["join_month"] = c.cohort_month
c["join_period"] = period(c.join_month)
c["cohort_quarter"] = c.join_month.dt.year.astype(str) + "-Q" + c.join_month.dt.quarter.astype(str)
c["churn_month"] = c.churn_date.dt.to_period("M").dt.to_timestamp()
c["churn_period"] = period(c.churn_month).astype("Int64")
cust_cols = ["customer_id", "gender", "age", "age_band", "senior_citizen", "partner", "dependents", "circle",
             "city", "city_tier", "join_date", "join_month", "join_period", "cohort_quarter",
             "acquisition_channel", "service_type", "plan_id", "network_type", "contract_type", "payment_method",
             "paperless_billing", "ott_bundle", "device_protection", "intl_roaming", "priority_support",
             "multi_line", "addon_count", "discount_pct", "monthly_charges", "charge_band", "tenure_months",
             "tenure_band", "total_charges", "avg_monthly_data_gb", "churn_flag", "churn_date", "churn_month",
             "churn_period", "churn_reason"]
c = c[cust_cols]
for col in ["join_date", "join_month", "churn_date", "churn_month"]:
    c[col] = c[col].dt.strftime("%Y-%m-%d")

b = pd.read_csv(PROC / "billing_clean.csv", parse_dates=["bill_month"])
b["bill_period"] = period(b.bill_month)
b["bill_month"] = b.bill_month.dt.strftime("%Y-%m-%d")
b = b[["invoice_id", "customer_id", "bill_month", "bill_period", "amount_billed", "amount_paid",
       "outstanding", "payment_status", "days_late"]]

t = pd.read_csv(PROC / "support_tickets_clean.csv")
t["csat_score"] = t["csat_score"].astype("Int64")
u = pd.read_csv(PROC / "network_usage_clean.csv")
p = pd.read_csv(PROC / "plans_clean.csv")
pr = pd.read_csv(REP / "churn_predictions.csv")

tables = {"plans": p, "customers": c, "billing": b, "support_tickets": t, "network_usage": u,
          "churn_predictions": pr}
for name, df in tables.items():
    df.to_csv(LOAD / f"{name}.csv", index=False)


def split_sql(text):
    text = "\n".join(l for l in text.splitlines() if not l.strip().startswith("--") or re.match(r"--\s*Q\d+", l.strip()))
    stmts = [s.strip() for s in text.split(";") if s.strip() and not all(
        l.strip().startswith("--") for l in s.strip().splitlines())]
    # MySQL-session statements are skipped for SQLite (and handled by the URL for MySQL)
    skip = ("CREATE DATABASE", "USE ", "SET GLOBAL")
    return [s for s in stmts if not s.upper().startswith(skip)]


# ------------------------------------------------------------------ 2. build DB
if args.mysql:
    from sqlalchemy import create_engine, text
    eng = create_engine(args.mysql)
    conn = eng.raw_connection()
else:
    db = ROOT / "outputs/telecom_churn.db"
    db.unlink(missing_ok=True)
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA foreign_keys = ON")
cur = conn.cursor()
for stmt in split_sql((SQL / "01_schema.sql").read_text()):
    cur.execute(stmt)
conn.commit()

for name, df in tables.items():
    cols = list(df.columns)
    ph = ", ".join(["?" if not args.mysql else "%s"] * len(cols))
    rows = [tuple(None if pd.isna(v) else (v.item() if hasattr(v, "item") else v) for v in r)
            for r in df.itertuples(index=False)]
    cur.executemany(f"INSERT INTO {name} ({', '.join(cols)}) VALUES ({ph})", rows)
    conn.commit()
    print(f"loaded {name:<18} {len(rows):>8,} rows")

for stmt in split_sql((SQL / "04_views_for_powerbi.sql").read_text()):
    cur.execute(stmt)
conn.commit()
print("views created")

# ------------------------------------------------------------------ 3. run analysis queries
text_sql = (SQL / "03_analysis_queries.sql").read_text()
blocks = re.split(r"\n(?=-- Q\d+ \|)", text_sql)
ok = 0
for blk in blocks:
    m = re.match(r"-- (Q\d+) \| (.+)", blk)
    if not m:
        continue
    qid, title = m.groups()
    q = blk.split(";")[0]
    t0 = time.time()
    df = pd.read_sql_query(q, conn)
    df.to_csv(RES / f"{qid}.csv", index=False)
    ok += 1
    print(f"{qid} ✔ {len(df):>5} rows  {time.time() - t0:5.2f}s  {title[:70]}")

# views smoke-test
for v in ["vw_customer_360", "vw_monthly_kpis", "vw_churn_by_segment", "vw_revenue_circle_month",
          "vw_high_risk_customers", "vw_support_summary"]:
    n = pd.read_sql_query(f"SELECT COUNT(*) AS n FROM {v}", conn).n.iat[0]
    print(f"view {v:<26} {n:>7,} rows")
conn.close()
print(f"\n{ok} / 30 queries executed successfully")
