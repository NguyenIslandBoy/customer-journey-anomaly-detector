import os
from pathlib import Path
from dotenv import load_dotenv
from google.cloud import bigquery
from google.oauth2 import service_account
import pandas as pd

load_dotenv()

PROJECT_ID = os.getenv("BQ_PROJECT_ID")
CREDENTIALS_PATH = os.getenv("BQ_CREDENTIALS_PATH")
DBT_DATASET = os.getenv("DBT_DATASET", "cja_dbt")

SQL_DIR = Path(__file__).parent.parent / "sql"
RAW_DIR = Path(__file__).parent.parent / "data" / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

SOURCES = ("sql", "dbt")

LEGACY_QUERIES = {
    "traffic_by_source":         "traffic_by_source.sql",
    "conversion_rate_by_source": "conversion_rate_by_source.sql",
    "direct_untagged_traffic":   "direct_untagged_traffic.sql",
}


def get_client() -> bigquery.Client:
    credentials = service_account.Credentials.from_service_account_file(
        CREDENTIALS_PATH,
        scopes=["https://www.googleapis.com/auth/bigquery"]
    )
    return bigquery.Client(project=PROJECT_ID, credentials=credentials)


def load_sql(filename: str) -> str:
    path = SQL_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"SQL file not found: {path}")
    return path.read_text()


def run_query(client: bigquery.Client, sql: str) -> pd.DataFrame:
    query_job = client.query(sql)
    return query_job.to_dataframe()


def _yyyymmdd(dates: pd.Series) -> pd.Series:
    """DATE column -> 'YYYYMMDD' strings, the legacy format process.py parses."""
    return pd.to_datetime(dates).dt.strftime("%Y%m%d")


def legacy_frames_from_marts(
    channel: pd.DataFrame, tracking: pd.DataFrame
) -> dict[str, pd.DataFrame]:
    """
    Rebuild the three extracts of the sql mode from the dbt marts: same
    files, column names, order and event_date format.

    The only rename is user_conversion_rate -> conversion_rate. users,
    total_users and direct_users already match the sql mode's columns; they
    count distinct users with a session_start (the marts' session_count is
    the real session count, and is not used by the pipeline).
    """
    channel = channel.assign(event_date=_yyyymmdd(channel["event_date"])).rename(
        columns={"user_conversion_rate": "conversion_rate"}
    )
    tracking = tracking.assign(event_date=_yyyymmdd(tracking["event_date"]))

    # The conversion SQL has no WHERE, so it keeps rows with users = 0
    # (events but no session_start) and a null rate. The traffic SQL reads
    # session_start events only, so those rows never appear there.
    conversion = channel[
        ["event_date", "source", "medium", "users", "purchasers", "conversion_rate"]
    ].sort_values(["event_date", "source", "medium"])
    traffic = channel.loc[
        channel["users"] > 0, ["event_date", "source", "medium", "users"]
    ].sort_values(
        ["event_date", "users", "source", "medium"],
        ascending=[True, False, True, True],
    )
    direct = tracking[
        ["event_date", "total_users", "direct_users", "direct_share"]
    ].sort_values("event_date")

    return {
        "traffic_by_source":         traffic.reset_index(drop=True),
        "conversion_rate_by_source": conversion.reset_index(drop=True),
        "direct_untagged_traffic":   direct.reset_index(drop=True),
    }


def _extract_sql(client: bigquery.Client) -> dict[str, pd.DataFrame]:
    frames = {}
    for name, sql_file in LEGACY_QUERIES.items():
        print(f"  Running: {sql_file}")
        frames[name] = run_query(client, load_sql(sql_file))
    return frames


def _extract_dbt(client: bigquery.Client) -> dict[str, pd.DataFrame]:
    dataset = f"{PROJECT_ID}.{DBT_DATASET}"
    print(f"  Reading: {dataset}.mart_channel_performance_daily")
    channel = run_query(client, f"""
        SELECT event_date, source, medium, users, purchasers, user_conversion_rate
        FROM `{dataset}.mart_channel_performance_daily`
    """)
    print(f"  Reading: {dataset}.mart_tracking_quality_daily")
    tracking = run_query(client, f"""
        SELECT event_date, total_users, direct_users, direct_share
        FROM `{dataset}.mart_tracking_quality_daily`
    """)
    return legacy_frames_from_marts(channel, tracking)


def extract_all(source: str = "sql", out_dir: Path = RAW_DIR) -> None:
    """
    Write the three raw CSVs to out_dir.

    Args:
        source:  "sql" runs the legacy queries in sql/. "dbt" reads the dbt
                 marts in DBT_DATASET (build them first with dbt build).
        out_dir: target directory, data/raw/ by default.
    """
    if source not in SOURCES:
        raise ValueError(f"Unknown source {source!r}; expected one of {SOURCES}")

    client = get_client()
    frames = _extract_sql(client) if source == "sql" else _extract_dbt(client)

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, df in frames.items():
        out_path = out_dir / f"{name}.csv"
        df.to_csv(out_path, index=False)
        print(f"  Saved:   {out_path}  ({len(df)} rows)")


if __name__ == "__main__":
    print("Starting extraction...")
    extract_all()
    print("Extraction complete.")