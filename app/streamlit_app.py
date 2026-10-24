"""
Telecom Customer Churn & Revenue Intelligence - Streamlit App
-------------------------------------------------------------
Run (from the project root):
    pip install streamlit altair
    streamlit run app/streamlit_app.py

Two data modes (sidebar):
    Demo data    - the project's 8,000-customer dataset (needs: python python/run_pipeline.py)
    Upload CSV   - your own customer file; every page re-computes on it
                   (churn scores, risk tiers, reasons, revenue at risk, actions)
"""
import io
from pathlib import Path
import numpy as np
import pandas as pd
import altair as alt
import streamlit as st
from sklearn.metrics import roc_auc_score, precision_score, recall_score, accuracy_score

from churn_engine import ChurnEngine, DRIVERS

ROOT = Path(__file__).resolve().parents[1]
PROC, REP, CH = ROOT / "data/processed", ROOT / "outputs/reports", ROOT / "outputs/charts"
BLUE, ORANGE, AQUA, YELLOW, RED, GREEN = "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e34948", "#1baf7a"
TIER_SCALE = alt.Scale(domain=["High", "Medium", "Low"], range=[ORANGE, YELLOW, BLUE])

st.set_page_config(page_title="Telecom Churn Intelligence", page_icon="📱", layout="wide")


# ================================================================== helpers
def inr(x):
    if pd.isna(x):
        return "-"
    if abs(x) >= 1e7:
        return f"₹{x / 1e7:.2f} Cr"
    if abs(x) >= 1e5:
        return f"₹{x / 1e5:.1f} L"
    return f"₹{x:,.0f}"


def bar(df, x, y, title, color=BLUE, fmt=".1%", sort="-x"):
    base = alt.Chart(df).encode(
        x=alt.X(f"{x}:Q", title=None, axis=alt.Axis(format=fmt)),
        y=alt.Y(f"{y}:N", sort=sort, title=None),
        tooltip=[alt.Tooltip(f"{y}:N"), alt.Tooltip(f"{x}:Q", format=fmt)])
    chart = base.mark_bar(color=color, cornerRadiusEnd=4) + \
        base.mark_text(align="left", dx=4, color="#52514e").encode(text=alt.Text(f"{x}:Q", format=fmt))
    return chart.properties(title=title, height=max(160, 30 * len(df)))


def contrib_chart(c_row, title):
    """Horizontal bars: red = raises churn risk, green = lowers it."""
    d = c_row[c_row.abs() >= 0.005].sort_values()
    if d.empty:
        return None
    df = pd.DataFrame({"driver": [DRIVERS[k][1] for k in d.index], "effect": d.values})
    df["direction"] = np.where(df.effect > 0, "Raises risk", "Lowers risk")
    return alt.Chart(df).mark_bar(cornerRadiusEnd=4).encode(
        x=alt.X("effect:Q", title="Change in churn probability", axis=alt.Axis(format="+.0%")),
        y=alt.Y("driver:N", sort="-x", title=None),
        color=alt.Color("direction:N", scale=alt.Scale(domain=["Raises risk", "Lowers risk"], range=[RED, GREEN]),
                        title=None),
        tooltip=["driver", alt.Tooltip("effect:Q", format="+.1%")]
    ).properties(title=title, height=max(140, 28 * len(df)))


@st.cache_resource
def get_engine():
    return ChurnEngine()


@st.cache_data
def load_demo():
    return {
        "cust": pd.read_csv(PROC / "customers_clean.csv", parse_dates=["join_date", "churn_date"]),
        "pred": pd.read_csv(REP / "churn_predictions.csv"),
        "models": pd.read_csv(REP / "model_comparison.csv"),
        "final": pd.read_csv(REP / "final_model_metrics.csv"),
        "imp": pd.read_csv(REP / "feature_importance.csv"),
        "clv": pd.read_csv(REP / "clv_by_segment.csv"),
        "cohort": pd.read_csv(REP / "cohort_retention.csv", index_col=0),
        "feat": pd.read_csv(PROC / "model_features.csv"),
        "bill": pd.read_csv(PROC / "billing_clean.csv", parse_dates=["bill_month"]),
    }


