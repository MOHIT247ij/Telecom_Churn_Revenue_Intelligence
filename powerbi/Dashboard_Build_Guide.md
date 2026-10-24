# Power BI Dashboard – Build Guide

**Report:** Telecom Customer Churn & Revenue Intelligence · 6 pages · star-schema model · 60+ DAX measures

Estimated build time: 3–4 hours.

---

## 1. Load the data

1. Open Power BI Desktop and apply the theme: **View → Themes → Browse for themes → `Telecom_Theme.json`**.
2. Go to **Home → Transform data → Manage Parameters → New**. Name it `DataFolder` and point it at your `powerbi\model_data\` folder. Keep the trailing `\`.
3. Create the `fnLoadCsv` function and the queries from `PowerQuery_M.pq`. A quicker route also works: **Get Data → Text/CSV** for each of the 9 files, then fix the column types as listed in the .pq file.
4. Rename the queries so they match the file names (`dim_customer`, `fact_billing`, and so on), then click **Close & Apply**.

| Table | Rows | Grain |
|---|---|---|
| dim_customer | 8,000 | 1 per subscriber |
| dim_date | 2,557 | 1 per day (2019–2025) |
| dim_geography | 24 | 1 per city |
| dim_plan | 11 | 1 per plan |
| fact_billing | ~117K | customer × month |
| fact_usage | ~117K | customer × month |
| fact_tickets | ~38K | 1 per ticket |
| fact_churn_predictions | ~5.7K | 1 per active customer (ML score) |
| fact_monthly_kpis | 24 | 1 per month (pre-aggregated from Python) |

## 2. Data model (Model view)

```
                 dim_geography
                      │ 1
                      ▼ *
dim_plan 1──* fact_billing *──1 dim_customer 1──* fact_tickets
                  │ *           │ 1  │ 1         │ *
                  ▼ 1           │    └──* fact_usage
               dim_date ◄───────┘ (inactive: join_date, churn_date)
                  ▲ 1           │ 1
                  │             └──1 fact_churn_predictions
     fact_usage / fact_tickets / fact_monthly_kpis (*)
```

| From (many) | To (one) | Active | Cross-filter |
|---|---|---|---|
| fact_billing[customer_id] | dim_customer[customer_id] | ✅ | Single |
| fact_billing[plan_id] | dim_plan[plan_id] | ✅ | Single |
| fact_billing[bill_month] | dim_date[date] | ✅ | Single |
| fact_usage[customer_id] | dim_customer[customer_id] | ✅ | Single |
| fact_usage[usage_month] | dim_date[date] | ✅ | Single |
| fact_tickets[customer_id] | dim_customer[customer_id] | ✅ | Single |
| fact_tickets[ticket_date] | dim_date[date] | ✅ | Single |
| fact_churn_predictions[customer_id] | dim_customer[customer_id] | ✅ | Single |
| fact_monthly_kpis[month] | dim_date[date] | ✅ | Single |
| dim_customer[geo_key] | dim_geography[geo_key] | ✅ | Single |
| dim_customer[join_date] | dim_date[date] | ❌ inactive | used by `USERELATIONSHIP` |
| dim_customer[churn_date] | dim_date[date] | ❌ inactive | used by `USERELATIONSHIP` |

Then finish the model setup:

- Select `dim_date` and choose **Table tools → Mark as date table → date**.
- Set the sort order with **Sort by column**: `month_name` by `month_num`, `tenure_band` by `tenure_band_sort`, `charge_band` by `charge_band_sort`, and `risk_tier` by `risk_tier_sort`.
- Set the data category on `dim_geography[circle]` to **State or Province** and on `city` to **City**. Set `country` to **Country**.
- Hide every key column (`customer_id` on the fact tables, `geo_key`, `plan_id` on the facts) from report view.

## 3. Measures

1. Choose **Home → Enter data**, name the table `_Measures`, and click **Load**. Delete the default column.
2. Paste each measure from `DAX_Measures.dax` and put it in the display folder given in the file.
3. Create the What-If parameters under **Modeling → New parameter → Numeric range**:
   - `Save Rate`: 0.10–0.60, step 0.05, default 0.30
   - `Offer Cost`: 100–800, step 50, default 300
4. Set the formats:
   - **Percentage:** all `%` measures
   - **Currency ₹ (en-IN):** revenue measures, using the custom format `₹#,##,##0`
   - **Whole number:** counts

