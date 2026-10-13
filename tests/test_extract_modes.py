from datetime import date

import pandas as pd
import pytest

from src import extract

# Columns, order and dtypes of the legacy CSVs after pd.read_csv, recorded
# from a real legacy extract on 2026-10-13. The dbt mode must reproduce them.
LEGACY_CONTRACT = {
    "traffic_by_source": {
        "event_date": "int64", "source": "object", "medium": "object",
        "sessions": "int64",
    },
    "conversion_rate_by_source": {
        "event_date": "int64", "source": "object", "medium": "object",
        "sessions": "int64", "purchasers": "int64", "conversion_rate": "float64",
    },
    "direct_untagged_traffic": {
        "event_date": "int64", "total_sessions": "int64",
        "direct_sessions": "int64", "direct_share": "float64",
    },
}

CHANNEL_TABLE = "proj.ds.mart_channel_performance_daily"
TRACKING_TABLE = "proj.ds.mart_tracking_quality_daily"


def _channel_mart() -> pd.DataFrame:
    """Mart-shaped rows: honest names, DATE event_date, one users = 0 row."""
    return pd.DataFrame({
        "event_date": [date(2020, 11, 1), date(2020, 11, 1), date(2020, 11, 2)],
        "source": ["google", "(direct)", "google"],
        "medium": ["organic", "(none)", "cpc"],
        "users": [100, 50, 0],
        "session_count": [110, 55, 0],
        "purchasers": [5, 1, 0],
        "user_conversion_rate": [0.05, 0.02, None],
    })


def _tracking_mart() -> pd.DataFrame:
    return pd.DataFrame({
        "event_date": [date(2020, 11, 2), date(2020, 11, 1)],
        "total_users": [80, 140],
        "direct_users": [20, 50],
        "direct_share": [0.25, 50 / 140],
        "data_deleted_users": [3, 4],
        "not_set_users": [0, 0],
        "purchase_events": [0, 6],
        "purchase_events_missing_transaction_id": [0, 1],
        "purchase_events_duplicate_transaction_id": [0, 0],
    })


@pytest.fixture
def fake_bigquery(monkeypatch):
    """Record every SQL string sent and answer mart queries with fixtures."""
    sent = []

    def run_query(client, sql):
        sent.append(sql)
        if CHANNEL_TABLE in sql:
            return _channel_mart()
        if TRACKING_TABLE in sql:
            return _tracking_mart()
        return pd.DataFrame({"event_date": ["20201101"], "x": [1]})

    monkeypatch.setattr(extract, "get_client", lambda: object())
    monkeypatch.setattr(extract, "run_query", run_query)
    monkeypatch.setattr(extract, "PROJECT_ID", "proj")
    monkeypatch.setattr(extract, "DBT_DATASET", "ds")
    return sent


def test_sql_mode_runs_the_three_legacy_files(fake_bigquery, tmp_path):
    extract.extract_all(source="sql", out_dir=tmp_path)
    expected = [extract.load_sql(f"{name}.sql") for name in LEGACY_CONTRACT]
    assert fake_bigquery == expected
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted(
        f"{name}.csv" for name in LEGACY_CONTRACT
    )


def test_default_source_is_sql(fake_bigquery, tmp_path):
    extract.extract_all(out_dir=tmp_path)
    assert fake_bigquery[0] == extract.load_sql("traffic_by_source.sql")


def test_dbt_mode_queries_only_the_two_marts(fake_bigquery, tmp_path):
    extract.extract_all(source="dbt", out_dir=tmp_path)
    assert len(fake_bigquery) == 2
    assert any(f"`{CHANNEL_TABLE}`" in sql for sql in fake_bigquery)
    assert any(f"`{TRACKING_TABLE}`" in sql for sql in fake_bigquery)


@pytest.mark.parametrize("name", list(LEGACY_CONTRACT))
def test_dbt_mode_writes_legacy_columns_order_and_dtypes(fake_bigquery, tmp_path, name):
    extract.extract_all(source="dbt", out_dir=tmp_path)
    df = pd.read_csv(tmp_path / f"{name}.csv")
    assert dict(df.dtypes.astype(str)) == LEGACY_CONTRACT[name]
    assert list(df.columns) == list(LEGACY_CONTRACT[name])


def test_dbt_mode_writes_event_date_as_yyyymmdd(fake_bigquery, tmp_path):
    extract.extract_all(source="dbt", out_dir=tmp_path)
    df = pd.read_csv(tmp_path / "direct_untagged_traffic.csv")
    assert df["event_date"].tolist() == [20201101, 20201102]


def test_dbt_mode_maps_users_to_legacy_sessions(fake_bigquery, tmp_path):
    extract.extract_all(source="dbt", out_dir=tmp_path)
    cvr = pd.read_csv(tmp_path / "conversion_rate_by_source.csv")
    google = cvr[(cvr["source"] == "google") & (cvr["medium"] == "organic")].iloc[0]
    assert google["sessions"] == 100
    assert google["purchasers"] == 5
    assert google["conversion_rate"] == 0.05
    direct = pd.read_csv(tmp_path / "direct_untagged_traffic.csv")
    assert direct["total_sessions"].tolist() == [140, 80]
    assert direct["direct_sessions"].tolist() == [50, 20]


def test_dbt_mode_keeps_zero_user_rows_only_in_conversion(fake_bigquery, tmp_path):
    """Legacy conversion SQL has no WHERE, so it keeps sessions = 0 rows with a
    null rate; legacy traffic SQL filters session_start, so it never has them."""
    extract.extract_all(source="dbt", out_dir=tmp_path)
    cvr = pd.read_csv(tmp_path / "conversion_rate_by_source.csv")
    zero = cvr[cvr["sessions"] == 0]
    assert len(zero) == 1
    assert zero["conversion_rate"].isna().all()
    traffic = pd.read_csv(tmp_path / "traffic_by_source.csv")
    assert len(traffic) == 2
    assert (traffic["sessions"] > 0).all()


def test_unknown_source_rejected(fake_bigquery, tmp_path):
    with pytest.raises(ValueError):
        extract.extract_all(source="csv", out_dir=tmp_path)
    assert fake_bigquery == []
