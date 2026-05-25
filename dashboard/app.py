import json
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# ── Paths ────────────────────────────────────────────────────────────────────
ROOT         = Path(__file__).parent.parent
ALERTS_PATH  = ROOT / "output" / "alerts.json"
PROCESSED    = ROOT / "data" / "processed"

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Customer Journey Anomaly Detector",
    page_icon="🔍",
    layout="wide",
)

# ── Data loaders ─────────────────────────────────────────────────────────────
@st.cache_data
def load_alerts() -> pd.DataFrame:
    if not ALERTS_PATH.exists():
        return pd.DataFrame()
    with open(ALERTS_PATH) as f:
        data = json.load(f)
    df = pd.DataFrame(data)
    df["detected_at"] = pd.to_datetime(df["detected_at"])
    return df


@st.cache_data
def load_traffic() -> pd.DataFrame:
    df = pd.read_csv(PROCESSED / "traffic_by_source.csv", parse_dates=["event_date"])
    return df


@st.cache_data
def load_cvr() -> pd.DataFrame:
    df = pd.read_csv(PROCESSED / "conversion_rate_by_source.csv", parse_dates=["event_date"])
    return df


@st.cache_data
def load_direct() -> pd.DataFrame:
    df = pd.read_csv(PROCESSED / "direct_untagged_traffic.csv", parse_dates=["event_date"])
    return df


# ── Load data ─────────────────────────────────────────────────────────────────
alerts_df  = load_alerts()
traffic_df = load_traffic()
cvr_df     = load_cvr()
direct_df  = load_direct()

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("🔍 Anomaly Detector")
    st.markdown("---")

    severity_filter = st.multiselect(
        "Severity",
        options=["high", "medium"],
        default=["high", "medium"],
    )

    anomaly_filter = st.multiselect(
        "Anomaly Type",
        options=["traffic_spike", "conversion_collapse", "untagged_surge"],
        default=["traffic_spike", "conversion_collapse", "untagged_surge"],
    )

    if not alerts_df.empty:
        min_date = alerts_df["detected_at"].min().date()
        max_date = alerts_df["detected_at"].max().date()
        date_range = st.date_input(
            "Date Range",
            value=(min_date, max_date),
            min_value=min_date,
            max_value=max_date,
        )
    else:
        date_range = None

    st.markdown("---")
    st.caption("Data: Google Merchandise Store GA4 (BigQuery public dataset)")