@st.cache_data(show_spinner="Explaining churn drivers for every customer...")
def demo_scored(_engine, feat, pred):
    """Active customers: honest out-of-fold probability + reason codes."""
    act = feat[feat.churn_flag == 0].merge(pred[["customer_id", "churn_probability"]], on="customer_id")
    X = act[_engine.features].reset_index(drop=True)
    R, C = _engine.reasons(X)
    s = _engine.score(X, prob=act["churn_probability"].values)
    s.insert(0, "customer_id", act["customer_id"].values)
    return pd.concat([s, R], axis=1), C


@st.cache_data(show_spinner="Scoring your customers...")
def upload_scored(_engine, raw_bytes, name):
    raw = pd.read_excel(io.BytesIO(raw_bytes)) if name.lower().endswith((".xlsx", ".xls")) \
        else pd.read_csv(io.BytesIO(raw_bytes))
    X, disp, info = _engine.prepare(raw)
    X = X.reset_index(drop=True)
    disp = disp.reset_index(drop=True)
    R, C = _engine.reasons(X)
    s = _engine.score(X)
    s.insert(0, "customer_id", disp["customer_id"].astype(str).values)
    for c in ["tenure_band", "charge_band", "churn_flag"]:
        if c in disp:
            s[c] = disp[c].values
    return pd.concat([s, R], axis=1), C, info, raw.head(5)


# ================================================================== engine & data
model_ready = (ROOT / "outputs/models/churn_model.pkl").exists() and (PROC / "model_features.csv").exists()
if not model_ready:
    st.error("Model not found. Run the pipeline first:  `python python/run_pipeline.py`")
    st.stop()
E = get_engine()

st.sidebar.title("📱 Telecom Churn Intelligence")
mode = st.sidebar.radio("Data source", ["Demo data (8,000 customers)", "Upload my CSV"])
DEMO = mode.startswith("Demo")

if DEMO:
    D = load_demo()
    scored, CONTRIB = demo_scored(E, D["feat"], D["pred"])
    base = D["cust"].copy()                       # all customers incl. churned (has actual label)
    HAS_LABEL, HAS_TIME = True, True
    info = None
else:
    st.sidebar.markdown("**Upload a customer file** (CSV or Excel)")
    up = st.sidebar.file_uploader("Customer file", type=["csv", "xlsx", "xls"], label_visibility="collapsed")
    st.sidebar.download_button("⬇ Download sample / template", E.template(50).to_csv(index=False),
                               "churn_upload_template.csv", "text/csv")
    with st.sidebar.expander("Which columns do I need?"):
        st.markdown(
            "**Minimum:** `customer_id`, `tenure_months`, `monthly_charges`, `contract_type`\n\n"
            "**Better accuracy:** `avg_csat`, `tickets_per_month` (or `ticket_count`), `avg_drop_rate`, "
            "`late_payment_ratio`, `usage_trend`, `payment_method`, `service_type`, `circle`\n\n"
            "**Optional:** `churn` / `churn_flag` (Yes/No) → unlocks actual churn analysis + model accuracy.\n\n"
            "Missing columns are filled with a *typical customer* value. Common names like `Tenure`, "
            "`MonthlyCharges`, `Contract`, `CustomerID` are recognised automatically.")
    if up is None:
        st.title("📤 Upload your customer data")
        st.markdown(
            "1. Download the **sample / template** from the sidebar (or use your own file).\n"
            "2. Upload it in the sidebar.\n"
            "3. Every page will re-calculate on **your** customers: churn probability, risk tier, "
            "top churn reasons, revenue at risk, next-best action and campaign ROI.")
        st.dataframe(E.template(5), hide_index=True, use_container_width=True)
        st.stop()
    scored, CONTRIB, info, preview = upload_scored(E, up.getvalue(), up.name)
    base = scored.copy()
    HAS_LABEL = "churn_flag" in scored and scored["churn_flag"].nunique() > 1
    HAS_TIME = False

page = st.sidebar.radio("Page", ["Executive Overview", "Churn Analysis", "Revenue Intelligence",
                                 "Risk & Retention", "Customer Drill-down", "Churn Predictor", "Model Performance"])
