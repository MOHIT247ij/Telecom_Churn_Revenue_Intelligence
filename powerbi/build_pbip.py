"""
build_pbip.py - generates a ready-to-open Power BI Project (.pbip)

    powerbi/Telecom_Churn_Dashboard.pbip
    powerbi/Telecom_Churn_Dashboard.SemanticModel/   (model.bim: tables, M queries, relationships, measures)
    powerbi/Telecom_Churn_Dashboard.Report/          (report.json: 6 pages, visuals, backgrounds)

Open the .pbip in Power BI Desktop -> Refresh -> File > Save As .pbix if you want a single file.
Data folder is a parameter (DataFolder) - change it in Transform data > Manage parameters
if the project lives somewhere else.

Run:  python build_pbip.py ["E:\\path\\to\\powerbi\\model_data\\"]
"""
import json, re, shutil, sys, uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
NAME = "Telecom_Churn_Dashboard"
DATA_FOLDER = sys.argv[1] if len(sys.argv) > 1 else \
    r"E:\ALL_PROJECT\Telecom_Churn_Revenue_Intelligence\powerbi\model_data" + "\\"
LAYOUT = json.loads((HERE / "backgrounds/LAYOUT.json").read_text())
SM, RP = HERE / f"{NAME}.SemanticModel", HERE / f"{NAME}.Report"


def gid():
    return str(uuid.uuid4())


# ====================================================================== SEMANTIC MODEL
# column specs: name -> (tmsl dataType, M type)
T = {"s": ("string", "type text"), "i": ("int64", "Int64.Type"), "d": ("double", "type number"),
     "c": ("decimal", "Currency.Type"), "dt": ("dateTime", "type date"), "b": ("boolean", "type logical")}

TABLES = {
    "dim_customer": dict(customer_id="s", geo_key="s", gender="s", age="i", age_band="s", senior_citizen="i",
                         partner="s", dependents="s", join_date="dt", acquisition_channel="s", service_type="s",
                         plan_id="s", network_type="s", contract_type="s", payment_method="s",
                         paperless_billing="s", ott_bundle="s", device_protection="s", intl_roaming="s",
                         priority_support="s", multi_line="s", addon_count="i", discount_pct="d",
                         monthly_charges="c", charge_band="s", tenure_months="i", tenure_band="s", churn="s",
                         churn_flag="i", churn_date="dt", churn_reason="s", customer_status="s"),
    "dim_date": dict(date="dt", year="i", quarter="s", month_num="i", month_name="s", year_month="s",
                     month_start="dt", fiscal_year="s", fiscal_quarter="s", is_weekend="b"),
    "dim_geography": dict(geo_key="s", circle="s", city="s", city_tier="s", zone="s", country="s"),
    "dim_plan": dict(plan_id="s", plan_name="s", service_type="s", monthly_fee="c", data_gb_limit="i",
                     voice_benefit="s", plan_tier="s"),
    "fact_billing": dict(invoice_id="s", customer_id="s", plan_id="s", bill_month="dt", amount_billed="c",
                         amount_paid="c", outstanding="c", payment_status="s", days_late="i"),
    "fact_usage": dict(customer_id="s", usage_month="dt", data_used_gb="d", voice_minutes="i",
                       call_drop_rate_pct="d", avg_speed_mbps="d"),
    "fact_tickets": dict(ticket_id="s", customer_id="s", ticket_date="dt", category="s", channel="s",
                         resolution_hours="d", resolved="s", csat_score="d", resolved_flag="i"),
    "fact_churn_predictions": dict(customer_id="s", circle="s", city="s", service_type="s", plan_name="s",
                                   contract_type="s", tenure_months="i", monthly_charges="c", avg_drop_rate="d",
                                   tickets_per_month="d", avg_csat="d", late_payment_ratio="d",
                                   churn_probability="d", risk_tier="s", annual_revenue="c",
                                   revenue_at_risk="c", predicted_clv="c", next_best_action="s"),
    "fact_monthly_kpis": dict(month="dt", opening_subscribers="i", new_subscribers="i", churned_subscribers="i",
                              closing_subscribers="i", churn_rate="d", mrr="c", collected="c",
                              collection_efficiency="d", late_payment_rate="d", billed_subscribers="i",
                              churned_mrr="c", new_mrr="c", arpu="c", mrr_growth_pct="d",
                              net_subscriber_adds="i", cumulative_revenue_lost="c"),
}
KEYS_TO_HIDE = {"geo_key", "invoice_id", "ticket_id"}
SORT_HELPERS = {  # helper sort columns added in M
    "dim_customer": {"tenure_band": ("tenure_band_sort", 'if [tenure_band] = "0-6 M" then 1 else if [tenure_band] = "7-12 M" then 2 else if [tenure_band] = "13-24 M" then 3 else if [tenure_band] = "25-48 M" then 4 else 5'),
                     "charge_band": ("charge_band_sort", 'if [charge_band] = "< 300" then 1 else if [charge_band] = "300-600" then 2 else if [charge_band] = "600-1000" then 3 else 4')},
    "fact_churn_predictions": {"risk_tier": ("risk_tier_sort", 'if [risk_tier] = "High" then 1 else if [risk_tier] = "Medium" then 2 else 3')},
}


