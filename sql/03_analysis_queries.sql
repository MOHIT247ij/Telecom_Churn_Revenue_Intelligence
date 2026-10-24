-- =====================================================================
--  Telecom Customer Churn & Revenue Intelligence
--  03_analysis_queries.sql  -  30 business questions answered in SQL
--  Portable ANSI SQL (CTEs + window functions) - tested on MySQL 8 & SQLite 3.4x
--  Each query is tagged  "-- Qnn | <question>"  (python/07_load_sql.py runs & exports them)
-- =====================================================================

USE telecom_churn_db;


-- =====================================================================
--  SECTION A : EXECUTIVE KPIs
-- =====================================================================

-- Q01 | Headline KPIs - customer base, churn rate, revenue, ARPU
SELECT
    COUNT(*)                                                         AS total_customers,
    SUM(CASE WHEN churn_flag = 0 THEN 1 ELSE 0 END)                  AS active_customers,
    SUM(churn_flag)                                                  AS churned_customers,
    ROUND(100.0 * SUM(churn_flag) / COUNT(*), 2)                     AS churn_rate_pct,
    ROUND(AVG(monthly_charges), 2)                                   AS avg_monthly_charge,
    ROUND(SUM(CASE WHEN churn_flag = 0 THEN monthly_charges ELSE 0 END), 0) AS current_mrr,
    ROUND(AVG(tenure_months), 1)                                     AS avg_tenure_months
FROM customers;

-- Q02 | Total billed vs collected revenue and collection efficiency
SELECT
    ROUND(SUM(amount_billed), 0)                                     AS total_billed,
    ROUND(SUM(amount_paid), 0)                                       AS total_collected,
    ROUND(SUM(outstanding), 0)                                       AS bad_debt_outstanding,
    ROUND(100.0 * SUM(amount_paid) / SUM(amount_billed), 2)          AS collection_efficiency_pct,
    ROUND(100.0 * SUM(CASE WHEN payment_status = 'Paid Late' THEN 1 ELSE 0 END) / COUNT(*), 2) AS late_payment_pct
FROM billing;


-- =====================================================================
--  SECTION B : CHURN DIAGNOSTICS
-- =====================================================================

-- Q03 | Churn rate by contract type (with lift vs company average)
WITH base AS (SELECT AVG(1.0 * churn_flag) AS avg_churn FROM customers)
SELECT
    c.contract_type,
    COUNT(*)                                                AS customers,
    SUM(c.churn_flag)                                       AS churned,
    ROUND(100.0 * AVG(1.0 * c.churn_flag), 2)               AS churn_rate_pct,
    ROUND(AVG(1.0 * c.churn_flag) / MAX(b.avg_churn), 2)    AS lift_vs_avg
FROM customers c CROSS JOIN base b
GROUP BY c.contract_type
ORDER BY churn_rate_pct DESC;

-- Q04 | Churn rate by tenure band (new-customer churn problem)
SELECT tenure_band,
       COUNT(*)                                  AS customers,
       ROUND(100.0 * AVG(1.0 * churn_flag), 2)   AS churn_rate_pct
FROM customers
GROUP BY tenure_band
ORDER BY MIN(tenure_months);

-- Q05 | Churn rate by telecom circle - ranked
SELECT circle,
       COUNT(*)                                                       AS customers,
       SUM(churn_flag)                                                AS churned,
       ROUND(100.0 * AVG(1.0 * churn_flag), 2)                        AS churn_rate_pct,
       RANK() OVER (ORDER BY AVG(1.0 * churn_flag) DESC)              AS churn_rank
FROM customers
GROUP BY circle;

-- Q06 | Service type x contract churn matrix
SELECT service_type,
       contract_type,
       COUNT(*)                                  AS customers,
       ROUND(100.0 * AVG(1.0 * churn_flag), 2)   AS churn_rate_pct,
       ROUND(AVG(monthly_charges), 0)            AS avg_charge