st.sidebar.markdown("---")
circles = sorted(base.circle.astype(str).unique())
services = sorted(base.service_type.astype(str).unique())
f_circle = st.sidebar.multiselect("Circle", circles, default=circles)
f_service = st.sidebar.multiselect("Service type", services, default=services)

base = base[base.circle.astype(str).isin(f_circle) & base.service_type.astype(str).isin(f_service)]
keep = scored.circle.astype(str).isin(f_circle) & scored.service_type.astype(str).isin(f_service)
CONTRIB = CONTRIB[keep.values].reset_index(drop=True)
scored = scored[keep].reset_index(drop=True)
if scored.empty:
    st.warning("No customers match the filters.")
    st.stop()

if not DEMO:
    cov = info["coverage"]
    msg = (f"**{info['rows']:,} customers uploaded** · {len(info['provided'])}/{len(E.features)} model inputs found "
           f"({cov:.0%})" + (" · churn label found ✅" if HAS_LABEL else ""))
    (st.success if cov >= 0.5 else st.warning)(msg + ("" if cov >= 0.5 else
        " · few inputs provided, so scores lean on typical-customer defaults. Add more columns for better accuracy."))

# churn metric used on charts: actual churn if label exists, else predicted probability
if HAS_LABEL:
    RATE_COL, RATE_NAME = "churn_flag", "Churn rate (actual)"
else:
    RATE_COL, RATE_NAME = "churn_probability", "Avg predicted churn probability"
    base = scored


def seg_rate(df, dim):
    g = df.groupby(dim).agg(rate=(RATE_COL, "mean"), customers=(RATE_COL, "size")).reset_index()
    g[dim] = g[dim].astype(str)
    return g


# demo time series
if HAS_TIME:
    bill = D["bill"][D["bill"].customer_id.isin(base.customer_id)]
    monthly = bill.groupby("bill_month").agg(revenue=("amount_billed", "sum"), collected=("amount_paid", "sum"),
                                             subscribers=("customer_id", "nunique")).reset_index()
    monthly["arpu"] = monthly.revenue / monthly.subscribers
    ch = base.dropna(subset=["churn_date"])
    move = pd.concat([base.groupby(base.join_date.dt.to_period("M").dt.to_timestamp()).size().rename("new"),
                      ch.groupby(ch.churn_date.dt.to_period("M").dt.to_timestamp()).size().rename("churned")],
                     axis=1).fillna(0).reset_index(names="month")
    move = move[(move.month >= "2024-01-01") & (move.month <= "2025-12-01")]


