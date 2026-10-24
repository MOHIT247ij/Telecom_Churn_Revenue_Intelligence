"""
01_generate_data.py
-------------------
Generates a realistic, Indian-telecom-style synthetic dataset (Jan-2024 .. Dec-2025)
for the "Telecom Customer Churn & Revenue Intelligence" project.

Tables produced (data/raw/):
    customers.csv        - customer master + subscription + usage snapshot (with DQ issues)
    plans.csv            - plan catalogue
    billing.csv          - monthly invoices & payments (one row per customer-month)
    support_tickets.csv  - customer care tickets
    network_usage.csv    - monthly data / voice usage & network quality KPIs

Business realism baked in:
    * July-2024 tariff hike (~15%) on mobile plans -> churn spike Jul-Sep 2024
    * Month-to-month & prepaid customers churn more than 12/24-month contracts
    * Poor network quality -> more tickets -> lower CSAT -> higher churn
    * Late payers and high-bill / low-tenure customers are high risk
    * Intentional data-quality issues in customers.csv for the cleaning step
"""
from pathlib import Path
import numpy as np
import pandas as pd

SEED = 42
rng = np.random.default_rng(SEED)
ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
RAW.mkdir(parents=True, exist_ok=True)

N_CUSTOMERS = 8000
WINDOW_START = pd.Timestamp("2024-01-01")
WINDOW_END = pd.Timestamp("2025-12-01")          # last billing month
SNAPSHOT = pd.Timestamp("2025-12-31")
MONTHS = pd.date_range(WINDOW_START, WINDOW_END, freq="MS")
TARIFF_HIKE = pd.Timestamp("2024-07-01")
HAZARD_SHIFT = 2.10          # calibrates overall 24-month churn to ~25%

# ------------------------------------------------------------------ plans
plans = pd.DataFrame([
    # plan_id, plan_name, service_type, monthly_fee, data_gb, voice
    ("PP199", "Prepaid Basic 4G",        "Prepaid Mobile",  199,  30, "Unlimited"),
    ("PP299", "Prepaid Smart 5G",        "Prepaid Mobile",  299,  60, "Unlimited"),
    ("PP399", "Prepaid Unlimited 5G",    "Prepaid Mobile",  399,  90, "Unlimited"),
    ("PP599", "Prepaid Unlimited Plus",  "Prepaid Mobile",  599, 150, "Unlimited"),
    ("PO399", "Postpaid Essential",      "Postpaid Mobile", 399,  75, "Unlimited"),
    ("PO599", "Postpaid Plus",           "Postpaid Mobile", 599, 120, "Unlimited"),
    ("PO999", "Postpaid Family (3 SIM)", "Postpaid Mobile", 999, 250, "Unlimited"),
    ("PO1499","Postpaid Premium",        "Postpaid Mobile",1499, 400, "Unlimited + ISD"),
    ("FB699", "Fiber 100 Mbps",          "Fiber Broadband", 699, 3300, "Landline"),
    ("FB999", "Fiber 300 Mbps",          "Fiber Broadband", 999, 3300, "Landline"),
    ("FB1499","Fiber 1 Gbps",            "Fiber Broadband",1499, 5000, "Landline"),
], columns=["plan_id", "plan_name", "service_type", "monthly_fee", "data_gb_limit", "voice_benefit"])
plans["plan_tier"] = np.select(
    [plans.monthly_fee < 400, plans.monthly_fee < 900], ["Value", "Mid"], "Premium")

# ------------------------------------------------------------------ geography
geo = {
    "Maharashtra":   ["Mumbai", "Pune", "Nagpur", "Nashik"],
    "Delhi NCR":     ["New Delhi", "Gurugram", "Noida"],
    "Karnataka":     ["Bengaluru", "Mysuru", "Hubballi"],
    "Tamil Nadu":    ["Chennai", "Coimbatore", "Madurai"],
    "Gujarat":       ["Ahmedabad", "Surat", "Vadodara"],
    "Uttar Pradesh": ["Lucknow", "Kanpur", "Varanasi"],
    "West Bengal":   ["Kolkata", "Howrah", "Siliguri"],
    "Telangana":     ["Hyderabad", "Warangal"],
}
circle_w = np.array([0.20, 0.15, 0.14, 0.12, 0.10, 0.12, 0.09, 0.08])
# some circles have weaker networks (drives churn)
circle_network_penalty = {"Maharashtra": 0.0, "Delhi NCR": 0.05, "Karnataka": 0.0, "Tamil Nadu": 0.02,
                          "Gujarat": 0.03, "Uttar Pradesh": 0.35, "West Bengal": 0.25, "Telangana": 0.05}

