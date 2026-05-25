import json
import uuid
from pathlib import Path

from src.detect.traffic_spike import detect_traffic_spikes
from src.detect.conversion_collapse import detect_conversion_collapses
from src.detect.untagged_surge import detect_untagged_surges

OUTPUT_DIR = Path(__file__).parent.parent / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

SEVERITY_ORDER = {"high": 0, "medium": 1}


def build_alerts() -> list[dict]:
    """
    Run all detectors, merge results, assign IDs, sort by severity then date.

    Returns:
        List of alert dicts written to output/alerts.json.
    """
    print("  Running detector: traffic_spike")
    traffic_alerts = detect_traffic_spikes()
    print(f"    → {len(traffic_alerts)} alerts")

    print("  Running detector: conversion_collapse")
    cvr_alerts = detect_conversion_collapses()
    print(f"    → {len(cvr_alerts)} alerts")

    print("  Running detector: untagged_surge")
    surge_alerts = detect_untagged_surges()
    print(f"    → {len(surge_alerts)} alerts")

    all_alerts = traffic_alerts + cvr_alerts + surge_alerts

    # Assign unique ID to each alert
    for alert in all_alerts:
        alert["alert_id"] = str(uuid.uuid4())

    # Sort: severity first (high before medium), then date ascending
    all_alerts.sort(key=lambda a: (
        SEVERITY_ORDER.get(a["severity"], 99),
        a["detected_at"]
    ))

    output_path = OUTPUT_DIR / "alerts.json"
    with open(output_path, "w") as f:
        json.dump(all_alerts, f, indent=2)

    print(f"\n  Total alerts: {len(all_alerts)}")
    print(f"  Written to:   {output_path}")

    return all_alerts


if __name__ == "__main__":
    build_alerts()