// =====================================================================
//  Power Query (M) scripts
//  Option A: CSV star schema   (powerbi/model_data/*.csv)   <- recommended for portfolio
//  Option B: MySQL views       (sql/04_views_for_powerbi.sql)
//  Home > Transform data > New Source > Blank Query > Advanced Editor > paste
// =====================================================================


// ---------------------------------------------------------------------
// STEP 0 : Parameter   (Manage Parameters > New)  Name: DataFolder  Type: Text
//          Value e.g.  C:\Telecom_Churn_Revenue_Intelligence\powerbi\model_data\
// ---------------------------------------------------------------------


// ---------------------------------------------------------------------
// fnLoadCsv  - reusable function (name the query exactly: fnLoadCsv)
// ---------------------------------------------------------------------
(fileName as text) as table =>
let
    Source   = Csv.Document(File.Contents(DataFolder & fileName),
                            [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true])
in
    Promoted


// ---------------------------------------------------------------------
// dim_customer
// ---------------------------------------------------------------------
let
    Source = fnLoadCsv("dim_customer.csv"),
    Typed  = Table.TransformColumnTypes(Source, {
        {"customer_id", type text}, {"geo_key", type text}, {"gender", type text}, {"age", Int64.Type},
        {"age_band", type text}, {"senior_citizen", Int64.Type}, {"join_date", type date},
        {"service_type", type text}, {"plan_id", type text}, {"contract_type", type text},
        {"payment_method", type text}, {"addon_count", Int64.Type}, {"discount_pct", type number},
        {"monthly_charges", Currency.Type}, {"tenure_months", Int64.Type}, {"churn_flag", Int64.Type},
        {"churn_date", type date}, {"churn_reason", type text}}, "en-IN"),
    // sort helper columns so bands display in logical order (Column tools > Sort by column)
    TenureSort = Table.AddColumn(Typed, "tenure_band_sort", each
        if [tenure_band] = "0-6 M" then 1 else if [tenure_band] = "7-12 M" then 2
        else if [tenure_band] = "13-24 M" then 3 else if [tenure_band] = "25-48 M" then 4 else 5, Int64.Type),
    ChargeSort = Table.AddColumn(TenureSort, "charge_band_sort", each
        if [charge_band] = "< 300" then 1 else if [charge_band] = "300-600" then 2
        else if [charge_band] = "600-1000" then 3 else 4, Int64.Type),
    BlankReason = Table.ReplaceValue(ChargeSort, "", null, Replacer.ReplaceValue, {"churn_reason"})
in
    BlankReason


// ---------------------------------------------------------------------
// fact_billing
// ---------------------------------------------------------------------
let
    Source = fnLoadCsv("fact_billing.csv"),
    Typed  = Table.TransformColumnTypes(Source, {
        {"invoice_id", type text}, {"customer_id", type text}, {"plan_id", type text},
        {"bill_month", type date}, {"amount_billed", Currency.Type}, {"amount_paid", Currency.Type},
        {"outstanding", Currency.Type}, {"payment_status", type text}, {"days_late", Int64.Type}}, "en-IN")
in
    Typed


// ---------------------------------------------------------------------
// fact_usage
// ---------------------------------------------------------------------
let
    Source = fnLoadCsv("fact_usage.csv"),
    Typed  = Table.TransformColumnTypes(Source, {
        {"customer_id", type text}, {"usage_month", type date}, {"data_used_gb", type number},
        {"voice_minutes", Int64.Type}, {"call_drop_rate_pct", type number}, {"avg_speed_mbps", type number}}, "en-IN")
in
    Typed


// ---------------------------------------------------------------------
// fact_tickets
// ---------------------------------------------------------------------
let
    Source = fnLoadCsv("fact_tickets.csv"),
    Typed  = Table.TransformColumnTypes(Source, {
        {"ticket_id", type text}, {"customer_id", type text}, {"ticket_date", type date},
        {"category", type text}, {"channel", type text}, {"resolution_hours", type number},
        {"resolved", type text}, {"csat_score", Int64.Type}, {"resolved_flag", Int64.Type}}, "en-IN")
in
    Typed


// ---------------------------------------------------------------------
// fact_churn_predictions
// ---------------------------------------------------------------------
let
    Source = fnLoadCsv("fact_churn_predictions.csv"),
    Typed  = Table.TransformColumnTypes(Source, {
        {"customer_id", type text}, {"tenure_months", Int64.Type}, {"monthly_charges", Currency.Type},
        {"avg_drop_rate", type number}, {"tickets_per_month", type number}, {"avg_csat", type number},
        {"late_payment_ratio", type number}, {"churn_probability", type number}, {"risk_tier", type text},
        {"annual_revenue", Currency.Type}, {"revenue_at_risk", Currency.Type}, {"predicted_clv", Currency.Type},
        {"next_best_action", type text}}, "en-IN"),
    TierSort = Table.AddColumn(Typed, "risk_tier_sort", each
        if [risk_tier] = "High" then 1 else if [risk_tier] = "Medium" then 2 else 3, Int64.Type)
in
    TierSort


// ---------------------------------------------------------------------
// dim_date   (or load dim_date.csv the same way)
// ---------------------------------------------------------------------
let
    Source = fnLoadCsv("dim_date.csv"),
    Typed  = Table.TransformColumnTypes(Source, {
        {"date", type date}, {"year", Int64.Type}, {"month_num", Int64.Type}, {"month_start", type date},
        {"is_weekend", type logical}}, "en-IN")
in
    Typed

// dim_plan, dim_geography, fact_monthly_kpis : fnLoadCsv("<file>.csv") + auto-detected types


// ---------------------------------------------------------------------
// OPTION B : MySQL source (after running sql/01 -> 04)
// ---------------------------------------------------------------------
let
    Source  = MySQL.Database("localhost", "telecom_churn_db", [ReturnSingleDatabase = true]),
    C360    = Source{[Schema = "telecom_churn_db", Item = "vw_customer_360"]}[Data]
in
    C360
