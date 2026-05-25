import pandas as pd
from pathlib import Path

PROCESSED_DIR = Path(__file__).parent.parent.parent / "data" / "processed"

ROLLING_WINDOW         = 14    # days of history to build baseline
DROP_THRESHOLD         = 0.60  # 60% relative drop from baseline triggers alert
MIN_ABS_CVR_DROP       = 0.01  # minimum absolute CVR drop (1 percentage point)
MIN_SESSIONS_ON_DAY    = 30    # ignore low-traffic days
MIN_BASELINE_CVR       = 0.001 # ignore sources with near-zero baseline CVR

def detect_conversion_collapses(df: pd.DataFrame = None) -> list[dict]:
    """
    Detect days where conversion rate for a source/medium drops
    significantly below its 14-day rolling baseline.

    Args:
        df: processed conversion_rate_by_source DataFrame.
            Loads from disk if not provided.

    Returns:
        List of alert dicts, one per flagged day per source/medium.
    """
    if df is None:
        df = pd.read_csv(
            PROCESSED_DIR / "conversion_rate_by_source.csv",
            parse_dates=["event_date"]
        )

    alerts = []

    for (source, medium), group in df.groupby(["source", "medium"]):
        group = group.sort_values("event_date").copy()

        rolling = group["conversion_rate"].rolling(
            window=ROLLING_WINDOW,
            min_periods=ROLLING_WINDOW
        )
        group["rolling_mean_cvr"] = rolling.mean()

        # Skip rows where window not yet populated
        group = group[group["rolling_mean_cvr"].notna()].copy()

        # Skip groups where baseline CVR is near zero — no meaningful collapse possible
        if group["rolling_mean_cvr"].mean() < MIN_BASELINE_CVR:
            continue

        group["relative_drop"] = (
            (group["rolling_mean_cvr"] - group["conversion_rate"])
            / group["rolling_mean_cvr"]
        )

        group["abs_cvr_drop"] = group["rolling_mean_cvr"] - group["conversion_rate"]

        flagged = group[
            (group["relative_drop"] > DROP_THRESHOLD) &
            (group["abs_cvr_drop"] >= MIN_ABS_CVR_DROP) &
            (group["sessions"] >= MIN_SESSIONS_ON_DAY)
        ]

        for _, row in flagged.iterrows():
            alerts.append(_build_alert(row, source, medium))

    return alerts


def _build_alert(row: pd.Series, source: str, medium: str) -> dict:
    drop_pct = round(float(row["relative_drop"]) * 100, 1)
    return {
        "anomaly_type":       "conversion_collapse",
        "detected_at":        str(row["event_date"].date()),
        "source":             source,
        "medium":             medium,
        "metric_value":       round(float(row["conversion_rate"]), 5),
        "baseline_value":     round(float(row["rolling_mean_cvr"]), 5),
        "relative_drop_pct":  drop_pct,
        "severity":           "high" if drop_pct >= 75.0 else "medium",
        "recommended_action": _recommend(source, medium),
    }


def _recommend(source: str, medium: str) -> str:
    if medium == "cpc":
        return (
            "Paid search conversion rate collapsed. Check landing page "
            "integrity, ad-to-page message match, and purchase event firing."
        )
    if medium == "organic":
        return (
            "Organic conversion rate collapsed. Investigate landing page "
            "changes, checkout errors, or GA4 purchase event misfiring."
        )
    if medium == "(none)":
        return (
            "Direct traffic conversion rate collapsed. Check for session "
            "stitching issues, checkout flow errors, or cookie problems."
        )
    if medium == "referral":
        return (
            "Referral conversion rate collapsed. Confirm referral source "
            "quality and whether landing page is correctly configured."
        )
    return (
        "Conversion rate drop detected. Audit tracking setup, landing page "
        "health, and checkout funnel for this source/medium."
    )


if __name__ == "__main__":
    alerts = detect_conversion_collapses()
    print(f"Conversion collapse alerts found: {len(alerts)}")
    for a in alerts:
        print(a)