## 3b. Page backgrounds (ready-made PNGs)

`backgrounds/` has a designed background for every page (1920×1080). It includes a header with the project name and page title, a slicer strip, KPI card slots with an accent bar, and white panels for each visual.

| Page | File |
|---|---|
| 1 Executive Overview | `01_executive_overview.png` |
| 2 Churn Analysis | `02_churn_analysis.png` |
| 3 Revenue Intelligence | `03_revenue_intelligence.png` |
| 4 Churn Risk & Retention | `04_risk_retention.png` |
| 5 Customer Experience | `05_customer_experience.png` |
| 6 Customer 360 (drill-through) | `06_customer_360.png` |
| Tooltip page | `07_tooltip.png` |

How to apply a background:

1. Click an empty part of the canvas. Go to **Format page → Canvas background**.
2. Click **Browse** and pick the PNG. Set **Image fit = Fit** and **Transparency = 0%**.
3. Go to **Format page → Wallpaper** and set the colour to `#F4F5F7`.
4. On every visual, turn **Background OFF** and **Border OFF**. The white panels are already in the image.
5. To line visuals up with the panels exactly, use the X / Y / Width / Height values in `backgrounds/LAYOUT.md`, entered under **Format → General → Properties**.
6. Put a **Page navigator** (Insert → Buttons → Navigator) over the six pills in the header at X 792, Y 19, W 465, H 23.
7. Style the navigator: transparent fill, white text, and a selected state of `#2A78D6`.

To change the colours or the layout, edit `make_backgrounds.py` and run `python make_backgrounds.py`.

---

## 4. Report pages

Canvas: 1280 × 720. Put a slicer row at the top of every page with **Fiscal Year · Circle · Service Type · Contract Type**. Use **View → Sync slicers** to sync it across all pages.

### Page 1 – Executive Overview

| Visual | Fields |
|---|---|
| Title (card) | `Title Executive` |
| 6 KPI cards | Total Customers · Active Customers · Churn Rate % · Total Revenue · ARPU · Revenue at Risk |
| Line chart | X: dim_date[month_start] · Y: Total Revenue, Revenue Collected |
| Clustered column chart | X: month_start · Y: New Subscribers, Churned in Period |
| Bar chart | Y: dim_customer[contract_type] · X: Churn Rate % · bar colour: fx → field value `Churn Colour` |
| Filled map / shape map | Location: dim_geography[circle] · colour saturation: Churn Rate % |
| Smart narrative | Auto-summary of the page |

### Page 2 – Churn Analysis

| Visual | Fields |
|---|---|
| Line chart | month_start × Monthly Churn Rate %. Add an error band or constant line for the average and annotate "Jul-24 tariff hike". |
| Column chart | tenure_band × Churn Rate % |
| Matrix | Rows: service_type · Columns: contract_type · Values: Churn Rate %, with a background-colour scale (white → red) |
| Bar chart | churn_reason × Churned Customers (sorted descending) |
| **Key Influencers** (AI visual) | Analyse: dim_customer[churn] = "Yes". Explain by: contract_type, tenure_band, payment_method, network_type, circle, addon_count, charge_band. |
| **Decomposition tree** | Analyse: Churn Rate %. Explain by: circle → service_type → contract_type → payment_method. |

### Page 3 – Revenue Intelligence