FROM customers
GROUP BY service_type, contract_type
ORDER BY service_type, churn_rate_pct DESC;

-- Q07 | Churn by payment method
SELECT payment_method,
       COUNT(*)                                  AS customers,
       ROUND(100.0 * AVG(1.0 * churn_flag), 2)   AS churn_rate_pct
FROM customers
GROUP BY payment_method
ORDER BY churn_rate_pct DESC;

-- Q08 | Churn reasons - share of total churn and revenue lost
SELECT churn_reason,
       COUNT(*)                                                         AS churned_customers,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2)               AS share_pct,
       ROUND(SUM(monthly_charges), 0)                                   AS mrr_lost
FROM customers
WHERE churn_flag = 1
GROUP BY churn_reason
ORDER BY churned_customers DESC;

-- Q09 | Does bundling add-ons reduce churn?
SELECT addon_count,
       COUNT(*)                                  AS customers,
       ROUND(100.0 * AVG(1.0 * churn_flag), 2)   AS churn_rate_pct,
       ROUND(AVG(monthly_charges), 0)            AS avg_charge
FROM customers
GROUP BY addon_count
ORDER BY addon_count;

-- Q10 | Churn by acquisition channel (quality of acquisition)
SELECT acquisition_channel,
       COUNT(*)                                  AS customers,
       ROUND(100.0 * AVG(1.0 * churn_flag), 2)   AS churn_rate_pct,
       ROUND(AVG(tenure_months), 1)              AS avg_tenure
FROM customers
GROUP BY acquisition_channel
ORDER BY churn_rate_pct DESC;

-- Q11 | Monthly churn rate = churned in month / subscribers at start of month
WITH months AS (
    SELECT DISTINCT bill_month, bill_period FROM billing
),
movement AS (
    SELECT m.bill_month,
           SUM(CASE WHEN c.join_period < m.bill_period
                     AND (c.churn_period IS NULL OR c.churn_period >= m.bill_period) THEN 1 ELSE 0 END) AS opening_subs,
           SUM(CASE WHEN c.join_period  = m.bill_period THEN 1 ELSE 0 END)                             AS new_subs,
           SUM(CASE WHEN c.churn_period = m.bill_period THEN 1 ELSE 0 END)                             AS churned_subs
    FROM months m CROSS JOIN customers c
    GROUP BY m.bill_month
)
SELECT bill_month,
       opening_subs,
       new_subs,
       churned_subs,
       new_subs - churned_subs                                          AS net_adds,
       ROUND(100.0 * churned_subs / NULLIF(opening_subs, 0), 2)         AS monthly_churn_rate_pct
FROM movement
ORDER BY bill_month;

-- Q12 | Tariff-hike impact: churn before vs after July-2024 (mobile only)
SELECT CASE WHEN churn_month <  '2024-07-01' THEN '1. Pre-hike (Feb-Jun 24)'
            WHEN churn_month <= '2024-09-01' THEN '2. Hike window (Jul-Sep 24)'
            ELSE '3. Post-hike (Oct 24 onward)' END                    AS period,
       COUNT(*)                                                         AS churned,
       ROUND(1.0 * COUNT(*) / COUNT(DISTINCT churn_month), 1)           AS avg_churn_per_month,
       ROUND(100.0 * SUM(CASE WHEN churn_reason = 'Price / Tariff Hike' THEN 1 ELSE 0 END) / COUNT(*), 1) AS price_reason_pct
FROM customers
WHERE churn_flag = 1 AND service_type <> 'Fiber Broadband'
GROUP BY CASE WHEN churn_month <  '2024-07-01' THEN '1. Pre-hike (Feb-Jun 24)'
              WHEN churn_month <= '2024-09-01' THEN '2. Hike window (Jul-Sep 24)'
              ELSE '3. Post-hike (Oct 24 onward)' END
ORDER BY period;


-- =====================================================================
--  SECTION C : REVENUE INTELLIGENCE
-- =====================================================================

