-- =====================================================================
--  04_views_for_powerbi.sql  -  Semantic views consumed by Power BI
--  (Power BI > Get Data > MySQL database > select these views)
-- =====================================================================

USE telecom_churn_db;

-- ---------------------------------------------------------------------
-- Customer 360: one row per customer with billing, support, network & ML score
-- ---------------------------------------------------------------------
CREATE VIEW vw_customer_360 AS
WITH bill AS (
    SELECT customer_id,
           SUM(amount_billed)                                               AS lifetime_billed,
           SUM(amount_paid)                                                 AS lifetime_paid,
           SUM(CASE WHEN payment_status = 'Paid Late' THEN 1 ELSE 0 END)    AS late_invoices,
           COUNT(*)                                                         AS billed_months
    FROM billing
    GROUP BY customer_id
),
tkt AS (
    SELECT customer_id,
           COUNT(*)                     AS tickets,
           AVG(1.0 * csat_score)        AS avg_csat,
           AVG(resolution_hours)        AS avg_resolution_hrs
    FROM support_tickets
    GROUP BY customer_id
),
net AS (
    SELECT customer_id,
           AVG(data_used_gb)            AS avg_data_gb,
           AVG(call_drop_rate_pct)      AS avg_drop_rate,
           AVG(avg_speed_mbps)          AS avg_speed
    FROM network_usage
    GROUP BY customer_id
)
SELECT c.customer_id, c.gender, c.age_band, c.circle, c.city, c.city_tier,
       c.service_type, c.plan_id, p.plan_name, p.plan_tier, c.network_type, c.contract_type,
       c.payment_method, c.acquisition_channel, c.tenure_months, c.tenure_band,
       c.monthly_charges, c.addon_count, c.churn_flag,
       CASE WHEN c.churn_flag = 1 THEN 'Churned' ELSE 'Active' END   AS customer_status,
       c.churn_month, c.churn_reason,
       b.lifetime_billed, b.lifetime_paid, b.late_invoices, b.billed_months,
       COALESCE(t.tickets, 0)                                         AS tickets,
       t.avg_csat, t.avg_resolution_hrs,
       n.avg_data_gb, n.avg_drop_rate, n.avg_speed,
       cp.churn_probability, cp.risk_tier, cp.revenue_at_risk, cp.predicted_clv, cp.next_best_action
FROM customers c
JOIN plans p              ON p.plan_id = c.plan_id
LEFT JOIN bill b          ON b.customer_id = c.customer_id
LEFT JOIN tkt t           ON t.customer_id = c.customer_id
LEFT JOIN net n           ON n.customer_id = c.customer_id
LEFT JOIN churn_predictions cp ON cp.customer_id = c.customer_id;

-- ---------------------------------------------------------------------
-- Monthly KPI trend
-- ---------------------------------------------------------------------
CREATE VIEW vw_monthly_kpis AS
WITH months AS (
    SELECT bill_month, bill_period,
           SUM(amount_billed)            AS mrr,
           SUM(amount_paid)              AS collected,
           COUNT(DISTINCT customer_id)   AS billed_subs
    FROM billing
    GROUP BY bill_month, bill_period
)
SELECT m.bill_month,
       m.mrr,
       m.collected,
       m.billed_subs,
       m.mrr / m.billed_subs                                                                AS arpu,
       SUM(CASE WHEN c.join_period < m.bill_period
                 AND (c.churn_period IS NULL OR c.churn_period >= m.bill_period) THEN 1 ELSE 0 END) AS opening_subs,
       SUM(CASE WHEN c.join_period  = m.bill_period THEN 1 ELSE 0 END)                      AS new_subs,
       SUM(CASE WHEN c.churn_period = m.bill_period THEN 1 ELSE 0 END)                      AS churned_subs,
       SUM(CASE WHEN c.churn_period = m.bill_period THEN c.monthly_charges ELSE 0 END)      AS churned_mrr
FROM months m
CROSS JOIN customers c
GROUP BY m.bill_month, m.bill_period, m.mrr, m.collected, m.billed_subs;

-- ---------------------------------------------------------------------
-- Churn by segment (unpivoted for a single slicer-driven visual)
-- ---------------------------------------------------------------------
CREATE VIEW vw_churn_by_segment AS
SELECT 'Contract' AS dimension, contract_type AS segment, COUNT(*) AS customers,
       SUM(churn_flag) AS churned, 1.0 * SUM(churn_flag) / COUNT(*) AS churn_rate
FROM customers GROUP BY contract_type
UNION ALL
SELECT 'Tenure', tenure_band, COUNT(*), SUM(churn_flag), 1.0 * SUM(churn_flag) / COUNT(*)
FROM customers GROUP BY tenure_band
UNION ALL
SELECT 'Circle', circle, COUNT(*), SUM(churn_flag), 1.0 * SUM(churn_flag) / COUNT(*)
FROM customers GROUP BY circle
UNION ALL
SELECT 'Service', service_type, COUNT(*), SUM(churn_flag), 1.0 * SUM(churn_flag) / COUNT(*)
FROM customers GROUP BY service_type
UNION ALL
SELECT 'Payment', payment_method, COUNT(*), SUM(churn_flag), 1.0 * SUM(churn_flag) / COUNT(*)
FROM customers GROUP BY payment_method;

-- ---------------------------------------------------------------------
-- Revenue by circle x month
-- ---------------------------------------------------------------------
CREATE VIEW vw_revenue_circle_month AS
SELECT b.bill_month, c.circle, c.service_type,
       SUM(b.amount_billed)          AS revenue,
       SUM(b.amount_paid)            AS collected,
       COUNT(DISTINCT b.customer_id) AS subscribers
FROM billing b
JOIN customers c ON c.customer_id = b.customer_id
GROUP BY b.bill_month, c.circle, c.service_type;

-- ---------------------------------------------------------------------
-- High-risk retention list
-- ---------------------------------------------------------------------
CREATE VIEW vw_high_risk_customers AS
SELECT cp.*, c.payment_method, c.acquisition_channel, c.network_type
FROM churn_predictions cp
JOIN customers c ON c.customer_id = cp.customer_id
WHERE cp.risk_tier IN ('High', 'Medium');

-- ---------------------------------------------------------------------
-- Support summary by month & category
-- ---------------------------------------------------------------------
CREATE VIEW vw_support_summary AS
SELECT SUBSTR(CAST(ticket_date AS CHAR(10)), 1, 7)  AS ticket_month,
       category, channel,
       COUNT(*)                         AS tickets,
       AVG(resolution_hours)            AS avg_resolution_hrs,
       AVG(1.0 * csat_score)            AS avg_csat,
       SUM(resolved_flag)               AS resolved
FROM support_tickets
GROUP BY SUBSTR(CAST(ticket_date AS CHAR(10)), 1, 7), category, channel;
