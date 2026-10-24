-- =====================================================================
--  Telecom Customer Churn & Revenue Intelligence
--  01_schema.sql  -  Database schema (OLTP-style normalised model)
--  Target: MySQL 8.0+  (also runs unchanged on SQLite / PostgreSQL)
-- =====================================================================
-- =====================================================================

CREATE DATABASE IF NOT EXISTS telecom_churn_db;
USE telecom_churn_db;

DROP VIEW IF EXISTS vw_customer_360;
DROP VIEW IF EXISTS vw_monthly_kpis;
DROP VIEW IF EXISTS vw_churn_by_segment;
DROP VIEW IF EXISTS vw_revenue_circle_month;
DROP VIEW IF EXISTS vw_high_risk_customers;
DROP VIEW IF EXISTS vw_support_summary;

DROP TABLE IF EXISTS churn_predictions;
DROP TABLE IF EXISTS network_usage;
DROP TABLE IF EXISTS support_tickets;
DROP TABLE IF EXISTS billing;
DROP TABLE IF EXISTS customers;
DROP TABLE IF EXISTS plans;

-- ---------------------------------------------------------------------
-- Plan catalogue
-- ---------------------------------------------------------------------
CREATE TABLE plans (
    plan_id         VARCHAR(10)   NOT NULL PRIMARY KEY,
    plan_name       VARCHAR(60)   NOT NULL,
    service_type    VARCHAR(30)   NOT NULL,      -- Prepaid Mobile / Postpaid Mobile / Fiber Broadband
    monthly_fee     DECIMAL(10,2) NOT NULL,
    data_gb_limit   INT,
    voice_benefit   VARCHAR(30),
    plan_tier       VARCHAR(10)                  -- Value / Mid / Premium
);

-- ---------------------------------------------------------------------
-- Customer master (one row per subscriber, snapshot as of 31-Dec-2025)
-- ---------------------------------------------------------------------
CREATE TABLE customers (
    customer_id          VARCHAR(12)   NOT NULL PRIMARY KEY,
    gender               VARCHAR(10),
    age                  INT,
    age_band             VARCHAR(10),
    senior_citizen       INT,
    partner              VARCHAR(3),
    dependents           VARCHAR(3),
    circle               VARCHAR(30),
    city                 VARCHAR(30),
    city_tier            VARCHAR(10),
    join_date            DATE,
    join_month           DATE,                   -- first day of joining month (cohort key)
    join_period          INT,                    -- year*12 + month  (portable month arithmetic)
    cohort_quarter       VARCHAR(7),             -- e.g. 2024-Q3
    acquisition_channel  VARCHAR(30),
    service_type         VARCHAR(30),
    plan_id              VARCHAR(10),
    network_type         VARCHAR(10),
    contract_type        VARCHAR(30),
    payment_method       VARCHAR(30),
    paperless_billing    VARCHAR(3),
    ott_bundle           VARCHAR(3),
    device_protection    VARCHAR(3),
    intl_roaming         VARCHAR(3),
    priority_support     VARCHAR(3),
    multi_line           VARCHAR(3),
    addon_count          INT,
    discount_pct         DECIMAL(5,2),
    monthly_charges      DECIMAL(10,2),
    charge_band          VARCHAR(12),
    tenure_months        INT,
    tenure_band          VARCHAR(10),
    total_charges        DECIMAL(12,2),
    avg_monthly_data_gb  DECIMAL(10,2),
    churn_flag           INT           NOT NULL,  -- 1 = churned
    churn_date           DATE,
    churn_month          DATE,                    -- first day of churn month
    churn_period         INT,                     -- year*12 + month, NULL if active
    churn_reason         VARCHAR(40),
    FOREIGN KEY (plan_id) REFERENCES plans(plan_id)
);

-- ---------------------------------------------------------------------
-- Monthly invoices
-- ---------------------------------------------------------------------
CREATE TABLE billing (
    invoice_id      VARCHAR(12)   NOT NULL PRIMARY KEY,
    customer_id     VARCHAR(12)   NOT NULL,
    bill_month      DATE          NOT NULL,
    bill_period     INT           NOT NULL,       -- year*12 + month
    amount_billed   DECIMAL(10,2) NOT NULL,
    amount_paid     DECIMAL(10,2) NOT NULL,
    outstanding     DECIMAL(10,2),
    payment_status  VARCHAR(15),                  -- Paid On Time / Paid Late / Unpaid
    days_late       INT,                          -- -1 = unpaid
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
);

-- ---------------------------------------------------------------------
-- Customer-care tickets
-- ---------------------------------------------------------------------
CREATE TABLE support_tickets (
    ticket_id         VARCHAR(12)  NOT NULL PRIMARY KEY,
    customer_id       VARCHAR(12)  NOT NULL,
    ticket_date       DATE         NOT NULL,
    category          VARCHAR(40),
    channel           VARCHAR(20),
    resolution_hours  DECIMAL(8,1),
    resolved          VARCHAR(3),
    csat_score        INT,                        -- 1-5, NULL when unresolved
    resolved_flag     INT,
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
);

-- ---------------------------------------------------------------------
-- Monthly usage & network-quality KPIs
-- ---------------------------------------------------------------------
CREATE TABLE network_usage (
    customer_id         VARCHAR(12)   NOT NULL,
    usage_month         DATE          NOT NULL,
    data_used_gb        DECIMAL(10,2),
    voice_minutes       INT,
    call_drop_rate_pct  DECIMAL(6,2),
    avg_speed_mbps      DECIMAL(8,1),
    PRIMARY KEY (customer_id, usage_month),
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
);

-- ---------------------------------------------------------------------
-- ML output: churn scores for ACTIVE customers (written by Python)
-- ---------------------------------------------------------------------
CREATE TABLE churn_predictions (
    customer_id         VARCHAR(12)   NOT NULL PRIMARY KEY,
    circle              VARCHAR(30),
    city                VARCHAR(30),
    service_type        VARCHAR(30),
    plan_name           VARCHAR(60),
    contract_type       VARCHAR(30),
    tenure_months       INT,
    monthly_charges     DECIMAL(10,2),
    avg_drop_rate       DECIMAL(6,3),
    tickets_per_month   DECIMAL(6,3),
    avg_csat            DECIMAL(4,2),
    late_payment_ratio  DECIMAL(6,4),
    churn_probability   DECIMAL(6,4),
    risk_tier           VARCHAR(10),
    annual_revenue      DECIMAL(12,2),
    revenue_at_risk     DECIMAL(12,2),
    predicted_clv       DECIMAL(12,2),
    next_best_action    VARCHAR(60),
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
);

-- ---------------------------------------------------------------------
-- Indexes for analytical query performance
-- ---------------------------------------------------------------------
CREATE INDEX idx_cust_circle      ON customers (circle);
CREATE INDEX idx_cust_contract    ON customers (contract_type);
CREATE INDEX idx_cust_churn       ON customers (churn_flag, churn_month);
CREATE INDEX idx_cust_join        ON customers (join_month);
CREATE INDEX idx_bill_cust_month  ON billing (customer_id, bill_month);
CREATE INDEX idx_bill_month       ON billing (bill_month);
CREATE INDEX idx_tkt_cust         ON support_tickets (customer_id);
CREATE INDEX idx_tkt_category     ON support_tickets (category);
CREATE INDEX idx_pred_tier        ON churn_predictions (risk_tier);