-- Q13 | Monthly MRR, MoM growth (LAG) and running revenue total
WITH m AS (
    SELECT bill_month,
           SUM(amount_billed)            AS mrr,
           COUNT(DISTINCT customer_id)   AS billed_subs
    FROM billing
    GROUP BY bill_month
)
SELECT bill_month,
       ROUND(mrr, 0)                                                              AS mrr,
       billed_subs,
       ROUND(mrr / billed_subs, 2)                                                AS arpu,
       ROUND(100.0 * (mrr - LAG(mrr) OVER (ORDER BY bill_month))
             / LAG(mrr) OVER (ORDER BY bill_month), 2)                            AS mom_growth_pct,
       ROUND(SUM(mrr) OVER (ORDER BY bill_month ROWS UNBOUNDED PRECEDING), 0)     AS running_revenue
FROM m
ORDER BY bill_month;

-- Q14 | Year-over-year revenue & ARPU by service type
SELECT c.service_type,
       ROUND(SUM(CASE WHEN b.bill_month <  '2025-01-01' THEN b.amount_billed ELSE 0 END), 0) AS revenue_2024,
       ROUND(SUM(CASE WHEN b.bill_month >= '2025-01-01' THEN b.amount_billed ELSE 0 END), 0) AS revenue_2025,
       ROUND(100.0 * (SUM(CASE WHEN b.bill_month >= '2025-01-01' THEN b.amount_billed ELSE 0 END)
                    - SUM(CASE WHEN b.bill_month <  '2025-01-01' THEN b.amount_billed ELSE 0 END))
             / SUM(CASE WHEN b.bill_month < '2025-01-01' THEN b.amount_billed ELSE 0 END), 1)     AS yoy_growth_pct,
       ROUND(AVG(b.amount_billed), 0)                                                          AS arpu
FROM billing b
JOIN customers c ON c.customer_id = b.customer_id
GROUP BY c.service_type
ORDER BY revenue_2025 DESC;

-- Q15 | Revenue by circle with share and rank
SELECT c.circle,
       ROUND(SUM(b.amount_billed), 0)                                             AS revenue,
       ROUND(100.0 * SUM(b.amount_billed) / SUM(SUM(b.amount_billed)) OVER (), 2) AS revenue_share_pct,
       DENSE_RANK() OVER (ORDER BY SUM(b.amount_billed) DESC)                     AS revenue_rank
FROM billing b
JOIN customers c ON c.customer_id = b.customer_id
GROUP BY c.circle
ORDER BY revenue_rank;

-- Q16 | Plan performance - revenue, subscribers, churn
SELECT p.plan_id,
       p.plan_name,
       p.plan_tier,
       COUNT(DISTINCT c.customer_id)                                   AS customers,
       ROUND(100.0 * AVG(1.0 * c.churn_flag), 2)                       AS churn_rate_pct,
       ROUND(SUM(c.total_charges), 0)                                  AS lifetime_revenue
FROM plans p
JOIN customers c ON c.plan_id = p.plan_id
GROUP BY p.plan_id, p.plan_name, p.plan_tier
ORDER BY lifetime_revenue DESC;

-- Q17 | MRR lost to churn per month and cumulative revenue leakage
WITH lost AS (
    SELECT churn_month,
           COUNT(*)              AS churned_customers,
           SUM(monthly_charges)  AS mrr_lost
    FROM customers
    WHERE churn_flag = 1
    GROUP BY churn_month
)
SELECT churn_month,
       churned_customers,
       ROUND(mrr_lost, 0)                                                         AS mrr_lost,
       ROUND(SUM(mrr_lost) OVER (ORDER BY churn_month ROWS UNBOUNDED PRECEDING), 0) AS cumulative_mrr_lost,
       ROUND(mrr_lost * 12, 0)                                                    AS annualised_loss
FROM lost
ORDER BY churn_month;