# ================================================================== PAGES
if page == "Executive Overview":
    st.title("Executive Overview")
    st.caption("Demo: Jan-2024 to Dec-2025 · 8,000 synthetic subscribers" if DEMO else "Your uploaded customers")
    c = st.columns(6)
    c[0].metric("Customers", f"{len(base):,}")
    if HAS_LABEL:
        c[1].metric("Churn rate (actual)", f"{base.churn_flag.mean():.1%}")
    else:
        c[1].metric("Avg churn probability", f"{scored.churn_probability.mean():.1%}")
    c[2].metric("High-risk customers", f"{(scored.risk_tier == 'High').sum():,}")
    c[3].metric("Monthly revenue (scored base)", inr(scored.monthly_charges.sum()))
    c[4].metric("Annual revenue at risk", inr(scored.revenue_at_risk.sum()))
    c[5].metric("Revenue at risk %", f"{scored.revenue_at_risk.sum() / scored.annual_revenue.sum():.1%}")

    l, r = st.columns(2)
    if HAS_TIME:
        mrr = monthly.melt("bill_month", ["revenue", "collected"], var_name="series", value_name="amount")
        l.altair_chart(alt.Chart(mrr).mark_line(point=True).encode(
            x=alt.X("bill_month:T", title=None), y=alt.Y("amount:Q", title="₹"),
            color=alt.Color("series:N", scale=alt.Scale(range=[BLUE, AQUA]), title=None),
            tooltip=["bill_month:T", "series", alt.Tooltip("amount:Q", format=",.0f")]
        ).properties(title="Monthly revenue - billed vs collected", height=300), use_container_width=True)
        mv = move.melt("month", ["new", "churned"], var_name="type", value_name="customers")
        r.altair_chart(alt.Chart(mv).mark_bar().encode(
            x=alt.X("yearmonth(month):T", title=None), xOffset="type:N", y=alt.Y("customers:Q", title=None),
            color=alt.Color("type:N", scale=alt.Scale(domain=["new", "churned"], range=[BLUE, ORANGE]), title=None),
            tooltip=["month:T", "type", "customers"]
        ).properties(title="New vs churned subscribers", height=300), use_container_width=True)
    else:
        l.altair_chart(alt.Chart(scored).mark_bar(color=BLUE).encode(
            x=alt.X("churn_probability:Q", bin=alt.Bin(maxbins=20), title="Churn probability",
                    axis=alt.Axis(format=".0%")),
            y=alt.Y("count():Q", title="Customers"), tooltip=["count():Q"]
        ).properties(title="Distribution of churn probability", height=300), use_container_width=True)
        t = scored.groupby("risk_tier").agg(customers=("customer_id", "count"),
                                            at_risk=("revenue_at_risk", "sum")).reset_index()
        r.altair_chart(alt.Chart(t).mark_bar(cornerRadiusEnd=4).encode(
            x=alt.X("customers:Q", title="Customers"), y=alt.Y("risk_tier:N", sort=["High", "Medium", "Low"], title=None),
            color=alt.Color("risk_tier:N", scale=TIER_SCALE, legend=None),
            tooltip=["risk_tier", "customers", alt.Tooltip("at_risk:Q", format=",.0f", title="₹ at risk")]
        ).properties(title="Customers by risk tier", height=300), use_container_width=True)

    l, r = st.columns(2)
    l.altair_chart(bar(seg_rate(base, "contract_type"), "rate", "contract_type", f"{RATE_NAME} by contract"),
                   use_container_width=True)
    r.altair_chart(bar(seg_rate(base, "circle"), "rate", "circle", f"{RATE_NAME} by circle"),
                   use_container_width=True)

    top = scored[scored.risk_tier != "Low"].reason_1.str.split(":").str[0].value_counts()
    if len(top):
        st.info(f"**Biggest churn driver among at-risk customers:** {top.index[0]} "
                f"({top.iloc[0]:,} customers). Second: {top.index[1] if len(top) > 1 else '-'}.")

elif page == "Churn Analysis":
    st.title("Churn Analysis")
    if not HAS_LABEL:
        st.caption("No churn label in your file, so charts show the model's predicted churn probability.")
    dims = {"Contract type": "contract_type", "Tenure band": "tenure_band", "Circle": "circle",
            "Service type": "service_type", "Payment method": "payment_method", "Network type": "network_type",
            "Monthly charge band": "charge_band", "Acquisition channel": "acquisition_channel",
            "Add-on count": "addon_count"}
    dims = {k: v for k, v in dims.items() if v in base}
    l, r = st.columns(2)
    dim = l.selectbox("Break churn down by", list(dims))
    g = seg_rate(base, dims[dim])
    l.altair_chart(bar(g, "rate", dims[dim], f"{RATE_NAME} by {dim.lower()}"), use_container_width=True)
    l.dataframe(g.sort_values("rate", ascending=False).rename(columns={"rate": RATE_NAME})
                .style.format({RATE_NAME: "{:.1%}"}), hide_index=True, use_container_width=True)

    if DEMO:
        rs = base.dropna(subset=["churn_reason"]).churn_reason.value_counts().reset_index()
        rs.columns = ["reason", "customers"]
        r.altair_chart(bar(rs, "customers", "reason", "Exit reasons (churned customers)", fmt=",.0f"),
                       use_container_width=True)
    drv = scored[scored.risk_tier != "Low"].reason_1.str.split(":").str[0].value_counts().reset_index()
    drv.columns = ["driver", "customers"]
    if len(drv):
        r.altair_chart(bar(drv, "customers", "driver", "Top risk driver - at-risk customers (model)",
                           color=ORANGE, fmt=",.0f"), use_container_width=True)

    if HAS_TIME:
        line = alt.Chart(move).mark_line(point=True, color=BLUE).encode(
            x=alt.X("month:T", title=None), y=alt.Y("churned:Q", title="Churned customers"),
            tooltip=["month:T", "churned"])
        band = alt.Chart(pd.DataFrame({"start": ["2024-07-01", "2025-04-01"], "end": ["2024-09-30", "2025-05-31"],
                                       "event": ["Tariff hike", "Competitor 5G"]})).mark_rect(
            color=ORANGE, opacity=0.12).encode(x="start:T", x2="end:T", tooltip="event")
        st.altair_chart((band + line).properties(title="Churned customers per month (shaded = market events)",
                                                 height=280), use_container_width=True)

