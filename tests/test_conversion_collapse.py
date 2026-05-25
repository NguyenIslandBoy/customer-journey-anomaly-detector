import pandas as pd
import pytest
from src.detect.conversion_collapse import detect_conversion_collapses, _build_alert


def _base_cvr_series(cvr: float = 0.05, sessions: int = 200, days: int = 40) -> pd.DataFrame:
    """Generate a stable conversion rate series for one source/medium."""
    dates = pd.date_range("2021-01-01", periods=days, freq="D")
    purchasers = [int(sessions * cvr)] * days
    return pd.DataFrame({
        "event_date":      dates,
        "source":          "google",
        "medium":          "organic",
        "sessions":        sessions,
        "purchasers":      purchasers,
        "conversion_rate": cvr,
    })


def test_no_alerts_on_stable_series():
    """Stable CVR series should produce zero alerts."""
    df = _base_cvr_series(cvr=0.05, days=60)
    alerts = detect_conversion_collapses(df)
    assert len(alerts) == 0


def test_detects_known_collapse():
    """A CVR dropping to near zero on day 25 should be flagged."""
    df = _base_cvr_series(cvr=0.05, sessions=200, days=40)
    df.loc[df.index == 24, "conversion_rate"] = 0.001
    alerts = detect_conversion_collapses(df)
    assert len(alerts) >= 1
    flagged_dates = [a["detected_at"] for a in alerts]
    assert "2021-01-25" in flagged_dates    


def test_low_session_day_not_flagged():
    """Collapse on a day with fewer than MIN_SESSIONS should not be flagged."""
    df = _base_cvr_series(cvr=0.05, sessions=200, days=40)
    df.loc[df.index == 24, "conversion_rate"] = 0.001
    df.loc[df.index == 24, "sessions"] = 10  # below threshold
    alerts = detect_conversion_collapses(df)
    flagged_dates = [a["detected_at"] for a in alerts]
    assert "2021-01-25" not in flagged_dates


def test_near_zero_baseline_cvr_skipped():
    """Sources with near-zero baseline CVR should be skipped entirely."""
    df = _base_cvr_series(cvr=0.0001, sessions=200, days=40)
    alerts = detect_conversion_collapses(df)
    assert len(alerts) == 0


def test_severity_high():
    """A drop >= 60% should return severity=high."""
    row = pd.Series({
        "event_date":       pd.Timestamp("2021-01-25"),
        "conversion_rate":  0.01,
        "rolling_mean_cvr": 0.05,
        "relative_drop":    0.80,
        "sessions":         200,
    })
    alert = _build_alert(row, source="google", medium="organic")
    assert alert["severity"] == "high"  
    assert alert["relative_drop_pct"] == 80.0


def test_severity_medium():
    """A drop between 60% and 75% should return severity=medium."""
    row = pd.Series({
        "event_date":       pd.Timestamp("2021-01-25"),
        "conversion_rate":  0.02,
        "rolling_mean_cvr": 0.05,
        "relative_drop":    0.60,
        "sessions":         200,
    })
    alert = _build_alert(row, source="google", medium="organic")
    assert alert["severity"] == "medium"


def test_alert_schema():
    """Every alert must contain all required keys with correct types."""
    df = _base_cvr_series(cvr=0.05, sessions=200, days=40)
    df.loc[df.index == 24, "conversion_rate"] = 0.001
    alerts = detect_conversion_collapses(df)
    assert len(alerts) >= 1

    required_keys = {
        "anomaly_type", "detected_at", "source", "medium",
        "metric_value", "baseline_value", "relative_drop_pct",
        "severity", "recommended_action",
    }
    for alert in alerts:
        assert required_keys.issubset(alert.keys())
        assert alert["anomaly_type"] == "conversion_collapse"
        assert alert["severity"] in ("high", "medium")
        assert isinstance(alert["relative_drop_pct"], float)


def test_no_alerts_before_window_complete():
    """No alerts should fire before the 14-day rolling window is complete."""
    df = _base_cvr_series(cvr=0.05, sessions=200, days=20)
    df.loc[df.index == 9, "conversion_rate"] = 0.001  # day 10, inside window
    alerts = detect_conversion_collapses(df)
    flagged_dates = [a["detected_at"] for a in alerts]
    assert "2021-01-10" not in flagged_dates