def m_query(table, cols):
    types = ", ".join(f'{{"{c}", {T[t][1]}}}' for c, t in cols.items())
    lines = ["let",
             f'    Source = Csv.Document(File.Contents(DataFolder & "{table}.csv"), [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),',
             "    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),",
             f"    Typed = Table.TransformColumnTypes(Promoted, {{{types}}}, \"en-US\")"]
    last = "Typed"
    if table == "dim_date":   # keep the analysis window only (Jan-2024 .. Dec-2025)
        lines[-1] += ","
        lines.append("    Window = Table.SelectRows(Typed, each [date] >= #date(2024, 1, 1) and [date] <= #date(2025, 12, 31))")
        last = "Window"
    for _, (helper, expr) in SORT_HELPERS.get(table, {}).items():
        lines[-1] += ","
        lines.append(f"    Add_{helper} = Table.AddColumn({last}, \"{helper}\", each {expr}, Int64.Type)")
        last = f"Add_{helper}"
    if table in ("dim_customer",):
        lines[-1] += ","
        lines.append(f'    Clean = Table.ReplaceValue({last}, "", null, Replacer.ReplaceValue, {{"churn_reason"}})')
        last = "Clean"
    lines += ["in", f"    {last}"]
    return lines


def fmt_for(col, t):
    if t == "c":
        return "\u20B9#,0"
    if t == "dt":
        return "dd-mmm-yyyy"
    if t == "i":
        return "0"
    return None


tables = []
for tname, cols in TABLES.items():
    columns = []
    for c, t in cols.items():
        col = {"name": c, "dataType": T[t][0], "sourceColumn": c,
               "summarizeBy": "none" if (t in ("s", "dt", "b") or c.endswith(("_id", "_flag", "num", "year")) or c in ("age",)) else "sum"}
        f = fmt_for(c, t)
        if f:
            col["formatString"] = f
        if c in KEYS_TO_HIDE or (c.endswith("_id") and tname.startswith("fact_")):
            col["isHidden"] = True
        if tname == "dim_date" and c == "date":
            col["isKey"] = True
        if tname == "dim_date" and c == "month_name":
            col["sortByColumn"] = "month_num"
        if tname == "dim_geography" and c == "circle":
            col["dataCategory"] = "StateOrProvince"
        if tname == "dim_geography" and c == "city":
            col["dataCategory"] = "City"
        if tname == "dim_geography" and c == "country":
            col["dataCategory"] = "Country"
        columns.append(col)
    for base, (helper, _) in SORT_HELPERS.get(tname, {}).items():
        columns.append({"name": helper, "dataType": "int64", "sourceColumn": helper, "isHidden": True,
                        "summarizeBy": "none", "formatString": "0"})
        next(c for c in columns if c["name"] == base)["sortByColumn"] = helper
    tbl = {"name": tname, "columns": columns,
           "partitions": [{"name": tname, "mode": "import", "source": {"type": "m", "expression": m_query(tname, cols)}}]}
    if tname == "dim_date":
        tbl["dataCategory"] = "Time"
    tables.append(tbl)