# ── Filter alerts ─────────────────────────────────────────────────────────────
def filter_alerts(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    df = df[df["severity"].isin(severity_filter)]
    df = df[df["anomaly_type"].isin(anomaly_filter)]
    if date_range and len(date_range) == 2:
        df = df[
            (df["detected_at"].dt.date >= date_range[0]) &
            (df["detected_at"].dt.date <= date_range[1])
        ]
    return df


filtered = filter_alerts(alerts_df)

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs([
    "📊 Overview",
    "📈 Traffic Spike",
    "📉 Conversion Collapse",
    "🔗 Untagged Surge",
])


# ════════════════════════════════════════════════════════════════════════════
# TAB 1 — OVERVIEW
# ════════════════════════════════════════════════════════════════════════════
with tab1:
    st.header("Anomaly Overview")
    st.caption(
        "Summary of all detected anomalies across traffic volume, "
        "conversion rate, and tracking integrity signals."
    )

    # ── KPI cards ────────────────────────────────────────────────────────────
    col1, col2, col3, col4 = st.columns(4)

    total  = len(filtered)
    high   = len(filtered[filtered["severity"] == "high"]) if not filtered.empty else 0
    medium = len(filtered[filtered["severity"] == "medium"]) if not filtered.empty else 0
    types  = filtered["anomaly_type"].nunique() if not filtered.empty else 0

    col1.metric("Total Alerts",    total)
    col2.metric("High Severity",   high,   delta=None)
    col3.metric("Medium Severity", medium, delta=None)
    col4.metric("Anomaly Types",   types)

    st.markdown("---")

    # ── Timeline chart ────────────────────────────────────────────────────────
    st.subheader("Alert Timeline")

    if filtered.empty:
        st.info("No alerts match the current filters.")
    else:
        timeline = (
            filtered
            .groupby(["detected_at", "anomaly_type"])
            .size()
            .reset_index(name="count")
        )

        colour_map = {
            "traffic_spike":        "#EF553B",
            "conversion_collapse":  "#FFA15A",
            "untagged_surge":       "#636EFA",
        }

        fig = px.bar(
            timeline,
            x="detected_at",
            y="count",
            color="anomaly_type",
            color_discrete_map=colour_map,
            labels={
                "detected_at":  "Date",
                "count":        "Alerts",
                "anomaly_type": "Type",
            },
            title="Daily Alert Count by Anomaly Type",
        )
        fig.update_layout(
            xaxis_title="Date",
            yaxis_title="Number of Alerts",
            legend_title="Anomaly Type",
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            bargap=0.2,
        )
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")

    # ── Alerts table ──────────────────────────────────────────────────────────
    st.subheader("All Alerts")

    if filtered.empty:
        st.info("No alerts match the current filters.")
    else:
        display_cols = [
            "detected_at", "anomaly_type", "source", "medium",
            "severity", "metric_value", "baseline_value", "recommended_action",
        ]
        # Only show columns that exist (traffic_spike has z_score,
        # conversion_collapse has relative_drop_pct)
        available = [c for c in display_cols if c in filtered.columns]

        display_df = filtered[available].copy()
        display_df["detected_at"] = display_df["detected_at"].dt.date
        st.dataframe(
            display_df.sort_values("detected_at"),
            use_container_width=True,
            hide_index=True,
        )

# ════════════════════════════════════════════════════════════════════════════
# TAB 2 — TRAFFIC SPIKE
# ════════════════════════════════════════════════════════════════════════════
with tab2:
    st.header("Traffic Spike Detection")
    st.caption(
        "Daily session volume per source/medium with 14-day rolling baseline. "
        "Flagged days exceed 3 standard deviations above the rolling mean."
    )

    spike_alerts = filtered[filtered["anomaly_type"] == "traffic_spike"]

    col1, col2 = st.columns(2)
    col1.metric("Traffic Spike Alerts", len(spike_alerts))
    col2.metric(
        "High Severity",
        len(spike_alerts[spike_alerts["severity"] == "high"])
        if not spike_alerts.empty else 0
    )

    st.markdown("---")

    sources = sorted(traffic_df["source"].unique().tolist())
    selected_source = st.selectbox(
        "Select Source / Medium",
        options=traffic_df.groupby(["source", "medium"])
                          .size().reset_index()[["source", "medium"]]
                          .apply(lambda r: f"{r['source']} / {r['medium']}", axis=1)
                          .tolist(),
        key="traffic_source_select",
    )

    src, med = selected_source.split(" / ", 1)
    series = traffic_df[
        (traffic_df["source"] == src) &
        (traffic_df["medium"] == med)
    ].sort_values("event_date").copy()

    # Compute rolling baseline for display
    series["rolling_mean"] = (
        series["sessions"]
        .rolling(window=14, min_periods=14)
        .mean()
    )

    # Flagged dates for this source/medium
    flagged_dates = set()
    if not spike_alerts.empty:
        mask = (spike_alerts["source"] == src) & (spike_alerts["medium"] == med)
        flagged_dates = set(
            spike_alerts[mask]["detected_at"].dt.date.astype(str)
        )

    series["flagged"] = series["event_date"].dt.date.astype(str).isin(flagged_dates)

    fig = go.Figure()

    # Session volume line
    fig.add_trace(go.Scatter(
        x=series["event_date"],
        y=series["sessions"],
        mode="lines",
        name="Daily Sessions",
        line=dict(color="#636EFA", width=2),
    ))

    # Rolling mean line
    fig.add_trace(go.Scatter(
        x=series["event_date"],
        y=series["rolling_mean"],
        mode="lines",
        name="14-day Rolling Mean",
        line=dict(color="#AAAAAA", width=1.5, dash="dash"),
    ))

    # Flagged points
    flagged_series = series[series["flagged"]]
    if not flagged_series.empty:
        fig.add_trace(go.Scatter(
            x=flagged_series["event_date"],
            y=flagged_series["sessions"],
            mode="markers",
            name="Anomaly Flagged",
            marker=dict(color="#EF553B", size=10, symbol="x"),
        ))

    fig.update_layout(
        title=f"Daily Sessions — {src} / {med}",
        xaxis_title="Date",
        yaxis_title="Sessions",
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    st.plotly_chart(fig, use_container_width=True)

    if spike_alerts.empty:
        st.info("No traffic spike alerts detected in the current date range.")
    else:
        st.subheader("Traffic Spike Alerts")
        display = spike_alerts.copy()
        display["detected_at"] = display["detected_at"].dt.date
        st.dataframe(
            display[["detected_at", "source", "medium", "metric_value",
                      "baseline_value", "z_score", "severity",
                      "recommended_action"]],
            use_container_width=True,
            hide_index=True,
        )


# ════════════════════════════════════════════════════════════════════════════
# TAB 3 — CONVERSION COLLAPSE
# ════════════════════════════════════════════════════════════════════════════
with tab3:
    st.header("Conversion Rate Collapse Detection")
    st.caption(
        "Daily conversion rate per source/medium with 14-day rolling baseline. "
        "Flagged days show a relative drop exceeding 60% against the rolling mean, "
        "with a minimum absolute drop of 1 percentage point."
    )

    cvr_alerts = filtered[filtered["anomaly_type"] == "conversion_collapse"]

    col1, col2 = st.columns(2)
    col1.metric("Conversion Collapse Alerts", len(cvr_alerts))
    col2.metric(
        "High Severity",
        len(cvr_alerts[cvr_alerts["severity"] == "high"])
        if not cvr_alerts.empty else 0
    )

    st.markdown("---")

    selected_cvr_source = st.selectbox(
        "Select Source / Medium",
        options=cvr_df.groupby(["source", "medium"])
                      .size().reset_index()[["source", "medium"]]
                      .apply(lambda r: f"{r['source']} / {r['medium']}", axis=1)
                      .tolist(),
        key="cvr_source_select",
    )

    src_c, med_c = selected_cvr_source.split(" / ", 1)
    cvr_series = cvr_df[
        (cvr_df["source"] == src_c) &
        (cvr_df["medium"] == med_c)
    ].sort_values("event_date").copy()

    cvr_series["rolling_mean_cvr"] = (
        cvr_series["conversion_rate"]
        .rolling(window=14, min_periods=14)
        .mean()
    )

    flagged_cvr_dates = set()
    if not cvr_alerts.empty:
        mask = (cvr_alerts["source"] == src_c) & (cvr_alerts["medium"] == med_c)
        flagged_cvr_dates = set(
            cvr_alerts[mask]["detected_at"].dt.date.astype(str)
        )

    cvr_series["flagged"] = (
        cvr_series["event_date"].dt.date.astype(str).isin(flagged_cvr_dates)
    )

    fig2 = go.Figure()

    # CVR line
    fig2.add_trace(go.Scatter(
        x=cvr_series["event_date"],
        y=(cvr_series["conversion_rate"] * 100).round(3),
        mode="lines",
        name="Daily CVR %",
        line=dict(color="#00CC96", width=2),
    ))

    # Rolling mean
    fig2.add_trace(go.Scatter(
        x=cvr_series["event_date"],
        y=(cvr_series["rolling_mean_cvr"] * 100).round(3),
        mode="lines",
        name="14-day Rolling Mean",
        line=dict(color="#AAAAAA", width=1.5, dash="dash"),
    ))

    # Flagged points
    flagged_cvr = cvr_series[cvr_series["flagged"]]
    if not flagged_cvr.empty:
        fig2.add_trace(go.Scatter(
            x=flagged_cvr["event_date"],
            y=(flagged_cvr["conversion_rate"] * 100).round(3),
            mode="markers",
            name="Anomaly Flagged",
            marker=dict(color="#EF553B", size=10, symbol="x"),
        ))

    fig2.update_layout(
        title=f"Conversion Rate (%) — {src_c} / {med_c}",
        xaxis_title="Date",
        yaxis_title="Conversion Rate (%)",
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    st.plotly_chart(fig2, use_container_width=True)

    if cvr_alerts.empty:
        st.info("No conversion collapse alerts in the current date range.")
    else:
        st.subheader("Conversion Collapse Alerts")
        display_cvr = cvr_alerts.copy()
        display_cvr["detected_at"] = display_cvr["detected_at"].dt.date
        display_cvr["metric_value"]   = (display_cvr["metric_value"] * 100).round(3)
        display_cvr["baseline_value"] = (display_cvr["baseline_value"] * 100).round(3)
        st.dataframe(
            display_cvr[[
                "detected_at", "source", "medium",
                "metric_value", "baseline_value", "relative_drop_pct",
                "severity", "recommended_action"
            ]].rename(columns={
                "metric_value":   "cvr_%",
                "baseline_value": "baseline_cvr_%",
            }),
            use_container_width=True,
            hide_index=True,
        )


# ════════════════════════════════════════════════════════════════════════════
# TAB 4 — UNTAGGED SURGE
# ════════════════════════════════════════════════════════════════════════════
with tab4:
    st.header("Untagged Traffic Surge Detection")
    st.caption(
        "Daily share of direct/(none) traffic across the site with 21-day rolling baseline. "
        "A spike indicates potential UTM stripping, untagged campaign launches, "
        "or large email sends without tracking parameters."
    )

    surge_alerts = filtered[filtered["anomaly_type"] == "untagged_surge"]

    col1, col2 = st.columns(2)
    col1.metric("Untagged Surge Alerts", len(surge_alerts))
    col2.metric(
        "High Severity",
        len(surge_alerts[surge_alerts["severity"] == "high"])
        if not surge_alerts.empty else 0
    )

    st.markdown("---")

    direct_series = direct_df.sort_values("event_date").copy()
    direct_series["rolling_mean"] = (
        direct_series["direct_share"]
        .rolling(window=21, min_periods=21)
        .mean()
    )
    direct_series["rolling_std"] = (
        direct_series["direct_share"]
        .rolling(window=21, min_periods=21)
        .std()
        .clip(lower=0.005)
    )
    direct_series["upper_band"] = (
        direct_series["rolling_mean"] + 2.5 * direct_series["rolling_std"]
    )

    flagged_surge_dates = set()
    if not surge_alerts.empty:
        flagged_surge_dates = set(
            surge_alerts["detected_at"].dt.date.astype(str)
        )

    direct_series["flagged"] = (
        direct_series["event_date"].dt.date.astype(str).isin(flagged_surge_dates)
    )

    fig3 = go.Figure()

    # Upper band fill
    fig3.add_trace(go.Scatter(
        x=direct_series["event_date"],
        y=(direct_series["upper_band"] * 100).round(2),
        mode="lines",
        name="Alert Threshold (2.5σ)",
        line=dict(color="#FFA15A", width=1, dash="dot"),
        fill=None,
    ))

    # Direct share area
    fig3.add_trace(go.Scatter(
        x=direct_series["event_date"],
        y=(direct_series["direct_share"] * 100).round(2),
        mode="lines",
        name="Direct Share %",
        line=dict(color="#636EFA", width=2),
        fill="tonexty",
        fillcolor="rgba(99,110,250,0.1)",
    ))

    # Rolling mean
    fig3.add_trace(go.Scatter(
        x=direct_series["event_date"],
        y=(direct_series["rolling_mean"] * 100).round(2),
        mode="lines",
        name="21-day Rolling Mean",
        line=dict(color="#AAAAAA", width=1.5, dash="dash"),
    ))

    # Flagged points
    flagged_direct = direct_series[direct_series["flagged"]]
    if not flagged_direct.empty:
        fig3.add_trace(go.Scatter(
            x=flagged_direct["event_date"],
            y=(flagged_direct["direct_share"] * 100).round(2),
            mode="markers",
            name="Anomaly Flagged",
            marker=dict(color="#EF553B", size=10, symbol="x"),
        ))

    fig3.update_layout(
        title="Direct / Untagged Traffic Share (%)",
        xaxis_title="Date",
        yaxis_title="Direct Share (%)",
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    st.plotly_chart(fig3, use_container_width=True)

    if surge_alerts.empty:
        st.info(
            "No untagged surge alerts detected. "
            "Direct traffic share is within normal range throughout the period."
        )
    else:
        st.subheader("Untagged Surge Alerts")
        display_surge = surge_alerts.copy()
        display_surge["detected_at"] = display_surge["detected_at"].dt.date
        st.dataframe(
            display_surge[[
                "detected_at", "metric_value", "baseline_value",
                "z_score", "severity", "recommended_action"
            ]],
            use_container_width=True,
            hide_index=True,
        )