-- Q18 | Revenue concentration (Pareto) - revenue share by customer decile
WITH cust_rev AS (
    SELECT customer_id, SUM(amount_billed) AS revenue
    FROM billing
    GROUP BY customer_id
),
dec AS (
    SELECT customer_id, revenue, NTILE(10) OVER (ORDER BY revenue DESC) AS decile
    FROM cust_rev
)
SELECT decile,
       COUNT(*)                                                                    AS customers,
       ROUND(SUM(revenue), 0)                                                      AS revenue,
       ROUND(100.0 * SUM(revenue) / SUM(SUM(revenue)) OVER (), 2)                  AS revenue_share_pct,
       ROUND(100.0 * SUM(SUM(revenue)) OVER (ORDER BY decile ROWS UNBOUNDED PRECEDING)
             / SUM(SUM(revenue)) OVER (), 2)                                       AS cumulative_share_pct
FROM dec
GROUP BY decile
ORDER BY decile;

-- Q19 | Customer lifetime value by segment (ARPU x margin x expected lifetime)
WITH expo AS (
    SELECT customer_id, COUNT(*) AS billed_months
    FROM billing
    GROUP BY customer_id
),
seg AS (
    SELECT c.service_type,
           c.contract_type,
           COUNT(*)                 AS customers,
           SUM(c.churn_flag)        AS churners,
           AVG(c.monthly_charges)   AS arpu,
           SUM(e.billed_months)     AS exposure_months
    FROM customers c
    JOIN expo e ON e.customer_id = c.customer_id
    GROUP BY c.service_type, c.contract_type
)
SELECT service_type,
       contract_type,
       customers,
       ROUND(arpu, 0)                                                           AS arpu,
       ROUND(100.0 * churners / exposure_months, 2)                             AS monthly_churn_pct,
       ROUND(CASE WHEN 1.0 * exposure_months / churners > 120 THEN 120
                  ELSE 1.0 * exposure_months / churners END, 1)                 AS expected_life_months,
       ROUND(arpu * 0.40 * CASE WHEN 1.0 * exposure_months / churners > 120 THEN 120
                                ELSE 1.0 * exposure_months / churners END, 0)   AS clv_gross_margin
FROM seg
ORDER BY clv_gross_margin DESC;

-- Q20 | Chronic late payers (3+ late invoices in last 6 months) - collections watch-list
SELECT b.customer_id,
       c.circle,
       c.service_type,
       c.monthly_charges,
       SUM(CASE WHEN b.payment_status = 'Paid Late' THEN 1 ELSE 0 END)  AS late_invoices_6m,
       ROUND(AVG(CASE WHEN b.days_late > 0 THEN b.days_late END), 1)     AS avg_days_late
FROM billing b
JOIN customers c ON c.customer_id = b.customer_id
WHERE b.bill_month >= '2025-07-01' AND c.churn_flag = 0
GROUP BY b.customer_id, c.circle, c.service_type, c.monthly_charges
HAVING SUM(CASE WHEN b.payment_status = 'Paid Late' THEN 1 ELSE 0 END) >= 3
ORDER BY late_invoices_6m DESC, c.monthly_charges DESC;


-- =====================================================================
--  SECTION D : CUSTOMER EXPERIENCE & NETWORK
-- =====================================================================

-- Q21 | Ticket volume, resolution time and CSAT by category
SELECT category,
       COUNT(*)                                                        AS tickets,
       ROUND(AVG(resolution_hours), 1)                                 AS avg_resolution_hrs,
       ROUND(100.0 * AVG(1.0 * resolved_flag), 1)                      AS resolution_rate_pct,
       ROUND(AVG(1.0 * csat_score), 2)                                 AS avg_csat
FROM support_tickets
GROUP BY category
ORDER BY tickets DESC;