# what-if parameter tables (used by campaign ROI measures)
for pname, values, default, fmt in [("Save Rate", "List.Transform({2..12}, each _ * 0.05)", 0.30, "0%"),
                                    ("Offer Cost", "List.Transform({2..16}, each _ * 50)", 300, "\u20B9#,0")]:
    tables.append({
        "name": pname,
        "columns": [{"name": pname, "dataType": "double", "sourceColumn": pname, "formatString": fmt, "summarizeBy": "none"}],
        "partitions": [{"name": pname, "mode": "import", "source": {"type": "m", "expression": [
            "let", f"    Source = Table.FromList({values}, Splitter.SplitByNothing(), {{\"{pname}\"}}),",
            f"    Typed = Table.TransformColumnTypes(Source, {{{{\"{pname}\", type number}}}})", "in", "    Typed"]}}],
        "measures": [{"name": f"{pname} Value", "expression": f"SELECTEDVALUE ( '{pname}'[{pname}], {default} )",
                      "formatString": fmt}],
    })

# ---------------------------------------------------------------- measures from DAX_Measures.dax
dax = (HERE / "DAX_Measures.dax").read_text(encoding="utf-8")
measures, folder = [], "Measures"
cur = None
for line in dax.splitlines():
    fm = re.match(r"//\s*\[(.+?)\]", line)
    if fm:
        folder = fm.group(1)
        continue
    if line.startswith("//"):
        continue
    mm = re.match(r"^([A-Za-z0-9][^=]*?)\s*=\s*(.*)$", line)
    if mm and not line.startswith((" ", "\t")):
        cur = {"name": mm.group(1).strip(), "lines": [mm.group(2)] if mm.group(2).strip() else [],
               "folder": folder}
        measures.append(cur)
    elif cur is not None and line.strip():
        cur["lines"].append(line)

# extra measures for the Customer 360 page
extra = {
    "Customer Plan": "SELECTEDVALUE ( dim_customer[plan_id], \"Select a customer\" )",
    "Customer Contract": "SELECTEDVALUE ( dim_customer[contract_type], \"-\" )",
    "Customer Tenure (M)": "IF ( HASONEVALUE ( dim_customer[customer_id] ), MAX ( dim_customer[tenure_months] ) )",
    "Customer Monthly Charge": "IF ( HASONEVALUE ( dim_customer[customer_id] ), MAX ( dim_customer[monthly_charges] ) )",
    "Customer Churn Probability": "IF ( HASONEVALUE ( dim_customer[customer_id] ), MAX ( fact_churn_predictions[churn_probability] ) )",
    "Customer Risk Tier": "IF ( HASONEVALUE ( dim_customer[customer_id] ), COALESCE ( MAX ( fact_churn_predictions[risk_tier] ), \"Already churned\" ) )",
    "Customer Next Action": "IF ( HASONEVALUE ( dim_customer[customer_id] ), COALESCE ( MAX ( fact_churn_predictions[next_best_action] ), \"-\" ) )",
    "Customer Status": "SELECTEDVALUE ( dim_customer[customer_status], \"-\" )",
    "Total Data Used (GB)": "SUM ( fact_usage[data_used_gb] )",
    "Avg Monthly Charge": "AVERAGE ( dim_customer[monthly_charges] )",
}
for n, e in extra.items():
    measures.append({"name": n, "lines": [e], "folder": "09 Customer 360"})

PCT = {"Churn Rate %", "Retention Rate %", "Monthly Churn Rate %", "Avg Monthly Churn Rate %",
       "Collection Efficiency %", "Revenue MoM %", "Revenue YoY %", "Late Payment Rate %", "Top 20% Revenue Share",
       "Avg Churn Probability", "Revenue at Risk % of Annual", "Campaign ROI %", "Resolution Rate %",
       "Network Ticket Share %", "Avg Call Drop Rate %", "Customer Churn Probability"}
