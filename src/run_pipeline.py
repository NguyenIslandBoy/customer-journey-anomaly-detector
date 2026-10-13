import argparse
import time
from src.extract import SOURCES, extract_all
from src.process import process_all
from src.alert import build_alerts


def run_pipeline(skip_extract: bool = False, source: str = "sql") -> None:
    """
    Orchestrate the full pipeline:
        extract → process → detect → alert

    Args:
        skip_extract: if True, skip BigQuery extraction and use
                      existing data/raw/ files. Useful for development
                      when you don't want to re-query BigQuery on every run.
        source:       where extraction reads from. "sql" runs the legacy
                      queries in sql/. "dbt" reads the dbt marts, which
                      must already be built (dbt build).
    """
    if source not in SOURCES:
        raise ValueError(f"Unknown source {source!r}; expected one of {SOURCES}")

    start = time.time()
    print("=" * 55)
    print("  CUSTOMER JOURNEY ANOMALY DETECTOR — PIPELINE START")
    print("=" * 55)

    if skip_extract:
        print("\n[1/3] Extraction skipped (using existing raw data)")
    else:
        print(f"\n[1/3] Extracting data from BigQuery (source: {source})...")
        extract_all(source=source)

    print("\n[2/3] Processing raw data...")
    process_all()

    print("\n[3/3] Running anomaly detectors...")
    alerts = build_alerts()

    elapsed = round(time.time() - start, 1)
    high   = sum(1 for a in alerts if a["severity"] == "high")
    medium = sum(1 for a in alerts if a["severity"] == "medium")

    print("\n" + "=" * 55)
    print("  PIPELINE COMPLETE")
    print(f"  Total alerts : {len(alerts)}")
    print(f"  High         : {high}")
    print(f"  Medium       : {medium}")
    print(f"  Elapsed      : {elapsed}s")
    print("=" * 55)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m src.run_pipeline",
        description="Extract, process, detect and alert.",
    )
    parser.add_argument(
        "--skip-extract",
        action="store_true",
        help="reuse existing data/raw/ files instead of querying BigQuery",
    )
    parser.add_argument(
        "--source",
        choices=SOURCES,
        default="sql",
        help="extraction source (default: sql)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    run_pipeline(skip_extract=args.skip_extract, source=args.source)


if __name__ == "__main__":
    main()