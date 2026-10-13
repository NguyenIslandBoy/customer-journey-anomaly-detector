"""
Parity check: legacy SQL extracts vs dbt-mart extracts.

Runs both extract modes (sql -> data/raw/, dbt -> data/raw_dbt/), compares
each CSV exactly, then runs processing and the detectors on each side and
compares the alert lists. Build the marts first (dbt build).

    python scripts/parity_check.py                 # extract both, compare
    python scripts/parity_check.py --skip-extract  # compare existing files

Exit code 0 only when every file has zero mismatching rows and the alert
lists are identical.
"""
import argparse
import json
import sys
from contextlib import contextmanager
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import process  # noqa: E402
from src.alert import SEVERITY_ORDER  # noqa: E402
from src.detect.conversion_collapse import detect_conversion_collapses  # noqa: E402
from src.detect.traffic_spike import detect_traffic_spikes  # noqa: E402
from src.detect.untagged_surge import detect_untagged_surges  # noqa: E402
from src.extract import extract_all  # noqa: E402

SQL_DIR = ROOT / "data" / "raw"
DBT_DIR = ROOT / "data" / "raw_dbt"

KEYS = {
    "traffic_by_source":         ["event_date", "source", "medium"],
    "conversion_rate_by_source": ["event_date", "source", "medium"],
    "direct_untagged_traffic":   ["event_date"],
}

# Alert fields that legitimately differ between runs. alert_id is a uuid4
# assigned in src/alert.py; this script calls the detectors directly, so it
# is never generated here, and it is listed for the record.
RUN_SPECIFIC_ALERT_FIELDS = ["alert_id"]


def read_raw(path: Path, keys: list[str]) -> pd.DataFrame:
    # round_trip: the default C parser can be off by 1 ulp on some floats,
    # which would report bit-identical values as different.
    df = pd.read_csv(path, float_precision="round_trip")
    return df.sort_values(keys).reset_index(drop=True)


def compare_file(name: str) -> dict:
    keys = KEYS[name]
    sql = read_raw(SQL_DIR / f"{name}.csv", keys)
    dbt = read_raw(DBT_DIR / f"{name}.csv", keys)
    problems = []

    if list(sql.columns) != list(dbt.columns):
        problems.append(f"columns differ: {list(sql.columns)} vs {list(dbt.columns)}")
    if dict(sql.dtypes) != dict(dbt.dtypes):
        problems.append(f"dtypes differ: {dict(sql.dtypes)} vs {dict(dbt.dtypes)}")
    for side, df in (("sql", sql), ("dbt", dbt)):
        if df.duplicated(keys).any():
            problems.append(f"duplicate keys on the {side} side")

    merged = sql.merge(dbt, on=keys, how="outer", suffixes=("_sql", "_dbt"), indicator=True)
    one_sided = merged["_merge"] != "both"
    value_diff = pd.Series(False, index=merged.index)
    for col in (c for c in sql.columns if c not in keys and c in dbt.columns):
        a, b = merged[f"{col}_sql"], merged[f"{col}_dbt"]
        # Exact comparison; two nulls count as equal.
        value_diff |= ~((a == b) | (a.isna() & b.isna()))
    mismatching = one_sided | (value_diff & ~one_sided)

    return {
        "file": f"{name}.csv",
        "rows_sql": len(sql),
        "rows_dbt": len(dbt),
        "only_sql": int((merged["_merge"] == "left_only").sum()),
        "only_dbt": int((merged["_merge"] == "right_only").sum()),
        "mismatching_rows": int(mismatching.sum()),
        "problems": problems,
        "examples": merged[mismatching].head(5),
    }


@contextmanager
def raw_dir(path: Path):
    original = process.RAW_DIR
    process.RAW_DIR = path
    try:
        yield
    finally:
        process.RAW_DIR = original


def alerts_from(path: Path) -> list[dict]:
    """Same processing and detectors as the pipeline, without writing files."""
    with raw_dir(path):
        traffic = process.process_traffic_by_source()
        cvr = process.process_conversion_rate_by_source()
        direct = process.process_direct_untagged_traffic()
    alerts = (
        detect_traffic_spikes(traffic)
        + detect_conversion_collapses(cvr)
        + detect_untagged_surges(direct)
    )
    # Same ordering as src/alert.py.
    alerts.sort(key=lambda a: (SEVERITY_ORDER.get(a["severity"], 99), a["detected_at"]))
    for alert in alerts:
        for field in RUN_SPECIFIC_ALERT_FIELDS:
            alert.pop(field, None)
    # JSON round-trip so numpy scalars and NaN compare by value.
    return json.loads(json.dumps(alerts, sort_keys=True, default=str))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--skip-extract", action="store_true",
                        help="compare the CSVs already in data/raw/ and data/raw_dbt/")
    args = parser.parse_args(argv)

    if not args.skip_extract:
        print("Extracting: source=sql -> data/raw/")
        extract_all(source="sql", out_dir=SQL_DIR)
        print("Extracting: source=dbt -> data/raw_dbt/")
        extract_all(source="dbt", out_dir=DBT_DIR)

    print("\nRaw extracts")
    results = [compare_file(name) for name in KEYS]
    print(f"  {'file':<32}{'rows sql':>10}{'rows dbt':>10}{'mismatching rows':>18}")
    for r in results:
        print(f"  {r['file']:<32}{r['rows_sql']:>10}{r['rows_dbt']:>10}{r['mismatching_rows']:>18}")
        for p in r["problems"]:
            print(f"    ! {p}")
        if r["mismatching_rows"]:
            print(f"    only in sql: {r['only_sql']}, only in dbt: {r['only_dbt']}; first rows:")
            print(r["examples"].to_string(index=False))

    print("\nAlerts (process + detect on each side)")
    alerts_sql, alerts_dbt = alerts_from(SQL_DIR), alerts_from(DBT_DIR)
    alerts_equal = alerts_sql == alerts_dbt
    print(f"  sql: {len(alerts_sql)} alerts, dbt: {len(alerts_dbt)} alerts, identical: {alerts_equal}")
    print(f"  ignored fields: {', '.join(RUN_SPECIFIC_ALERT_FIELDS)} (uuid4 per run)")
    if not alerts_equal:
        diff = [i for i, (a, b) in enumerate(zip(alerts_sql, alerts_dbt)) if a != b]
        print(f"  first differing positions: {diff[:5]}")

    ok = alerts_equal and all(r["mismatching_rows"] == 0 and not r["problems"] for r in results)
    print(f"\nPARITY: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