MONEY_WORDS = ("Revenue", "MRR", "ARPU", "Cost", "Benefit", "Outstanding", "Collected", "CLV", "Charge", "Lost")
TEXT = {"Title Executive", "Churn Colour", "KPI Revenue Arrow", "Last Refresh", "Customer Plan", "Customer Contract",
        "Customer Risk Tier", "Customer Next Action", "Customer Status"}
DEC = {"Avg CSAT": "0.00", "Avg Resolution Hours": "0.0", "Avg Speed (Mbps)": "0.0", "Avg Data per User (GB)": "0.0",
       "Avg Tenure (Months)": "0.0", "Churn Lift vs Avg": "0.00", "Tickets per 100 Customers": "0.0",
       "Total Data Used (GB)": "#,0.0", "Customer Tenure (M)": "0"}

mtable = []
for m in measures:
    n = m["name"]
    item = {"name": n, "expression": m["lines"] if len(m["lines"]) > 1 else m["lines"][0].strip(),
            "displayFolder": m["folder"]}
    if n in PCT or n.endswith("%"):
        item["formatString"] = "0.0%"
    elif n in TEXT:
        pass
    elif n in DEC:
        item["formatString"] = DEC[n]
    elif any(w in n for w in MONEY_WORDS):
        item["formatString"] = "\u20B9#,0"
    else:
        item["formatString"] = "#,0"
    mtable.append(item)

tables.append({
    "name": "_Measures",
    "columns": [{"name": "Dummy", "dataType": "string", "sourceColumn": "Dummy", "isHidden": True, "summarizeBy": "none"}],
    "partitions": [{"name": "_Measures", "mode": "import", "source": {"type": "m", "expression": [
        "let", "    Source = #table(type table [Dummy = text], {})", "in", "    Source"]}}],
    "measures": mtable,
})

REL = [("fact_billing", "customer_id", "dim_customer", "customer_id", True),
       ("fact_usage", "customer_id", "dim_customer", "customer_id", True),
       ("fact_tickets", "customer_id", "dim_customer", "customer_id", True),
       ("fact_churn_predictions", "customer_id", "dim_customer", "customer_id", True),
       ("fact_billing", "plan_id", "dim_plan", "plan_id", True),
       ("dim_customer", "geo_key", "dim_geography", "geo_key", True),
       ("fact_billing", "bill_month", "dim_date", "date", True),
       ("fact_usage", "usage_month", "dim_date", "date", True),
       ("fact_tickets", "ticket_date", "dim_date", "date", True),
       ("fact_monthly_kpis", "month", "dim_date", "date", True),
       ("dim_customer", "join_date", "dim_date", "date", False),
       ("dim_customer", "churn_date", "dim_date", "date", False)]
relationships = []
for ft, fc, tt, tc, active in REL:
    r = {"name": gid(), "fromTable": ft, "fromColumn": fc, "toTable": tt, "toColumn": tc}
    if not active:
        r["isActive"] = False
    relationships.append(r)

folder_lit = DATA_FOLDER.replace('"', '""')
model = {
    "compatibilityLevel": 1567,
    "model": {
        "culture": "en-US",
        "dataAccessOptions": {"legacyRedirects": True, "returnErrorValuesAsNull": True},
        "defaultPowerBIDataSourceVersion": "powerBI_V3",
        "sourceQueryCulture": "en-IN",
        "tables": tables,
        "relationships": relationships,
        "expressions": [{"name": "DataFolder", "kind": "m",
                         "expression": f'"{folder_lit}" meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]'}],
        "annotations": [{"name": "__PBI_TimeIntelligenceEnabled", "value": "0"},
                        {"name": "PBI_QueryOrder", "value": json.dumps(["DataFolder"] + [t["name"] for t in tables])}],
    },
}

# ====================================================================== REPORT
LIT = lambda v: {"expr": {"Literal": {"Value": v}}}
OFF = [{"properties": {"show": LIT("false")}}]


