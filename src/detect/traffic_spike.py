import pandas as pd
from pathlib import Path

PROCESSED_DIR = Path(__file__).parent.parent.parent / "data" / "processed"

ROLLING_WINDOW = 14      # days of history to build baseline
Z_SCORE_THRESHOLD = 3.0  # standard deviations above mean to flag
MIN_ROLLING_STD = 1.0    # prevents division by near-zero std on flat series


def detect_traffic_spikes(df: pd.DataFrame = None) -> list[dict]:
    """
    Detect days where session volume for a source/medium spikes
    abnormally above its 14-day rolling baseline.

    Args:
        df: processed traffic_by_source DataFrame.
            Loads from disk if not provided.

    Returns:
        List of alert dicts, one per flagged day per source/medium.
    """
    if df is None:
        df = pd.read_csv(PROCESSED_DIR / "traffic_by_source.csv", parse_dates=["event_date"])

    alerts = []

    for (source, medium), group in df.groupby(["source", "medium"]):
        group = group.sort_values("event_date").copy()

        rolling = group["sessions"].rolling(window=ROLLING_WINDOW, min_periods=ROLLING_WINDOW)
        group["rolling_mean"] = rolling.mean()
        group["rolling_std"]  = rolling.std().clip(lower=MIN_ROLLING_STD)
        group["z_score"]      = (
            (group["sessions"] - group["rolling_mean"]) / group["rolling_std"]
        )

        # Only evaluate rows where the rolling window is fully populated
        flagged = group[
            group["z_score"].notna() &
            (group["z_score"] > Z_SCORE_THRESHOLD)
        ]

        for _, row in flagged.iterrows():
            alerts.append(_build_alert(row, source, medium))

    return alerts


def _build_alert(row: pd.Series, source: str, medium: str) -> dict:
    z = round(float(row["z_score"]), 3)
    return {
        "anomaly_type":       "traffic_spike",
        "detected_at":        str(row["event_date"].date()),
        "source":             source,
        "medium":             medium,
        "metric_value":       int(row["sessions"]),
        "baseline_value":     round(float(row["rolling_mean"]), 1),
        "z_score":            z,
        "severity":           "high" if z >= 4.0 else "medium",
        "recommended_action": _recommend(source, medium),
    }


def _recommend(source: str, medium: str) -> str:
    if medium == "cpc":
        return (
            "Paid traffic spike detected. Check for campaign budget error, "
            "bidding anomaly, or bot/invalid click activity on this source."
        )
    if medium == "organic":
        return (
            "Organic traffic spike detected. Investigate for viral content, "
            "unexpected press coverage, or tracking duplication."
        )
    if medium == "(none)":
        return (
            "Direct traffic spike detected. Check for untagged campaign launch, "
            "large email send without UTM parameters, or dark social sharing."
        )
    if medium == "referral":
        return (
            "Referral spike detected. Identify the referring domain and confirm "
            "whether traffic is legitimate or bot-driven."
        )
    return (
        "Unusual session spike detected. Investigate source/medium for campaign "
        "errors, bot traffic, or tracking issues."
    )


if __name__ == "__main__":
    alerts = detect_traffic_spikes()
    print(f"Traffic spike alerts found: {len(alerts)}")
    for a in alerts:
        print(a)