circles = rng.choice(list(geo.keys()), N_CUSTOMERS, p=circle_w)
cities = np.array([rng.choice(geo[c]) for c in circles])
tier1 = {"Mumbai", "Pune", "New Delhi", "Gurugram", "Noida", "Bengaluru", "Chennai", "Ahmedabad",
         "Kolkata", "Hyderabad"}
city_tier = np.where(np.isin(cities, list(tier1)), "Tier 1", "Tier 2")

# ------------------------------------------------------------------ demographics
cust_ids = np.array([f"CUST{100000 + i}" for i in range(N_CUSTOMERS)])
gender = rng.choice(["Male", "Female"], N_CUSTOMERS, p=[0.56, 0.44])
age = np.clip(rng.normal(36, 12, N_CUSTOMERS).round(), 18, 80).astype(int)
senior = (age >= 60).astype(int)
partner = rng.choice(["Yes", "No"], N_CUSTOMERS, p=[0.48, 0.52])
dependents = np.where(partner == "Yes", rng.choice(["Yes", "No"], N_CUSTOMERS, p=[0.55, 0.45]),
                      rng.choice(["Yes", "No"], N_CUSTOMERS, p=[0.12, 0.88]))

# join dates: 45% legacy (2019-2023), 55% acquired inside window
legacy = rng.random(N_CUSTOMERS) < 0.45
legacy_days = rng.integers(0, (pd.Timestamp("2023-12-31") - pd.Timestamp("2019-01-01")).days, N_CUSTOMERS)
new_days = rng.integers(0, (pd.Timestamp("2025-12-20") - WINDOW_START).days, N_CUSTOMERS)
join_date = np.where(legacy, pd.Timestamp("2019-01-01") + pd.to_timedelta(legacy_days, "D"),
                     WINDOW_START + pd.to_timedelta(new_days, "D"))
join_date = pd.Series(pd.to_datetime(join_date))

channel = rng.choice(["Retail Store", "Online / App", "Telesales", "Partner / Dealer", "Referral"],
                     N_CUSTOMERS, p=[0.34, 0.30, 0.10, 0.16, 0.10])

# ------------------------------------------------------------------ service & plan
service = rng.choice(["Prepaid Mobile", "Postpaid Mobile", "Fiber Broadband"], N_CUSTOMERS,
                     p=[0.52, 0.30, 0.18])
plan_id = np.empty(N_CUSTOMERS, dtype=object)
for s, w in [("Prepaid Mobile", [0.30, 0.35, 0.25, 0.10]),
             ("Postpaid Mobile", [0.30, 0.35, 0.22, 0.13]),
             ("Fiber Broadband", [0.45, 0.40, 0.15])]:
    idx = np.where(service == s)[0]
    plan_id[idx] = rng.choice(plans.loc[plans.service_type == s, "plan_id"].values, len(idx), p=w)
fee = plans.set_index("plan_id").loc[plan_id, "monthly_fee"].values

contract = np.where(service == "Prepaid Mobile", "Prepaid (No Contract)",
                    rng.choice(["Month-to-Month", "12 Month", "24 Month"], N_CUSTOMERS,
                               p=[0.50, 0.28, 0.22]))
payment = np.where(service == "Prepaid Mobile",
                   rng.choice(["UPI", "Retail Recharge (Cash)", "Credit / Debit Card", "Wallet"],
                              N_CUSTOMERS, p=[0.48, 0.24, 0.16, 0.12]),
                   rng.choice(["Auto-Debit (NACH)", "UPI", "Credit / Debit Card", "Net Banking"],
                              N_CUSTOMERS, p=[0.30, 0.35, 0.20, 0.15]))
paperless = np.where(np.isin(payment, ["Retail Recharge (Cash)"]), "No",
                     rng.choice(["Yes", "No"], N_CUSTOMERS, p=[0.78, 0.22]))

ott = rng.random(N_CUSTOMERS) < np.where(fee >= 599, 0.65, 0.25)
device_prot = rng.random(N_CUSTOMERS) < np.where(service == "Postpaid Mobile", 0.30, 0.08)
intl_roam = rng.random(N_CUSTOMERS) < np.where(fee >= 999, 0.30, 0.04)
priority_support = rng.random(N_CUSTOMERS) < np.where(service == "Prepaid Mobile", 0.05, 0.25)
multi_line = np.where(service == "Postpaid Mobile",
                      rng.choice(["Yes", "No"], N_CUSTOMERS, p=[0.35, 0.65]), "No")