elif page == "Revenue Intelligence":
    st.title("Revenue Intelligence")
    if HAS_TIME:
        c = st.columns(4)
        c[0].metric("Total billed (24 M)", inr(bill.amount_billed.sum()))
        c[1].metric("Collection efficiency", f"{bill.amount_paid.sum() / bill.amount_billed.sum():.2%}")
        c[2].metric("MRR lost to churn", inr(base.loc[base.churn_flag == 1, "monthly_charges"].sum()) + " /mo")
        rev = bill.groupby("customer_id").amount_billed.sum().sort_values(ascending=False)
        c[3].metric("Top-20% revenue share", f"{rev.head(int(len(rev) * 0.2)).sum() / rev.sum():.1%}")
        l, r = st.columns(2)
        l.altair_chart(alt.Chart(monthly).mark_line(point=True, color=BLUE).encode(
            x=alt.X("bill_month:T", title=None), y=alt.Y("arpu:Q", title="₹", scale=alt.Scale(zero=False)),
            tooltip=["bill_month:T", alt.Tooltip("arpu:Q", format=".0f")]
        ).properties(title="ARPU per month", height=280), use_container_width=True)
        g = bill.merge(base[["customer_id", "circle"]]).groupby("circle").amount_billed.sum().reset_index(name="revenue")
        r.altair_chart(bar(g, "revenue", "circle", "Revenue by circle (24 M)", fmt=",.0f"), use_container_width=True)
        l, r = st.columns(2)
        clv = D["clv"].copy()
        clv["segment"] = clv.service_type + " | " + clv.contract_type
        l.altair_chart(bar(clv[["segment", "clv"]], "clv", "segment", "Customer lifetime value (₹, gross margin)",
                           fmt=",.0f"), use_container_width=True)
        coh = D["cohort"].reset_index(names="cohort").melt("cohort", var_name="month", value_name="retention").dropna()
        coh["m"] = coh.month.str[1:].astype(int)
        heat = alt.Chart(coh).encode(x=alt.X("month:O", sort=alt.EncodingSortField("m"), title="Months since joining"),
                                     y=alt.Y("cohort:O", title=None))
        r.altair_chart((heat.mark_rect().encode(
            color=alt.Color("retention:Q", scale=alt.Scale(scheme="blues", domain=[0.4, 1]), legend=None),
            tooltip=["cohort", "month", alt.Tooltip("retention:Q", format=".0%")]) +
            heat.mark_text(fontSize=10).encode(text=alt.Text("retention:Q", format=".0%"))
        ).properties(title="Cohort retention", height=300), use_container_width=True)
    else:
        mrr = scored.monthly_charges.sum()
        c = st.columns(4)
        c[0].metric("Monthly revenue (MRR)", inr(mrr))
        c[1].metric("ARPU", f"₹{scored.monthly_charges.mean():,.0f}")
        c[2].metric("Annual revenue at risk", inr(scored.revenue_at_risk.sum()))
        top20 = scored.monthly_charges.sort_values(ascending=False)
        c[3].metric("Top-20% revenue share", f"{top20.head(max(1, int(len(top20) * 0.2))).sum() / mrr:.1%}")
        st.caption("Monthly trend & cohort charts need billing history - they are available in Demo mode.")
        l, r = st.columns(2)
        for col, dim in [(l, "circle"), (r, "service_type")]:
            g = scored.groupby(dim).agg(mrr=("monthly_charges", "sum"), at_risk=("revenue_at_risk", "sum")).reset_index()
            g = g.melt(dim, ["mrr", "at_risk"], var_name="measure", value_name="amount")
            g["measure"] = g.measure.map({"mrr": "Monthly revenue", "at_risk": "Annual revenue at risk"})
            col.altair_chart(alt.Chart(g).mark_bar(cornerRadiusEnd=4).encode(
                y=alt.Y(f"{dim}:N", title=None), yOffset="measure:N", x=alt.X("amount:Q", title="₹"),
                color=alt.Color("measure:N", scale=alt.Scale(range=[BLUE, ORANGE]), title=None),
                tooltip=[dim, "measure", alt.Tooltip("amount:Q", format=",.0f")]
            ).properties(title=f"Revenue vs revenue at risk by {dim.replace('_', ' ')}", height=320),
                use_container_width=True)
        seg = scored.groupby(["service_type", "contract_type"]).agg(
            customers=("customer_id", "count"), arpu=("monthly_charges", "mean"),
            churn_prob=("churn_probability", "mean")).reset_index()
        # expected lifetime from predicted churn over the ~24-month horizon the model was trained on
        monthly_hazard = 1 - (1 - seg.churn_prob.clip(0.01, 0.99)) ** (1 / 24)
        seg["est_clv"] = seg.arpu * 0.40 * (1 / monthly_hazard).clip(upper=120)
        st.dataframe(seg.style.format({"arpu": "₹{:,.0f}", "churn_prob": "{:.1%}", "est_clv": "₹{:,.0f}"}),
                     hide_index=True, use_container_width=True)

