import time
from src.extract import extract_all
from src.process import process_all
from src.alert import build_alerts


def run_pipeline(skip_extract: bool = False) -> None:
    """
    Orchestrate the full pipeline:
        extract → process → detect → alert

    Args:
        skip_extract: if True, skip BigQuery extraction and use
                      existing data/raw/ files. Useful for development
                      when you don't want to re-query BigQuery on every run.
    """
    start = time.time()
    print("=" * 55)
    print("  CUSTOMER JOURNEY ANOMALY DETECTOR — PIPELINE START")
    print("=" * 55)

    if skip_extract:
        print("\n[1/3] Extraction skipped (using existing raw data)")
    else:
        print("\n[1/3] Extracting data from BigQuery...")
        extract_all()

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


if __name__ == "__main__":
    # Pass skip_extract=True during development to avoid re-querying BigQuery
    run_pipeline(skip_extract=True)