network_type = np.where(service == "Fiber Broadband", "FTTH",
                        np.where(np.isin(plan_id, ["PP199"]), "4G",
                                 rng.choice(["5G", "4G"], N_CUSTOMERS, p=[0.62, 0.38])))

discount = np.where(np.isin(contract, ["12 Month", "24 Month"]),
                    rng.choice([0, 0.05, 0.10, 0.15], N_CUSTOMERS, p=[0.3, 0.3, 0.25, 0.15]), 0.0)
monthly_charges = (fee + ott * 149 + device_prot * 99 + intl_roam * 249 + priority_support * 49) \
                  * (1 - discount)
monthly_charges = np.round(monthly_charges, 2)

# ------------------------------------------------------------------ network quality
penalty = np.array([circle_network_penalty[c] for c in circles])
drop_rate = np.clip(rng.gamma(2.0, 0.6, N_CUSTOMERS) + penalty * 3 +
                    (network_type == "4G") * 0.4 - (network_type == "FTTH") * 0.6, 0.1, 12)
avg_speed = np.where(network_type == "FTTH", rng.normal(220, 60, N_CUSTOMERS),
                     np.where(network_type == "5G", rng.normal(165, 45, N_CUSTOMERS),
                              rng.normal(22, 7, N_CUSTOMERS))) * (1 - penalty * 0.5)
avg_speed = np.clip(avg_speed, 3, 900).round(1)

# ------------------------------------------------------------------ support tickets intensity
ticket_lambda = 0.15 + drop_rate * 0.10 + (monthly_charges > 900) * 0.05 + penalty * 0.3

# ------------------------------------------------------------------ churn propensity
tenure_at_start = ((WINDOW_START - join_date).dt.days / 30.4).clip(lower=0)
logit = (-3.05
         + 1.05 * (contract == "Month-to-Month")
         + 0.80 * (contract == "Prepaid (No Contract)")
         - 0.90 * (contract == "24 Month")
         - 0.35 * (contract == "12 Month")
         + 0.22 * drop_rate
         + 0.55 * penalty
         + 0.0012 * (monthly_charges - 500)
         - 0.020 * np.minimum(tenure_at_start, 60)
         + 0.35 * (payment == "Retail Recharge (Cash)")
         - 0.45 * (payment == "Auto-Debit (NACH)")
         - 0.30 * priority_support
         - 0.25 * (multi_line == "Yes")
         + 0.30 * (senior == 1)
         - 0.20 * (partner == "Yes")
         + 0.25 * (channel == "Partner / Dealer")
         - 0.30 * (channel == "Referral")
         + 0.45 * ticket_lambda
         + rng.normal(0, 0.45, N_CUSTOMERS))
# monthly churn hazard (discrete-time survival simulation)
monthly_hazard = 1 / (1 + np.exp(-(logit - HAZARD_SHIFT)))
churned = np.zeros(N_CUSTOMERS, dtype=bool)

first_month = pd.Series(join_date).dt.to_period("M").dt.to_timestamp().clip(lower=WINDOW_START)
churn_date = pd.Series(pd.NaT, index=range(N_CUSTOMERS), dtype="datetime64[ns]")
month_weights = np.ones(len(MONTHS))
month_weights[(MONTHS >= "2024-07-01") & (MONTHS <= "2024-09-01")] = 2.4   # tariff-hike shock
month_weights[(MONTHS >= "2025-04-01") & (MONTHS <= "2025-05-01")] = 1.5   # competitor 5G launch
for i in range(N_CUSTOMERS):
    for k, m in enumerate(MONTHS):
        if m <= first_month[i]:
            continue
        tenure_m = (m - join_date[i]).days / 30.4
        h = monthly_hazard[i] * month_weights[k] * (1.6 if tenure_m < 6 else 1.0)
        if rng.random() < h:
            churned[i] = True
            churn_date[i] = m + pd.Timedelta(days=int(rng.integers(0, 27)))
            break

reasons = ["Competitor Offer", "Network / Coverage Issues", "Price / Tariff Hike",
           "Poor Customer Service", "Relocation", "Billing Disputes", "Moved to Fiber / Other Device"]
churn_reason = np.full(N_CUSTOMERS, None, dtype=object)
for i in np.where(churned)[0]:
    w = np.array([0.24, 0.12 + penalty[i] * 0.6 + drop_rate[i] * 0.02, 0.18, 0.12, 0.10, 0.08, 0.06])
    if TARIFF_HIKE <= churn_date[i] < pd.Timestamp("2024-10-01"):
        w[2] += 0.35
    churn_reason[i] = rng.choice(reasons, p=w / w.sum())

