-- =====================================================================
--  02b_load_data_server.sql  -  Use this if 02_load_data.sql gives Error 2068
--  Server-side load (no LOCAL keyword) - works without OPT_LOCAL_INFILE.
--
--  STEP 1: Run this to see the allowed folder:
--          SHOW VARIABLES LIKE 'secure_file_priv';
--          (default: C:\ProgramData\MySQL\MySQL Server 8.0\Uploads\)
--  STEP 2: Copy the 6 CSV files from  sql\load\  into that folder.
--  STEP 3: Run this whole file (Ctrl+A, then the lightning icon).
--  If secure_file_priv shows a different folder, replace the path below.
-- =====================================================================

USE telecom_churn_db;
SHOW VARIABLES LIKE 'secure_file_priv';

LOAD DATA INFILE 'C:/ProgramData/MySQL/MySQL Server 8.0/Uploads/plans.csv'
INTO TABLE plans
FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 ROWS;

LOAD DATA INFILE 'C:/ProgramData/MySQL/MySQL Server 8.0/Uploads/customers.csv'
INTO TABLE customers
FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 ROWS
(customer_id, gender, age, age_band, senior_citizen, partner, dependents, circle, city, city_tier,
 join_date, join_month, join_period, cohort_quarter, acquisition_channel, service_type, plan_id, network_type, contract_type,
 payment_method, paperless_billing, ott_bundle, device_protection, intl_roaming, priority_support,
 multi_line, addon_count, discount_pct, monthly_charges, charge_band, tenure_months, tenure_band,
 total_charges, avg_monthly_data_gb, churn_flag, @churn_date, @churn_month, @churn_period, @churn_reason)
SET churn_date   = NULLIF(@churn_date, ''),
    churn_month  = NULLIF(@churn_month, ''),
    churn_period = NULLIF(@churn_period, ''),
    churn_reason = NULLIF(@churn_reason, '');

LOAD DATA INFILE 'C:/ProgramData/MySQL/MySQL Server 8.0/Uploads/billing.csv'
INTO TABLE billing
FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 ROWS;

LOAD DATA INFILE 'C:/ProgramData/MySQL/MySQL Server 8.0/Uploads/support_tickets.csv'
INTO TABLE support_tickets
FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 ROWS
(ticket_id, customer_id, ticket_date, category, channel, resolution_hours, resolved, @csat, resolved_flag)
SET csat_score = NULLIF(@csat, '');

LOAD DATA INFILE 'C:/ProgramData/MySQL/MySQL Server 8.0/Uploads/network_usage.csv'
INTO TABLE network_usage
FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 ROWS;

LOAD DATA INFILE 'C:/ProgramData/MySQL/MySQL Server 8.0/Uploads/churn_predictions.csv'
INTO TABLE churn_predictions
FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 ROWS;

-- Row-count reconciliation (expected values printed by python/07_load_sql.py)
SELECT 'plans' AS tbl, COUNT(*) AS rows_loaded FROM plans
UNION ALL SELECT 'customers', COUNT(*) FROM customers
UNION ALL SELECT 'billing', COUNT(*) FROM billing
UNION ALL SELECT 'support_tickets', COUNT(*) FROM support_tickets
UNION ALL SELECT 'network_usage', COUNT(*) FROM network_usage
UNION ALL SELECT 'churn_predictions', COUNT(*) FROM churn_predictions;