elif page == "Risk & Retention":
    st.title("Churn Risk & Retention Playbook")
    if DEMO:
        st.caption("Active customers only (churned customers are already gone).")
    c = st.columns(4)
    for i, t in enumerate(["High", "Medium", "Low"]):
        s = scored[scored.risk_tier == t]
        c[i].metric(f"{t} risk", f"{len(s):,} customers", inr(s.revenue_at_risk.sum()) + " at risk", delta_color="off")
    c[3].metric("Avg churn probability", f"{scored.churn_probability.mean():.1%}")

    st.subheader("Retention campaign simulator")
    a, b, cc = st.columns(3)
    save_rate = a.slider("Save rate (share of churners retained)", 0.10, 0.60, 0.30, 0.05)
    offer_cost = b.slider("Offer cost per customer (₹)", 100, 800, 300, 50)
    tiers = cc.multiselect("Target tiers", ["High", "Medium", "Low"], default=["High", "Medium"])
    tgt = scored[scored.risk_tier.isin(tiers)]
    saved, cost = tgt.revenue_at_risk.sum() * save_rate * 0.40, len(tgt) * offer_cost
    m = st.columns(4)
    m[0].metric("Customers targeted", f"{len(tgt):,}")
    m[1].metric("Campaign cost", inr(cost))
    m[2].metric("Margin saved", inr(saved))
    m[3].metric("Net benefit", inr(saved - cost), f"ROI {((saved - cost) / cost if cost else 0):.0%}")

    l, r = st.columns(2)
    g = scored.groupby(["circle", "risk_tier"]).revenue_at_risk.sum().reset_index()
    l.altair_chart(alt.Chart(g).mark_bar().encode(
        y=alt.Y("circle:N", sort="-x", title=None), x=alt.X("revenue_at_risk:Q", title="₹ at risk"),
        color=alt.Color("risk_tier:N", scale=TIER_SCALE, title="Tier"),
        tooltip=["circle", "risk_tier", alt.Tooltip("revenue_at_risk:Q", format=",.0f")]
    ).properties(title="Revenue at risk by circle", height=300), use_container_width=True)
    g = tgt.groupby("next_best_action").agg(customers=("customer_id", "count")).reset_index()
    if len(g):
        r.altair_chart(bar(g, "customers", "next_best_action", "Next-best action (targeted tiers)", fmt=",.0f"),
                       use_container_width=True)

    st.subheader("Retention call list - with churn reasons")
    cols = ["customer_id", "circle", "service_type", "contract_type", "tenure_months", "monthly_charges",
            "churn_probability", "risk_tier", "revenue_at_risk", "reason_1", "reason_2", "reason_3",
            "next_best_action"]
    show = tgt.sort_values("revenue_at_risk", ascending=False)[cols]
    st.dataframe(show, hide_index=True, use_container_width=True, height=380,
                 column_config={"churn_probability": st.column_config.ProgressColumn(
                     "churn_probability", format="%.2f", min_value=0, max_value=1),
                     "revenue_at_risk": st.column_config.NumberColumn("revenue_at_risk", format="₹%.0f"),
                     "monthly_charges": st.column_config.NumberColumn("monthly_charges", format="₹%.0f")})
    st.download_button("⬇ Download call list (CSV)", show.to_csv(index=False), "retention_call_list.csv", "text/csv")
    st.download_button("⬇ Download ALL scored customers (CSV)",
                       scored.drop(columns=[c for c in scored if c.startswith("effect_")]).to_csv(index=False),
                       "scored_customers.csv", "text/csv")

