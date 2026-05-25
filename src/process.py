import pandas as pd
from pathlib import Path

RAW_DIR = Path(__file__).parent.parent / "data" / "raw"
PROCESSED_DIR = Path(__file__).parent.parent / "data" / "processed"
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

# Minimum daily sessions for a source/medium to be included in detection.
# Below this, variance is too high to distinguish signal from noise.
MIN_SESSIONS = 30


def parse_event_date(df: pd.DataFrame) -> pd.DataFrame:
    df["event_date"] = pd.to_datetime(df["event_date"], format="%Y%m%d")
    return df


def filter_other(df: pd.DataFrame) -> pd.DataFrame:
    """Remove BigQuery's <Other> sampling bucket — not a real source."""
    mask = (df["source"] != "<Other>") & (df["medium"] != "<Other>")
    removed = (~mask).sum()
    if removed > 0:
        print(f"    Filtered {removed} <Other> rows")
    return df[mask].reset_index(drop=True)


def process_traffic_by_source() -> pd.DataFrame:
    df = pd.read_csv(RAW_DIR / "traffic_by_source.csv")
    df = parse_event_date(df)
    df = filter_other(df)

    # Drop source/medium combos that never exceed MIN_SESSIONS on any day.
    # These are too low-volume for reliable anomaly detection.
    max_sessions = df.groupby(["source", "medium"])["sessions"].transform("max")
    before = len(df)
    df = df[max_sessions >= MIN_SESSIONS].reset_index(drop=True)
    print(f"    Retained {len(df)}/{before} rows after min_sessions filter")

    df = df.sort_values(["source", "medium", "event_date"]).reset_index(drop=True)
    return df


def process_conversion_rate_by_source() -> pd.DataFrame:
    df = pd.read_csv(RAW_DIR / "conversion_rate_by_source.csv")
    df = parse_event_date(df)
    df = filter_other(df)

    # Same volume filter — only sources that regularly see >= MIN_SESSIONS.
    max_sessions = df.groupby(["source", "medium"])["sessions"].transform("max")
    before = len(df)
    df = df[max_sessions >= MIN_SESSIONS].reset_index(drop=True)
    print(f"    Retained {len(df)}/{before} rows after min_sessions filter")

    # Ensure conversion_rate is clean (SAFE_DIVIDE already handles nulls,
    # but enforce float and fill any remaining NaN as 0).
    df["conversion_rate"] = df["conversion_rate"].fillna(0.0).astype(float)

    df = df.sort_values(["source", "medium", "event_date"]).reset_index(drop=True)
    return df


def process_direct_untagged_traffic() -> pd.DataFrame:
    df = pd.read_csv(RAW_DIR / "direct_untagged_traffic.csv")
    df = parse_event_date(df)

    # No source/medium columns here — it's already site-wide daily.
    df["direct_share"] = df["direct_share"].fillna(0.0).astype(float)

    df = df.sort_values("event_date").reset_index(drop=True)
    return df


def process_all() -> None:
    print("  Processing: traffic_by_source")
    df_traffic = process_traffic_by_source()
    df_traffic.to_csv(PROCESSED_DIR / "traffic_by_source.csv", index=False)
    print(f"    Saved: {len(df_traffic)} rows\n")

    print("  Processing: conversion_rate_by_source")
    df_cvr = process_conversion_rate_by_source()
    df_cvr.to_csv(PROCESSED_DIR / "conversion_rate_by_source.csv", index=False)
    print(f"    Saved: {len(df_cvr)} rows\n")

    print("  Processing: direct_untagged_traffic")
    df_direct = process_direct_untagged_traffic()
    df_direct.to_csv(PROCESSED_DIR / "direct_untagged_traffic.csv", index=False)
    print(f"    Saved: {len(df_direct)} rows\n")


if __name__ == "__main__":
    print("Starting processing...")
    process_all()
    print("Processing complete.")