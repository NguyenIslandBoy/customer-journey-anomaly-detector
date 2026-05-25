import os
from pathlib import Path
from dotenv import load_dotenv
from google.cloud import bigquery
from google.oauth2 import service_account
import pandas as pd

load_dotenv()

PROJECT_ID = os.getenv("BQ_PROJECT_ID")
CREDENTIALS_PATH = os.getenv("BQ_CREDENTIALS_PATH")

SQL_DIR = Path(__file__).parent.parent / "sql"
RAW_DIR = Path(__file__).parent.parent / "data" / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)


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


def extract_all() -> None:
    client = get_client()

    queries = {
        "traffic_by_source":         "traffic_by_source.sql",
        "conversion_rate_by_source": "conversion_rate_by_source.sql",
        "direct_untagged_traffic":   "direct_untagged_traffic.sql",
    }

    for name, sql_file in queries.items():
        print(f"  Running: {sql_file}")
        sql = load_sql(sql_file)
        df = run_query(client, sql)
        out_path = RAW_DIR / f"{name}.csv"
        df.to_csv(out_path, index=False)
        print(f"  Saved:   {out_path}  ({len(df)} rows)")


if __name__ == "__main__":
    print("Starting extraction...")
    extract_all()
    print("Extraction complete.")