elif page == "Customer Drill-down":
    st.title("Customer Drill-down")
    st.caption("Pick a customer to see exactly why the model thinks they will (or won't) churn.")
    order = scored.sort_values("churn_probability", ascending=False)
    cid = st.selectbox("Customer (sorted by churn risk)", order.customer_id.tolist())
    i = scored.index[scored.customer_id == cid][0]
    r = scored.loc[i]
    k = st.columns(5)
    k[0].metric("Churn probability", f"{r.churn_probability:.1%}")
    k[1].metric("Risk tier", r.risk_tier)
    k[2].metric("Monthly charges", f"₹{r.monthly_charges:,.0f}")
    k[3].metric("Revenue at risk", inr(r.revenue_at_risk))
    k[4].metric("Tenure", f"{r.tenure_months:.0f} months")
    st.markdown(f"**Recommended action:** {r.next_best_action}")
    l, rr = st.columns([3, 2])
    ch_ = contrib_chart(CONTRIB.loc[i], "What drives this customer's churn risk")
    if ch_ is not None:
        l.altair_chart(ch_, use_container_width=True)
    reasons = [r[f"reason_{n}"] for n in (1, 2, 3) if isinstance(r.get(f"reason_{n}"), str)]
    rr.markdown("**Top reasons**")
    for n, txt in enumerate(reasons, 1):
        eff = r.get(f"effect_{n}")
        rr.markdown(f"{n}. 🔴 {txt}" + (f"  (+{eff:.0%} risk)" if pd.notna(eff) else ""))
    rr.markdown("**Profile**")
    rr.dataframe(pd.DataFrame({"value": r[["circle", "service_type", "contract_type", "payment_method", "avg_csat",
                                            "tickets_per_month", "avg_drop_rate", "late_payment_ratio",
                                            "usage_trend"]].astype(str)}), use_container_width=True)

