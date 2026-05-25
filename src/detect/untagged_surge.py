import pandas as pd
from pathlib import Path

PROCESSED_DIR = Path(__file__).parent.parent.parent / "data" / "processed"

ROLLING_WINDOW    = 21   # longer window — direct share is a slow-moving metric
Z_SCORE_THRESHOLD = 2.5  # lower than traffic spike — tracking failures are urgent
MIN_ROLLING_STD   = 0.005  # minimum std for a proportion series (not sessions)


def detect_untagged_surges(df: pd.DataFrame = None) -> list[dict]:
    """
    Detect days where the share of direct/(none) traffic spikes abnormally,
    indicating potential UTM stripping, untagged campaign launches, or
    large email sends without tracking parameters.

    Args:
        df: processed direct_untagged_traffic DataFrame.
            Loads from disk if not provided.

    Returns:
        List of alert dicts, one per flagged day.
    """
    if df is None:
        df = pd.read_csv(
            PROCESSED_DIR / "direct_untagged_traffic.csv",
            parse_dates=["event_date"]
        )

    df = df.sort_values("event_date").copy()

    rolling = df["direct_share"].rolling(
        window=ROLLING_WINDOW,
        min_periods=ROLLING_WINDOW
    )
    df["rolling_mean"] = rolling.mean()
    df["rolling_std"]  = rolling.std().clip(lower=MIN_ROLLING_STD)
    df["z_score"]      = (
        (df["direct_share"] - df["rolling_mean"]) / df["rolling_std"]
    )

    flagged = df[
        df["z_score"].notna() &
        (df["z_score"] > Z_SCORE_THRESHOLD)
    ]

    return [_build_alert(row) for _, row in flagged.iterrows()]


def _build_alert(row: pd.Series) -> dict:
    z = round(float(row["z_score"]), 3)
    direct_pct = round(float(row["direct_share"]) * 100, 1)
    baseline_pct = round(float(row["rolling_mean"]) * 100, 1)
    return {
        "anomaly_type":       "untagged_surge",
        "detected_at":        str(row["event_date"].date()),
        "source":             "(direct)",
        "medium":             "(none)",
        "metric_value":       direct_pct,
        "baseline_value":     baseline_pct,
        "z_score":            z,
        "severity":           "high" if z >= 3.5 else "medium",
        "recommended_action": (
            "Untagged direct traffic surge detected. Audit recent campaign "
            "UTM parameters, check for large email sends without tracking links, "
            "and confirm no URL shorteners or redirects are stripping parameters."
        ),
    }


if __name__ == "__main__":
    alerts = detect_untagged_surges()
    print(f"Untagged surge alerts found: {len(alerts)}")
    for a in alerts:
        print(a)