| Visual | Fields |
|---|---|
| KPI cards | Revenue FYTD · Revenue YoY % · Collection Efficiency % · MRR Lost to Churn · Top 20% Revenue Share |
| Area chart | month_start × Revenue Running Total |
| Line chart | month_start × ARPU (a separate visual, not a dual axis) |
| Waterfall | Category: month_start · Y: Net New MRR (shows gains and losses per month) |
| Bar chart | dim_geography[circle] × Total Revenue, with data labels |
| Treemap | dim_plan[plan_tier] → plan_name × Total Revenue |
| Line chart | month_start × Cumulative MRR Lost |
| Table | service_type, contract_type, ARPU, Churn Rate %, Avg Predicted CLV |

### Page 4 – Churn Risk & Retention (ML)

| Visual | Fields |
|---|---|
| KPI cards | High Risk Customers · Medium Risk Customers · Revenue at Risk · High Risk Revenue · Avg Churn Probability |
| Scatter | X: monthly_charges · Y: churn_probability · Legend: risk_tier · Details: customer_id |
| Stacked bar | circle × Revenue at Risk · Legend: risk_tier |
| Donut → bar | next_best_action × Targeted Customers |
| What-If panel | `Save Rate` and `Offer Cost` slicers, plus cards for Campaign Cost, Revenue Saved, Campaign Net Benefit, Campaign ROI % |
| Table (retention call-list) | customer_id, circle, plan_name, contract_type, monthly_charges, churn_probability (data bars), revenue_at_risk, next_best_action. Filter: risk_tier = High. Sort: revenue_at_risk descending. |

### Page 5 – Customer Experience & Network

| Visual | Fields |
|---|---|
| KPI cards | Total Tickets · Avg CSAT · Avg Resolution Hours · Resolution Rate % · Avg Call Drop Rate % |
| Bar chart | fact_tickets[category] × Total Tickets, with Avg Resolution Hours in the tooltip |
| Line chart | month_start × Avg CSAT |
| Scatter | circle: X = Avg Call Drop Rate %, Y = Churn Rate %, size = Total Customers |
| Matrix | channel × Avg CSAT, Avg Resolution Hours |

### Page 6 – Customer 360 (drill-through)

- Set the drill-through field to `dim_customer[customer_id]`.
- Add cards for plan, tenure, monthly_charges, churn_probability, risk_tier and next_best_action.
- Add a line chart of amount_billed by month and another of data_used_gb by month.
- Add a table of tickets (date, category, CSAT).
- Right-click any customer in the page 4 table and choose **Drill through → Customer 360**.

### Tooltip page (optional, adds polish)

1. Create a small page (Page size: Tooltip) with a mini trend of Churn Rate % plus the Avg CSAT card.
2. Turn on **Page information → Allow use as tooltip**.
3. Assign it to the circle visuals.

---

## 5. Row-level security (enterprise feature)

Use this so that circle heads see only their own region.

1. Choose **Modeling → Manage roles → New role "Circle Manager"** on `dim_geography`:
   ```DAX
   [circle] = LOOKUPVALUE ( circle_access[circle], circle_access[email], USERPRINCIPALNAME () )
   ```
   `circle_access` is a small mapping table with `email` and `circle` columns.
2. Test it with **Modeling → View as → Circle Manager**.

## 6. Publishing checklist

- [ ] All visuals have titles, and number formats use ₹ (lakh/crore).
- [ ] Page navigator buttons are set up (**Insert → Buttons → Navigator → Page navigator**).
- [ ] There are bookmarks for a "Reset filters" button.
- [ ] Alt text is set on the key visuals for accessibility.
- [ ] The report is published to the Power BI Service. Schedule the refresh (gateway → MySQL) and pin KPIs to a dashboard.
- [ ] Data alerts are on: Churn Rate % > 3% monthly and Revenue at Risk > ₹25 L.
- [ ] Screenshots of each page are exported to `/outputs/dashboard_screenshots/` for GitHub.