end_date = churn_date.fillna(SNAPSHOT)
tenure_months = (((end_date - join_date).dt.days) / 30.4).round().astype(int).clip(lower=1)

# ------------------------------------------------------------------ billing + usage (monthly)
bill_rows, usage_rows = [], []
plan_data = plans.set_index("plan_id")["data_gb_limit"].to_dict()
late_propensity = np.clip(0.05 + 0.10 * (payment == "Retail Recharge (Cash)") +
                          0.06 * (payment == "UPI") - 0.04 * (payment == "Auto-Debit (NACH)") +
                          0.03 * churned + rng.normal(0, 0.03, N_CUSTOMERS), 0.005, 0.6)
inv = 1
for i in range(N_CUSTOMERS):
    start = first_month[i]
    stop = churn_date[i].to_period("M").to_timestamp() if churned[i] else WINDOW_END
    cust_months = MONTHS[(MONTHS >= start) & (MONTHS <= stop)]
    base_usage = plan_data[plan_id[i]] * rng.uniform(0.35, 0.9)
    for m in cust_months:
        hike = 1.15 if (m >= TARIFF_HIKE and service[i] != "Fiber Broadband") else 1.0
        prorate = 1.0
        if m == start and join_date[i] >= WINDOW_START:
            prorate = max(0.2, 1 - (join_date[i].day - 1) / 30)
        overage = rng.choice([0, 0, 0, 0, 49, 99, 199]) if service[i] != "Prepaid Mobile" else 0
        billed = round(monthly_charges[i] * hike * prorate + overage, 2)
        # disengagement in last 2 months before churn
        months_to_churn = (stop.year - m.year) * 12 + (stop.month - m.month) if churned[i] else 99
        # subtle, noisy pre-churn disengagement; non-churners also have random dips (travel, dual-SIM)
        engage = rng.normal(0.85, 0.15) if months_to_churn <= 1 else (rng.normal(0.85, 0.15) if rng.random() < 0.10 else 1.0)
        r = rng.random()
        lp = late_propensity[i] * (1.3 if months_to_churn <= 1 else 1)
        if churned[i] and months_to_churn == 0 and rng.random() < 0.35:
            status, paid, late = "Unpaid", 0.0, None
        elif r < lp:
            status, paid, late = "Paid Late", billed, int(rng.integers(3, 45))
        else:
            status, paid, late = "Paid On Time", billed, 0
        bill_rows.append((f"INV{inv:07d}", cust_ids[i], m.date(), billed, paid, status, late))
        usage_rows.append((cust_ids[i], m.date(),
                           round(max(0.1, base_usage * engage * rng.normal(1, 0.15)), 2),
                           int(max(0, rng.normal(650, 250) * engage)) if service[i] != "Fiber Broadband"
                           else int(max(0, rng.normal(60, 30))),
                           round(max(0.05, drop_rate[i] * rng.normal(1, 0.25)), 2),
                           round(max(2, avg_speed[i] * rng.normal(1, 0.12)), 1)))
        inv += 1

billing = pd.DataFrame(bill_rows, columns=["invoice_id", "customer_id", "bill_month", "amount_billed",
                                           "amount_paid", "payment_status", "days_late"])
usage = pd.DataFrame(usage_rows, columns=["customer_id", "usage_month", "data_used_gb",
                                          "voice_minutes", "call_drop_rate_pct", "avg_speed_mbps"])

# ------------------------------------------------------------------ support tickets
cats = ["Network / Coverage", "Slow Data Speed", "Billing Dispute", "Recharge / Payment Failure",
        "SIM / Device", "Plan Change Request", "Broadband Outage"]
