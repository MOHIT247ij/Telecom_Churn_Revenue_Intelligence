-- =====================================================================
--  05_mysql_procedures.sql  -  MySQL 8 only (stored procedures, function, trigger)
--  Run in MySQL Workbench / CLI. DELIMITER is required for multi-statement bodies.
-- =====================================================================

USE telecom_churn_db;

-- ---------------------------------------------------------------------
-- 1. Function: risk tier from probability
-- ---------------------------------------------------------------------
DROP FUNCTION IF EXISTS fn_risk_tier;
DELIMITER $$
CREATE FUNCTION fn_risk_tier(p DECIMAL(6,4))
RETURNS VARCHAR(10) DETERMINISTIC
BEGIN
    -- cut-offs = profit-optimal threshold (0.36) and high-risk cut (0.56) from outputs/reports/final_model_metrics.csv
    RETURN CASE WHEN p >= 0.56 THEN 'High'
                WHEN p >= 0.36 THEN 'Medium'
                ELSE 'Low' END;
END$$
DELIMITER ;

-- ---------------------------------------------------------------------
-- 2. Procedure: churn KPIs for any circle and date range
--    CALL sp_circle_churn_report('Uttar Pradesh', '2024-01-01', '2025-12-01');
-- ---------------------------------------------------------------------
DROP PROCEDURE IF EXISTS sp_circle_churn_report;
DELIMITER $$
CREATE PROCEDURE sp_circle_churn_report(IN p_circle VARCHAR(30), IN p_from DATE, IN p_to DATE)
BEGIN
    SELECT c.circle,
           COUNT(*)                                        AS churned_customers,
           ROUND(SUM(c.monthly_charges), 0)                AS mrr_lost,
           ROUND(SUM(c.monthly_charges) * 12, 0)           AS annualised_loss
    FROM customers c
    WHERE c.churn_flag = 1
      AND c.circle = p_circle
      AND c.churn_month BETWEEN p_from AND p_to
    GROUP BY c.circle;

    SELECT c.churn_reason, COUNT(*) AS churned
    FROM customers c
    WHERE c.churn_flag = 1 AND c.circle = p_circle
      AND c.churn_month BETWEEN p_from AND p_to
    GROUP BY c.churn_reason
    ORDER BY churned DESC;
END$$
DELIMITER ;

-- ---------------------------------------------------------------------
-- 3. Procedure: customer 360 lookup for call-centre agents
--    CALL sp_customer_profile('CUST100123');
-- ---------------------------------------------------------------------
DROP PROCEDURE IF EXISTS sp_customer_profile;
DELIMITER $$
CREATE PROCEDURE sp_customer_profile(IN p_customer VARCHAR(12))
BEGIN
    SELECT * FROM vw_customer_360 WHERE customer_id = p_customer;

    SELECT bill_month, amount_billed, amount_paid, payment_status, days_late
    FROM billing WHERE customer_id = p_customer
    ORDER BY bill_month DESC LIMIT 6;

    SELECT ticket_date, category, resolution_hours, csat_score
    FROM support_tickets WHERE customer_id = p_customer
    ORDER BY ticket_date DESC LIMIT 5;
END$$
DELIMITER ;

-- ---------------------------------------------------------------------
-- 4. Audit table + trigger: log every churn-status change
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS churn_audit_log (
    audit_id      INT AUTO_INCREMENT PRIMARY KEY,
    customer_id   VARCHAR(12),
    old_flag      INT,
    new_flag      INT,
    churn_reason  VARCHAR(40),
    changed_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

DROP TRIGGER IF EXISTS trg_churn_audit;
DELIMITER $$
CREATE TRIGGER trg_churn_audit
AFTER UPDATE ON customers
FOR EACH ROW
BEGIN
    IF OLD.churn_flag <> NEW.churn_flag THEN
        INSERT INTO churn_audit_log (customer_id, old_flag, new_flag, churn_reason)
        VALUES (NEW.customer_id, OLD.churn_flag, NEW.churn_flag, NEW.churn_reason);
    END IF;
END$$
DELIMITER ;

-- ---------------------------------------------------------------------
-- 5. Monthly refresh procedure: re-tier predictions after a new model run
-- ---------------------------------------------------------------------
DROP PROCEDURE IF EXISTS sp_refresh_risk_tiers;
DELIMITER $$
CREATE PROCEDURE sp_refresh_risk_tiers()
BEGIN
    UPDATE churn_predictions
       SET risk_tier       = fn_risk_tier(churn_probability),
           revenue_at_risk = ROUND(annual_revenue * churn_probability, 2);
    SELECT risk_tier, COUNT(*) AS customers, ROUND(SUM(revenue_at_risk), 0) AS revenue_at_risk
    FROM churn_predictions GROUP BY risk_tier;
END$$
DELIMITER ;