def title(text, size=10):
    return [{"properties": {"show": LIT("true"), "text": LIT(f"'{text}'"), "fontSize": LIT(f"{size}D"),
                            "fontColor": {"solid": {"color": LIT("'#0B0B0B'")}}}}]


class Q:
    """Builds prototypeQuery + projections for one visual."""
    def __init__(self):
        self.src, self.sel, self.proj = {}, [], {}

    def _alias(self, ent):
        if ent not in self.src:
            self.src[ent] = f"t{len(self.src)}"
        return self.src[ent]

    def col(self, role, ent, prop):
        ref = f"{ent}.{prop}"
        self.sel.append({"Column": {"Expression": {"SourceRef": {"Source": self._alias(ent)}}, "Property": prop},
                         "Name": ref})
        self.proj.setdefault(role, []).append({"queryRef": ref, **({"active": True} if role in ("Category", "Rows") else {})})
        return self

    def mea(self, role, prop, ent="_Measures"):
        ref = f"{ent}.{prop}"
        self.sel.append({"Measure": {"Expression": {"SourceRef": {"Source": self._alias(ent)}}, "Property": prop},
                         "Name": ref})
        self.proj.setdefault(role, []).append({"queryRef": ref})
        return self

    def query(self):
        return {"Version": 2, "From": [{"Name": a, "Entity": e, "Type": 0} for e, a in self.src.items()],
                "Select": self.sel}


Z = [1000]


def visual(vtype, slot, q, ttl=None, objects=None, pad=(4, 4, 8, 8)):
    x, y, w, h = slot
    x, y, w, h = x + pad[0], y + pad[1], w - pad[2], h - pad[3]
    Z[0] += 1
    vc = {"background": OFF, "border": OFF, "dropShadow": OFF,
          "title": title(ttl) if ttl else OFF}
    cfg = {"name": uuid.uuid4().hex[:20],
           "layouts": [{"id": 0, "position": {"x": x, "y": y, "z": Z[0], "width": w, "height": h}}],
           "singleVisual": {"visualType": vtype, "projections": q.proj, "prototypeQuery": q.query(),
                            "drillFilterOtherVisuals": True, "vcObjects": vc,
                            **({"objects": objects} if objects else {})}}
    return {"x": x, "y": y, "z": Z[0], "width": w, "height": h, "config": json.dumps(cfg), "filters": "[]"}


def card(slot, measure, label=None):
    obj = {"labels": [{"properties": {"fontSize": LIT("20D"), "color": {"solid": {"color": LIT("'#0B0B0B'")}}}}],
           "categoryLabels": [{"properties": {"show": LIT("true"), "fontSize": LIT("9D")}}]}
    return visual("card", slot, Q().mea("Values", measure), objects=obj, pad=(12, 4, 16, 8))


def slicers(slot, fields):
    x, y, w, h = slot
    n = len(fields)
    out, gap = [], 10
    sw = (w - 20 - gap * (n - 1)) / n
    for i, (ent, col, label) in enumerate(fields):
        s = [x + 10 + i * (sw + gap), y + 1, sw, h - 2]
        obj = {"data": [{"properties": {"mode": LIT("'Dropdown'")}}],
               "header": [{"properties": {"show": LIT("true"), "text": LIT(f"'{label}'"), "fontSize": LIT("8D")}}]}
        out.append(visual("slicer", s, Q().col("Values", ent, col), objects=obj, pad=(0, 0, 0, 0)))
    return out


def legend_off():
    return {"legend": [{"properties": {"show": LIT("false")}}]}


def labels_on():
    return {"labels": [{"properties": {"show": LIT("true")}}]}


STD_SLICERS = [("dim_date", "fiscal_year", "Fiscal year"), ("dim_geography", "circle", "Circle"),
               ("dim_customer", "service_type", "Service type"), ("dim_customer", "contract_type", "Contract type")]

pages = []
L = LAYOUT