t_rows, tid = [], 1
for i in range(N_CUSTOMERS):
    start = max(join_date[i], WINDOW_START)
    stop = churn_date[i] if churned[i] else SNAPSHOT
    active_m = max(1, (stop - start).days / 30.4)
    n = rng.poisson(ticket_lambda[i] * active_m * (1.15 if churned[i] else 1.0))
    for _ in range(n):
        d = start + pd.Timedelta(days=int(rng.integers(0, max(1, (stop - start).days))))
        if service[i] == "Fiber Broadband":
            cw = [0.10, 0.25, 0.15, 0.10, 0.05, 0.10, 0.25]
        else:
            cw = [0.30, 0.20, 0.15, 0.15, 0.10, 0.10, 0.0]
        cat = rng.choice(cats, p=cw)
        res_h = round(float(rng.gamma(2, 9 if cat in ("Network / Coverage", "Broadband Outage") else 5)), 1)
        csat = int(np.clip(round(rng.normal(4.3 - res_h / 30 - (0.25 if churned[i] else 0), 0.8)), 1, 5))
        chan = rng.choice(["Call Centre", "App Chat", "Store", "Email", "Social Media"],
                          p=[0.40, 0.30, 0.15, 0.08, 0.07])
        resolved = "Yes" if rng.random() < 0.92 else "No"
        t_rows.append((f"TKT{tid:07d}", cust_ids[i], d.date(), cat, chan, res_h, resolved,
                       csat if resolved == "Yes" else None))
        tid += 1
tickets = pd.DataFrame(t_rows, columns=["ticket_id", "customer_id", "ticket_date", "category", "channel",
                                        "resolution_hours", "resolved", "csat_score"])

# ------------------------------------------------------------------ customer snapshot
total_charges = billing.groupby("customer_id")["amount_billed"].sum()
avg_data = usage.groupby("customer_id")["data_used_gb"].mean()
customers = pd.DataFrame({
    "customer_id": cust_ids, "gender": gender, "age": age, "senior_citizen": senior,
    "partner": partner, "dependents": dependents, "circle": circles, "city": cities,
    "city_tier": city_tier, "join_date": join_date.dt.date.values, "acquisition_channel": channel,
    "service_type": service, "plan_id": plan_id, "network_type": network_type, "contract_type": contract,
    "payment_method": payment, "paperless_billing": paperless,
    "ott_bundle": np.where(ott, "Yes", "No"), "device_protection": np.where(device_prot, "Yes", "No"),
    "intl_roaming": np.where(intl_roam, "Yes", "No"),
    "priority_support": np.where(priority_support, "Yes", "No"), "multi_line": multi_line,
    "discount_pct": (discount * 100).round(0), "monthly_charges": monthly_charges,
    "tenure_months": tenure_months,
    "total_charges": pd.Series(cust_ids).map(total_charges).round(2).values,
    "avg_monthly_data_gb": pd.Series(cust_ids).map(avg_data).round(2).values,
    "churn": np.where(churned, "Yes", "No"),
    "churn_date": churn_date.dt.date.values, "churn_reason": churn_reason,
})

# ------------------------------------------------------------------ inject data-quality issues
dq = customers.copy()
n = len(dq)
idx = rng.choice(n, int(n * 0.03), replace=False); dq.loc[idx, "age"] = np.nan
idx = rng.choice(n, 12, replace=False);             dq.loc[idx, "age"] = rng.choice([0, 150, 199, -5], 12)
idx = rng.choice(n, int(n * 0.10), replace=False)
dq.loc[idx, "gender"] = dq.loc[idx, "gender"].map({"Male": rng.choice(["M", "male", "MALE"]),
                                                   "Female": rng.choice(["F", "female", "FEMALE"])})
idx = rng.choice(n, int(n * 0.05), replace=False); dq.loc[idx, "city"] = "  " + dq.loc[idx, "city"].str.upper() + " "
dq["total_charges"] = dq["total_charges"].astype(object)
idx = rng.choice(n, int(n * 0.015), replace=False); dq.loc[idx, "total_charges"] = " "
idx = rng.choice(n, int(n * 0.02), replace=False);  dq.loc[idx, "payment_method"] = np.nan
idx = rng.choice(n, 15, replace=False);             dq.loc[idx, "avg_monthly_data_gb"] *= -1
dups = dq.sample(85, random_state=SEED)
dq = pd.concat([dq, dups]).sample(frac=1, random_state=SEED).reset_index(drop=True)

# ------------------------------------------------------------------ save
dq.to_csv(RAW / "customers.csv", index=False)
plans.to_csv(RAW / "plans.csv", index=False)
billing.to_csv(RAW / "billing.csv", index=False)
tickets.to_csv(RAW / "support_tickets.csv", index=False)
usage.to_csv(RAW / "network_usage.csv", index=False)

print(f"customers      : {len(dq):,} rows (incl. {len(dups)} duplicates)")
print(f"billing        : {len(billing):,} rows")
print(f"network_usage  : {len(usage):,} rows")
print(f"support_tickets: {len(tickets):,} rows")
print(f"overall churn  : {customers.churn.eq('Yes').mean():.1%}")
