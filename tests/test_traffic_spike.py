import pandas as pd
import pytest
from src.detect.traffic_spike import detect_traffic_spikes


def _base_series(sessions: int = 100, days: int = 30) -> pd.DataFrame:
    """Generate a flat, stable time series for one source/medium."""
    dates = pd.date_range("2021-01-01", periods=days, freq="D")
    return pd.DataFrame({
        "event_date": dates,
        "source":     "google",
        "medium":     "organic",
        "sessions":   sessions,
    })


def test_no_alerts_on_flat_series():
    """Stable flat series should produce zero alerts."""
    df = _base_series(sessions=500, days=60)
    alerts = detect_traffic_spikes(df)
    assert len(alerts) == 0


def test_detects_known_spike():
    """A 5x spike on day 20 should be flagged."""
    df = _base_series(sessions=200, days=40)
    df.loc[df.index == 19, "sessions"] = 1000  # day 20, 5x spike
    alerts = detect_traffic_spikes(df)
    assert len(alerts) >= 1
    flagged_dates = [a["detected_at"] for a in alerts]
    assert "2021-01-20" in flagged_dates


def test_spike_severity_high():
    """Severity=high is assigned when z_score >= 4.0."""
    import pandas as pd
    from src.detect.traffic_spike import _build_alert

    # Build a mock row with a known z-score above 4.0
    row = pd.Series({
        "event_date":    pd.Timestamp("2021-01-26"),
        "sessions":      5000,
        "rolling_mean":  200.0,
        "rolling_std":   50.0,
        "z_score":       4.5,
    })
    alert = _build_alert(row, source="google", medium="organic")
    assert alert["severity"] == "high"
    assert alert["z_score"] == 4.5


def test_spike_severity_medium():
    """Severity=medium is assigned when 3.0 < z_score < 4.0."""
    import pandas as pd
    from src.detect.traffic_spike import _build_alert

    row = pd.Series({
        "event_date":    pd.Timestamp("2021-01-26"),
        "sessions":      800,
        "rolling_mean":  200.0,
        "rolling_std":   50.0,
        "z_score":       3.5,
    })
    alert = _build_alert(row, source="google", medium="organic")
    assert alert["severity"] == "medium"


def test_no_alerts_before_window_complete():
    """No alerts should fire before the 14-day window is populated (days 1-14)."""
    df = _base_series(sessions=100, days=20)
    # Inject spike on day 10 (index 9) — inside the first 14-day window
    # Rolling baseline is not yet complete here, so no alert should fire
    df.loc[df.index == 9, "sessions"] = 5000
    alerts = detect_traffic_spikes(df)
    flagged_dates = [a["detected_at"] for a in alerts]
    # Day 10 = 2021-01-10, must not be flagged
    assert "2021-01-10" not in flagged_dates


def test_alert_schema():
    """Every alert must contain all required keys with correct types."""
    df = _base_series(sessions=200, days=40)
    df.loc[df.index == 19, "sessions"] = 1500
    alerts = detect_traffic_spikes(df)
    assert len(alerts) >= 1

    required_keys = {
        "anomaly_type", "detected_at", "source", "medium",
        "metric_value", "baseline_value", "z_score",
        "severity", "recommended_action",
    }
    for alert in alerts:
        assert required_keys.issubset(alert.keys()), f"Missing keys: {required_keys - alert.keys()}"
        assert alert["anomaly_type"] == "traffic_spike"
        assert alert["severity"] in ("high", "medium")
        assert isinstance(alert["z_score"], float)
        assert isinstance(alert["metric_value"], int)


def test_multiple_sources_detected_independently():
    """Spikes in one source should not affect detection in another."""
    df1 = _base_series(sessions=200, days=40)
    df1.loc[df1.index == 19, "sessions"] = 1500  # spike in google/organic

    df2 = _base_series(sessions=200, days=40)
    df2["source"] = "bing"
    df2["medium"] = "cpc"
    # No spike in bing/cpc

    df = pd.concat([df1, df2], ignore_index=True)
    alerts = detect_traffic_spikes(df)

    sources_flagged = {a["source"] for a in alerts}
    assert "google" in sources_flagged
    assert "bing" not in sources_flagged