# ---- page 1 Executive Overview
s = L["01 Executive Overview"]
v = slicers(s[0], STD_SLICERS)
for i, m in enumerate(["Total Customers", "Active Customers", "Churn Rate %", "Total Revenue", "ARPU",
                       "Revenue at Risk"]):
    v.append(card(s[1 + i], m))
v.append(visual("lineChart", s[7], Q().col("Category", "dim_date", "month_start").mea("Y", "Total Revenue")
                .mea("Y", "Revenue Collected"), "Monthly revenue - billed vs collected"))
v.append(visual("clusteredColumnChart", s[8], Q().col("Category", "dim_date", "month_start").mea("Y", "New Subscribers")
                .mea("Y", "Churned in Period"), "New vs churned subscribers"))
v.append(visual("clusteredBarChart", s[9], Q().col("Category", "dim_customer", "contract_type").mea("Y", "Churn Rate %"),
                "Churn rate by contract", {**legend_off(), **labels_on()}))
v.append(visual("clusteredBarChart", s[10], Q().col("Category", "dim_geography", "circle").mea("Y", "Churn Rate %"),
                "Churn rate by circle", {**legend_off(), **labels_on()}))
v.append(visual("donutChart", s[11], Q().col("Category", "fact_churn_predictions", "risk_tier")
                .mea("Y", "Revenue at Risk"), "Revenue at risk by tier"))
pages.append(("Executive Overview", "01_executive_overview.png", v))

# ---- page 2 Churn Analysis
s = L["02 Churn Analysis"]
v = slicers(s[0], STD_SLICERS)
for i, m in enumerate(["Total Customers", "Churned Customers", "Churn Rate %", "Avg Monthly Churn Rate %"]):
    v.append(card(s[1 + i], m))
v.append(visual("lineChart", s[5], Q().col("Category", "dim_date", "month_start").mea("Y", "Monthly Churn Rate %"),
                "Monthly churn rate (Jul-24 tariff hike, Apr-25 competitor 5G)"))
v.append(visual("clusteredColumnChart", s[6], Q().col("Category", "dim_customer", "tenure_band").mea("Y", "Churn Rate %"),
                "Churn rate by tenure", {**legend_off(), **labels_on()}))
v.append(visual("pivotTable", s[7], Q().col("Rows", "dim_customer", "service_type").col("Columns", "dim_customer", "contract_type")
                .mea("Values", "Churn Rate %"), "Churn rate: service x contract"))
v.append(visual("clusteredBarChart", s[8], Q().col("Category", "dim_customer", "churn_reason").mea("Y", "Churned Customers"),
                "Churn reasons", {**legend_off(), **labels_on()}))
v.append(visual("clusteredBarChart", s[9], Q().col("Category", "dim_customer", "payment_method").mea("Y", "Churn Rate %"),
                "Churn rate by payment method", {**legend_off(), **labels_on()}))
pages.append(("Churn Analysis", "02_churn_analysis.png", v))

# ---- page 3 Revenue Intelligence
s = L["03 Revenue Intelligence"]
v = slicers(s[0], STD_SLICERS)
for i, m in enumerate(["Total Revenue", "Collection Efficiency %", "ARPU", "MRR Lost to Churn", "Top 20% Revenue Share"]):
    v.append(card(s[1 + i], m))
v.append(visual("areaChart", s[6], Q().col("Category", "dim_date", "month_start").mea("Y", "Revenue Running Total"),
                "Cumulative revenue"))
v.append(visual("lineChart", s[7], Q().col("Category", "dim_date", "month_start").mea("Y", "ARPU"), "ARPU trend"))
v.append(visual("clusteredColumnChart", s[8], Q().col("Category", "dim_date", "month_start").mea("Y", "Net New MRR"),
                "Net new MRR (new - churned)", legend_off()))
v.append(visual("clusteredBarChart", s[9], Q().col("Category", "dim_geography", "circle").mea("Y", "Total Revenue"),
                "Revenue by circle", {**legend_off(), **labels_on()}))
v.append(visual("treemap", s[10], Q().col("Group", "dim_plan", "plan_name").mea("Values", "Total Revenue"),
                "Revenue by plan"))
