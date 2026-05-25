import pandas as pd
import pytest
from src.detect.untagged_surge import detect_untagged_surges, _build_alert


def _base_series(direct_share: float = 0.25, days: int = 50) -> pd.DataFrame:
    """Generate a stable direct_share series."""
    dates = pd.date_range("2021-01-01", periods=days, freq="D")
    total = 2000
    direct = int(total * direct_share)
    return pd.DataFrame({
        "event_date":      dates,
        "total_sessions":  total,
        "direct_sessions": direct,
        "direct_share":    direct_share,
    })


def test_no_alerts_on_stable_series():
    """Stable direct share should produce zero alerts."""
    df = _base_series(direct_share=0.25, days=60)
    alerts = detect_untagged_surges(df)
    assert len(alerts) == 0


def test_detects_known_surge():
    """A large direct share spike on day 30 should be flagged."""
    import numpy as np
    rng = np.random.default_rng(0)
    dates = pd.date_range("2021-01-01", periods=50, freq="D")
    shares = (rng.normal(loc=0.25, scale=0.01, size=50)).clip(0.1, 0.9).tolist()
    df = pd.DataFrame({
        "event_date":      dates,
        "total_sessions":  2000,
        "direct_sessions": [int(2000 * s) for s in shares],
        "direct_share":    shares,
    })
    df.loc[df.index == 29, "direct_share"] = 0.70  # large surge on day 30
    alerts = detect_untagged_surges(df)
    assert len(alerts) >= 1
    flagged_dates = [a["detected_at"] for a in alerts]
    assert "2021-01-30" in flagged_dates


def test_no_alerts_before_window_complete():
    """No alerts should fire before the 21-day rolling window is populated."""
    df = _base_series(direct_share=0.25, days=30)
    df.loc[df.index == 10, "direct_share"] = 0.90  # day 11, inside window
    alerts = detect_untagged_surges(df)
    flagged_dates = [a["detected_at"] for a in alerts]
    assert "2021-01-11" not in flagged_dates


def test_alert_schema():
    """Every alert must contain all required keys with correct types."""
    import numpy as np
    rng = np.random.default_rng(1)
    dates = pd.date_range("2021-01-01", periods=50, freq="D")
    shares = rng.normal(loc=0.25, scale=0.01, size=50).clip(0.1, 0.9).tolist()
    df = pd.DataFrame({
        "event_date":      dates,
        "total_sessions":  2000,
        "direct_sessions": [int(2000 * s) for s in shares],
        "direct_share":    shares,
    })
    df.loc[df.index == 35, "direct_share"] = 0.80
    alerts = detect_untagged_surges(df)
    assert len(alerts) >= 1

    required_keys = {
        "anomaly_type", "detected_at", "source", "medium",
        "metric_value", "baseline_value", "z_score",
        "severity", "recommended_action",
    }
    for alert in alerts:
        assert required_keys.issubset(alert.keys())
        assert alert["anomaly_type"] == "untagged_surge"
        assert alert["severity"] in ("high", "medium")
        assert isinstance(alert["z_score"], float)
        assert isinstance(alert["metric_value"], float)


def test_severity_high():
    """z_score >= 3.5 should return severity=high."""
    row = pd.Series({
        "event_date":    pd.Timestamp("2021-01-30"),
        "direct_share":  0.70,
        "rolling_mean":  0.25,
        "rolling_std":   0.01,
        "z_score":       4.2,
    })
    alert = _build_alert(row)
    assert alert["severity"] == "high"


def test_severity_medium():
    """2.5 <= z_score < 3.5 should return severity=medium."""
    row = pd.Series({
        "event_date":    pd.Timestamp("2021-01-30"),
        "direct_share":  0.35,
        "rolling_mean":  0.25,
        "rolling_std":   0.01,
        "z_score":       2.8,
    })
    alert = _build_alert(row)
    assert alert["severity"] == "medium"


def test_metric_value_is_percentage():
    """metric_value and baseline_value should be percentages, not proportions."""
    row = pd.Series({
        "event_date":    pd.Timestamp("2021-01-30"),
        "direct_share":  0.60,
        "rolling_mean":  0.25,
        "rolling_std":   0.01,
        "z_score":       3.0,
    })
    alert = _build_alert(row)
    assert alert["metric_value"] == 60.0
    assert alert["baseline_value"] == 25.0