-- Q22 | Churn rate by customer CSAT bucket
WITH cs AS (
    SELECT customer_id, AVG(1.0 * csat_score) AS avg_csat, COUNT(*) AS tickets
    FROM support_tickets
    GROUP BY customer_id
)
SELECT CASE WHEN cs.avg_csat IS NULL THEN '0. No rated tickets'
            WHEN cs.avg_csat < 2.5 THEN '1. Detractor (<2.5)'
            WHEN cs.avg_csat < 3.5 THEN '2. Passive (2.5-3.5)'
            ELSE '3. Promoter (3.5+)' END                              AS csat_bucket,
       COUNT(*)                                                        AS customers,
       ROUND(100.0 * AVG(1.0 * c.churn_flag), 2)                       AS churn_rate_pct
FROM customers c
LEFT JOIN cs ON cs.customer_id = c.customer_id
GROUP BY CASE WHEN cs.avg_csat IS NULL THEN '0. No rated tickets'
              WHEN cs.avg_csat < 2.5 THEN '1. Detractor (<2.5)'
              WHEN cs.avg_csat < 3.5 THEN '2. Passive (2.5-3.5)'
              ELSE '3. Promoter (3.5+)' END
ORDER BY csat_bucket;

-- Q23 | Network quality vs churn by circle
WITH nq AS (
    SELECT customer_id,
           AVG(call_drop_rate_pct) AS drop_rate,
           AVG(avg_speed_mbps)     AS speed
    FROM network_usage
    GROUP BY customer_id
)
SELECT c.circle,
       ROUND(AVG(nq.drop_rate), 2)                AS avg_call_drop_pct,
       ROUND(AVG(nq.speed), 1)                    AS avg_speed_mbps,
       ROUND(100.0 * AVG(1.0 * c.churn_flag), 2)  AS churn_rate_pct
FROM customers c
JOIN nq ON nq.customer_id = c.customer_id
GROUP BY c.circle
ORDER BY avg_call_drop_pct DESC;

-- Q24 | Support channel efficiency
SELECT channel,
       COUNT(*)                                     AS tickets,
       ROUND(AVG(resolution_hours), 1)              AS avg_resolution_hrs,
       ROUND(AVG(1.0 * csat_score), 2)              AS avg_csat
FROM support_tickets
GROUP BY channel
ORDER BY tickets DESC;


-- =====================================================================
--  SECTION E : COHORT & SEGMENTATION
-- =====================================================================

-- Q25 | Quarterly cohort retention at 3 / 6 / 12 months
SELECT cohort_quarter                                                              AS cohort,
       COUNT(*)                                                                    AS cohort_size,
       ROUND(100.0 * AVG(CASE WHEN churn_period IS NULL OR churn_period > join_period + 3  THEN 1.0 ELSE 0 END), 1) AS retained_m3_pct,
       ROUND(100.0 * AVG(CASE WHEN churn_period IS NULL OR churn_period > join_period + 6  THEN 1.0 ELSE 0 END), 1) AS retained_m6_pct,
       ROUND(100.0 * AVG(CASE WHEN churn_period IS NULL OR churn_period > join_period + 12 THEN 1.0 ELSE 0 END), 1) AS retained_m12_pct
FROM customers
WHERE join_month >= '2024-01-01'
GROUP BY cohort_quarter
ORDER BY cohort_quarter;

-- Q26 | Value-based segmentation with NTILE (tenure x spend quartiles)
WITH scored AS (
    SELECT customer_id, churn_flag, monthly_charges, tenure_months,
           NTILE(4) OVER (ORDER BY monthly_charges) AS spend_q,
           NTILE(4) OVER (ORDER BY tenure_months)   AS tenure_q
    FROM customers
)
SELECT CASE WHEN spend_q >= 3 AND tenure_q >= 3 THEN '1. Champions (high spend, loyal)'
            WHEN spend_q >= 3 AND tenure_q <= 2 THEN '2. High-value at risk (high spend, new)'
            WHEN spend_q <= 2 AND tenure_q >= 3 THEN '3. Loyal value seekers'
            ELSE '4. Low-value new' END                     AS segment,
       COUNT(*)                                             AS customers,
       ROUND(AVG(monthly_charges), 0)                       AS avg_charge,
       ROUND(AVG(tenure_months), 1)                         AS avg_tenure,
       ROUND(100.0 * AVG(1.0 * churn_flag), 2)              AS churn_rate_pct