elif page == "Churn Predictor":
    st.title("Churn Predictor - what-if for one customer")
    feat = E.reference
    with st.form("predict"):
        a, b, c = st.columns(3)
        service = a.selectbox("Service type", E.categories["service_type"])
        contracts = sorted(feat.loc[feat.service_type == service, "contract_type"].unique())
        contract = a.selectbox("Contract type", contracts)
        circle = a.selectbox("Circle", E.categories["circle"])
        payment = a.selectbox("Payment method", E.categories["payment_method"])
        tenure = b.slider("Tenure (months)", 1, 84, 12)
        charges = b.slider("Monthly charges (₹)", 199, 2100, 600, 10)
        data_gb = b.slider("Avg monthly data (GB)", 1, 400, 40)
        usage_trend = b.slider("Recent usage vs normal (1.0 = same)", 0.3, 1.5, 1.0, 0.05)
        tickets = c.slider("Support tickets per month", 0.0, 2.0, 0.2, 0.05)
        net_tickets = c.slider("Network complaints (total)", 0, 15, 1)
        csat = c.slider("Avg CSAT (1-5)", 1.0, 5.0, 4.0, 0.1)
        drop = c.slider("Call-drop rate (%)", 0.1, 8.0, 1.5, 0.1)
        late = c.slider("Late-payment ratio", 0.0, 1.0, 0.05, 0.05)
        go = st.form_submit_button("Predict churn risk", type="primary")
    if go:
        one = pd.DataFrame([{"service_type": service, "contract_type": contract, "circle": circle,
                             "payment_method": payment, "tenure_months": tenure, "monthly_charges": charges,
                             "avg_monthly_data_gb": data_gb, "usage_trend": usage_trend, "tickets_per_month": tickets,
                             "network_tickets": net_tickets, "avg_csat": csat, "avg_drop_rate": drop,
                             "late_payment_ratio": late}])
        X1, _, _ = E.prepare(one)
        s1 = E.score(X1).iloc[0]
        R1, C1 = E.reasons(X1)
        k = st.columns(4)
        k[0].metric("Churn probability", f"{s1.churn_probability:.1%}")
        k[1].metric("Risk tier", s1.risk_tier)
        k[2].metric("Annual revenue at risk", inr(s1.revenue_at_risk))
        k[3].markdown(f"**Next-best action**\n\n{s1.next_best_action}")
        st.progress(float(min(s1.churn_probability, 1.0)))
        l, r = st.columns([3, 2])
        ch_ = contrib_chart(C1.iloc[0], "Why this prediction")
        if ch_ is not None:
            l.altair_chart(ch_, use_container_width=True)
        r.markdown("**Top reasons**")
        for n in (1, 2, 3):
            t = R1.iloc[0][f"reason_{n}"]
            if isinstance(t, str):
                e = R1.iloc[0][f"effect_{n}"]
                r.markdown(f"{n}. 🔴 {t}" + (f"  (+{e:.0%})" if pd.notna(e) else ""))
        st.caption(f"Tier cut-offs: Medium ≥ {E.threshold:.2f} (profit-optimal), High ≥ {E.hi_cut:.2f}. "
                   "Reasons compare this customer with a typical retained customer.")

elif page == "Model Performance":
    st.title("Model Performance")
    if DEMO:
        f = D["final"].iloc[0]
        c = st.columns(5)
        c[0].metric("Model", f["model"])
        c[1].metric("ROC-AUC (test)", f"{f.roc_auc:.3f}")
        c[2].metric("Precision", f"{f.precision:.1%}")
        c[3].metric("Recall", f"{f.recall:.1%}")
        c[4].metric("Threshold", f"{f.threshold:.2f}")
        st.dataframe(D["models"], hide_index=True, use_container_width=True)
        l, r = st.columns(2)
        l.altair_chart(bar(D["imp"].head(12), "importance", "feature", "Top churn drivers (permutation importance)",
                           fmt=".3f"), use_container_width=True)
        for img in ["13_roc_curves.png", "14_profit_curve.png"]:
            if (CH / img).exists():
                r.image(str(CH / img), use_container_width=True)
    elif HAS_LABEL:
        y, p = scored.churn_flag.astype(int), scored.churn_probability
        pred_ = (p >= E.threshold).astype(int)
        c = st.columns(4)
        c[0].metric("ROC-AUC on your data", f"{roc_auc_score(y, p):.3f}")
        c[1].metric("Accuracy", f"{accuracy_score(y, pred_):.1%}")
        c[2].metric("Precision", f"{precision_score(y, pred_, zero_division=0):.1%}")
        c[3].metric("Recall", f"{recall_score(y, pred_, zero_division=0):.1%}")
        cm = pd.crosstab(y.map({0: "Actual: Stay", 1: "Actual: Churn"}),
                         pred_.map({0: "Pred: Stay", 1: "Pred: Churn"}))
        st.dataframe(cm, use_container_width=True)
        st.caption("Evaluated at the profit-optimal threshold. If your data differs a lot from telecom "
                   "customers, consider retraining the model on your own history.")
    else:
        st.info("Add a `churn` (Yes/No) or `churn_flag` (1/0) column to your file to measure model accuracy on it.")
    gimp = CONTRIB.clip(lower=0).mean().sort_values(ascending=False).head(10).reset_index()
    gimp.columns = ["driver", "avg_effect"]
    gimp["driver"] = gimp.driver.map(lambda k: DRIVERS[k][1])
    st.altair_chart(bar(gimp, "avg_effect", "driver", "Average churn-risk contribution across customers",
                        color=ORANGE, fmt=".1%"), use_container_width=True)

st.sidebar.markdown("---")
st.sidebar.caption("Built by Mohit Hingase · Python · SQL · Power BI · Streamlit")