v.append(visual("tableEx", s[11], Q().col("Values", "dim_customer", "service_type").col("Values", "dim_customer", "contract_type")
                .mea("Values", "Total Customers").mea("Values", "Avg Monthly Charge").mea("Values", "Churn Rate %")
                .mea("Values", "Avg Predicted CLV"), "Segment economics"))
pages.append(("Revenue Intelligence", "03_revenue_intelligence.png", v))

# ---- page 4 Risk & Retention
s = L["04 Churn Risk & Retention"]
v = slicers(s[0], [("dim_geography", "circle", "Circle"), ("dim_customer", "service_type", "Service type"),
                   ("fact_churn_predictions", "risk_tier", "Risk tier"), ("Save Rate", "Save Rate", "Save rate (what-if)"),
                   ("Offer Cost", "Offer Cost", "Offer cost (what-if)")])
for i, m in enumerate(["High Risk Customers", "Medium Risk Customers", "Revenue at Risk", "High Risk Revenue",
                       "Avg Churn Probability"]):
    v.append(card(s[1 + i], m))
v.append(visual("clusteredBarChart", s[6], Q().col("Category", "fact_churn_predictions", "next_best_action")
                .mea("Y", "Targeted Customers"), "Next-best action (High + Medium)", {**legend_off(), **labels_on()}))
v.append(visual("clusteredBarChart", s[7], Q().col("Category", "dim_geography", "circle").col("Series", "fact_churn_predictions", "risk_tier")
                .mea("Y", "Revenue at Risk"), "Revenue at risk by circle & tier"))
v.append(visual("multiRowCard", s[8], Q().mea("Values", "Targeted Customers").mea("Values", "Campaign Cost")
                .mea("Values", "Revenue Saved (Gross Margin)").mea("Values", "Campaign Net Benefit")
                .mea("Values", "Campaign ROI %"), "Retention campaign ROI"))
v.append(visual("tableEx", s[9], Q().col("Values", "fact_churn_predictions", "customer_id")
                .col("Values", "fact_churn_predictions", "circle").col("Values", "fact_churn_predictions", "plan_name")
                .col("Values", "fact_churn_predictions", "contract_type").col("Values", "fact_churn_predictions", "monthly_charges")
                .col("Values", "fact_churn_predictions", "churn_probability").col("Values", "fact_churn_predictions", "risk_tier")
                .col("Values", "fact_churn_predictions", "revenue_at_risk").col("Values", "fact_churn_predictions", "next_best_action"),
                "Retention call list"))
pages.append(("Risk & Retention", "04_risk_retention.png", v))

# ---- page 5 Customer Experience & Network
s = L["05 Customer Experience & Network"]
v = slicers(s[0], STD_SLICERS)
for i, m in enumerate(["Total Tickets", "Avg CSAT", "Avg Resolution Hours", "Resolution Rate %", "Avg Call Drop Rate %"]):
    v.append(card(s[1 + i], m))
v.append(visual("clusteredBarChart", s[6], Q().col("Category", "fact_tickets", "category").mea("Y", "Total Tickets"),
                "Tickets by category", {**legend_off(), **labels_on()}))
v.append(visual("lineChart", s[7], Q().col("Category", "dim_date", "month_start").mea("Y", "Avg CSAT"), "CSAT trend"))
v.append(visual("scatterChart", s[8], Q().col("Category", "dim_geography", "circle").mea("X", "Avg Call Drop Rate %")
                .mea("Y", "Churn Rate %"), "Network quality vs churn (by circle)"))
v.append(visual("pivotTable", s[9], Q().col("Rows", "fact_tickets", "channel").mea("Values", "Total Tickets")
                .mea("Values", "Avg CSAT").mea("Values", "Avg Resolution Hours"), "Support channel performance"))
pages.append(("Customer Experience", "05_customer_experience.png", v))