FROM scored
GROUP BY CASE WHEN spend_q >= 3 AND tenure_q >= 3 THEN '1. Champions (high spend, loyal)'
              WHEN spend_q >= 3 AND tenure_q <= 2 THEN '2. High-value at risk (high spend, new)'
              WHEN spend_q <= 2 AND tenure_q >= 3 THEN '3. Loyal value seekers'
              ELSE '4. Low-value new' END
ORDER BY segment;

-- Q27 | Usage decline early-warning: active customers whose last-2-month data fell >30% vs their average
WITH u AS (
    SELECT customer_id, usage_month, data_used_gb,
           ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY usage_month DESC) AS rn
    FROM network_usage
),
agg AS (
    SELECT customer_id,
           AVG(CASE WHEN rn <= 2 THEN data_used_gb END)  AS recent_gb,
           AVG(CASE WHEN rn >  2 THEN data_used_gb END)  AS baseline_gb,
           COUNT(*)                                      AS months
    FROM u
    GROUP BY customer_id
)
SELECT a.customer_id, c.circle, c.service_type, c.monthly_charges,
       ROUND(a.baseline_gb, 1)                                  AS baseline_gb,
       ROUND(a.recent_gb, 1)                                    AS recent_gb,
       ROUND(100.0 * (a.recent_gb - a.baseline_gb) / a.baseline_gb, 1) AS usage_change_pct
FROM agg a
JOIN customers c ON c.customer_id = a.customer_id
WHERE c.churn_flag = 0 AND a.months >= 6
  AND a.recent_gb < 0.7 * a.baseline_gb
ORDER BY usage_change_pct;


-- =====================================================================
--  SECTION F : PREDICTIVE RISK (ML output joined back to SQL)
-- =====================================================================

-- Q28 | Revenue at risk by risk tier
SELECT risk_tier,
       COUNT(*)                                                         AS customers,
       ROUND(AVG(churn_probability), 3)                                 AS avg_churn_prob,
       ROUND(SUM(annual_revenue), 0)                                    AS annual_revenue,
       ROUND(SUM(revenue_at_risk), 0)                                   AS revenue_at_risk,
       ROUND(100.0 * SUM(revenue_at_risk) / SUM(SUM(revenue_at_risk)) OVER (), 1) AS risk_share_pct
FROM churn_predictions
GROUP BY risk_tier
ORDER BY avg_churn_prob DESC;

-- Q29 | Top 3 highest revenue-at-risk customers in every circle (retention call list)
WITH ranked AS (
    SELECT customer_id, circle, plan_name, contract_type, monthly_charges,
           churn_probability, revenue_at_risk, next_best_action,
           ROW_NUMBER() OVER (PARTITION BY circle ORDER BY revenue_at_risk DESC) AS rn
    FROM churn_predictions
    WHERE risk_tier = 'High'
)
SELECT circle, rn AS priority, customer_id, plan_name, contract_type, monthly_charges,
       churn_probability, revenue_at_risk, next_best_action
FROM ranked
WHERE rn <= 3
ORDER BY circle, rn;

-- Q30 | Retention playbook sizing - next-best-action summary for High & Medium risk
SELECT next_best_action,
       COUNT(*)                                       AS customers,
       ROUND(SUM(revenue_at_risk), 0)                 AS revenue_at_risk,
       ROUND(AVG(churn_probability), 3)               AS avg_churn_prob,
       ROUND(0.30 * SUM(revenue_at_risk) * 0.40 - 300 * COUNT(*), 0) AS est_net_benefit
FROM churn_predictions
WHERE risk_tier IN ('High', 'Medium')
GROUP BY next_best_action
ORDER BY revenue_at_risk DESC;