# ---- page 6 Customer 360
s = L["06 Customer 360"]
v = [visual("slicer", [s[0][0] + 10, s[0][1] + 1, 400, s[0][3] - 2],
            Q().col("Values", "dim_customer", "customer_id"),
            objects={"data": [{"properties": {"mode": LIT("'Dropdown'")}}],
                     "header": [{"properties": {"show": LIT("true"), "text": LIT("'Pick a customer (type to search)'"),
                                                "fontSize": LIT("8D")}}]}, pad=(0, 0, 0, 0))]
for i, m in enumerate(["Customer Plan", "Customer Contract", "Customer Tenure (M)", "Customer Monthly Charge",
                       "Customer Churn Probability", "Customer Next Action"]):
    v.append(card(s[2 + i], m))
v.append(visual("lineChart", s[8], Q().col("Category", "dim_date", "month_start").mea("Y", "Total Revenue"), "Monthly bill"))
v.append(visual("lineChart", s[9], Q().col("Category", "dim_date", "month_start").mea("Y", "Total Data Used (GB)"),
                "Monthly data usage (GB)"))
v.append(visual("tableEx", s[10], Q().col("Values", "fact_tickets", "ticket_date").col("Values", "fact_tickets", "category")
                .col("Values", "fact_tickets", "channel").col("Values", "fact_tickets", "resolution_hours")
                .col("Values", "fact_tickets", "csat_score"), "Support tickets"))
pages.append(("Customer 360", "06_customer_360.png", v))

# ---- assemble report.json
sections = []
for i, (pname, bg, vis) in enumerate(pages):
    bg_obj = {"background": [{"properties": {
        "image": {"image": {"name": LIT(f"'{bg}'"),
                            "url": {"expr": {"ResourcePackageItem": {"PackageName": "RegisteredResources",
                                                                      "PackageType": 1, "ItemName": bg}}},
                            "scaling": LIT("'Fit'")}},
        "transparency": LIT("0D")}}],
        "outspace": [{"properties": {"color": {"solid": {"color": LIT("'#F4F5F7'")}}}}]}
    sections.append({"name": f"ReportSection{i + 1:02d}", "displayName": pname, "displayOption": 1,
                     "width": 1280, "height": 720, "filters": "[]", "ordinal": i,
                     "config": json.dumps({"objects": bg_obj}), "visualContainers": vis})

report = {
    "config": json.dumps({"version": "5.43", "themeCollection": {}, "activeSectionIndex": 0,
                          "defaultDrillFilterOtherVisuals": True,
                          "settings": {"useStylableVisualContainerHeader": True, "exportDataMode": 1,
                                       "useNewFilterPaneExperience": True}}),
    "layoutOptimization": 0,
    "resourcePackages": [{"resourcePackage": {"name": "RegisteredResources", "type": 1, "disabled": False,
                                              "items": [{"type": 100, "path": bg, "name": bg} for _, bg, _ in pages]}}],
    "sections": sections,
}

# ====================================================================== WRITE FILES
for d in (SM, RP):
    if d.exists():
        shutil.rmtree(d)
(SM).mkdir()
(RP / "StaticResources/RegisteredResources").mkdir(parents=True)
(SM / "model.bim").write_text(json.dumps(model, indent=2, ensure_ascii=False), encoding="utf-8")
(SM / "definition.pbism").write_text(json.dumps({"version": "1.0", "settings": {}}, indent=2))
(RP / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
(RP / "definition.pbir").write_text(json.dumps(
    {"version": "1.0", "datasetReference": {"byPath": {"path": f"../{NAME}.SemanticModel"}, "byConnection": None}}, indent=2))
for _, bg, _ in pages:
    shutil.copy(HERE / "backgrounds" / bg, RP / "StaticResources/RegisteredResources" / bg)
(HERE / f"{NAME}.pbip").write_text(json.dumps(
    {"version": "1.0", "artifacts": [{"report": {"path": f"{NAME}.Report"}}], "settings": {"enableAutoRecovery": True}},
    indent=2))
print(f"tables {len(tables)} | measures {len(mtable)} | relationships {len(relationships)} | "
      f"pages {len(pages)} | visuals {sum(len(p[2]) for p in pages)}")
print("Open:", HERE / f"{NAME}.pbip")
