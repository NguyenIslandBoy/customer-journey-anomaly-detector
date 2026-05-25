# Customer Journey Anomaly Detector

A production-grade anomaly detection pipeline for GA4 marketing data,
built on the Google Merchandise Store public BigQuery dataset.

Monitors three operational signals that matter to any marketing or
analytics team:

| Anomaly Type | Signal | Method |
|---|---|---|
| Traffic Spike | Abnormal session volume by source/medium | Rolling Z-score (14-day, 3σ) |
| Conversion Collapse | CVR drop vs rolling baseline | Relative drop threshold (60%, min 1pp absolute) |
| Untagged Surge | Direct/(none) traffic share spike | Rolling Z-score (21-day, 2.5σ) |

## Architecture

```
BigQuery (GA4 public dataset)
    ↓
src/extract.py        ← SQL queries, saves to data/raw/
    ↓
src/process.py        ← cleaning, filtering, aggregation
    ↓
src/detect/           ← one module per anomaly type
    ↓
src/alert.py          ← merges alerts, assigns IDs and severity
    ↓
output/alerts.json    ← consumed by dashboard
    ↓
dashboard/app.py      ← Streamlit (reads only, no pipeline logic)
```

## Project Structure

```
customer-journey-anomaly-detector/
├── sql/                          # BigQuery SQL queries
├── src/
│   ├── extract.py                # BigQuery extraction
│   ├── process.py                # Data cleaning and aggregation
│   ├── detect/
│   │   ├── traffic_spike.py
│   │   ├── conversion_collapse.py
│   │   └── untagged_surge.py
│   ├── alert.py                  # Alert merging and output
│   └── run_pipeline.py           # Pipeline orchestrator
├── dashboard/
│   └── app.py                    # Streamlit dashboard
├── tests/                        # Pytest suite (22 tests)
├── output/                       # alerts.json written here
└── data/
    ├── raw/                      # BigQuery exports
    └── processed/                # Cleaned aggregations
```

## Setup

### Prerequisites
- Python 3.10+
- Google Cloud project with BigQuery API enabled
- Service account with `BigQuery Data Viewer` and `BigQuery Job User` roles

### Installation

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Configuration

```bash
cp .env.example .env
# Edit .env with your GCP project ID and credentials path
```

### Run Pipeline

```bash
# Full run (extracts from BigQuery + processes + detects)
python -m src.run_pipeline

# Skip extraction (use existing data/raw/ files)
python -m src.run_pipeline  # edit skip_extract=True in run_pipeline.py
```

### Run Dashboard

```bash
streamlit run dashboard/app.py
```

### Run Tests

```bash
pytest tests/ -v
```

## Detection Logic

### Traffic Spike
Computes a 14-day rolling mean and standard deviation of daily sessions per source/medium. Flags days where the Z-score exceeds 3.0. A minimum rolling std of 1.0 prevents false positives on near-flat series.

### Conversion Collapse
Computes a 14-day rolling mean CVR per source/medium. Flags days where the relative drop from baseline exceeds 60% AND the absolute drop exceeds 1 percentage point. Minimum 30 sessions required on the flagged day to exclude noise from low-traffic sources.

### Untagged Surge
Computes the daily share of `(direct)/(none)` traffic site-wide. Applies a 21-day rolling Z-score with a lower threshold of 2.5σ - tracking failures are operationally urgent, so sensitivity is deliberately higher.

## Key Design Decisions

**Why relative drop for CVR, not Z-score?**
Conversion rates are proportions bounded between 0 and 1, often right-skewed with small absolute values. A 40% relative drop has a clear business meaning; a Z-score on a proportion series is noisier and harder to explain to stakeholders.

**Why different rolling windows (14 vs 21 days)?**
Session volume changes day-to-day. Direct traffic share is a slower-moving structural metric - a longer window gives a more stable baseline and avoids flagging normal weekly seasonality.

**Why does the pipeline separate extract → process → detect → alert?**
Each layer is independently testable and replaceable. The Streamlit dashboard reads output files only - it never imports detection logic. This mirrors production ML system design where serving and training are decoupled.

## Limitations and Honest Notes

- The GMS dataset covers Nov 2020 – Jan 2021 (92 days). A longer
  history would improve rolling baselines for the first 2–3 weeks.
- Zero traffic spike and untagged surge alerts on this dataset reflect
  genuine stability in the public data, not detector failure. The test
  suite validates detector logic independently of the real data.
- `(data deleted)` is a GA4 obfuscation label in the public dataset,
  not a tracking error. In a production environment this would be a
  real source/medium value.

## Tests

22 tests across three test files. Each detector is tested with:
- Stable series producing zero alerts
- Known anomaly injected at a specific date
- Low-volume filter behaviour
- Alert schema validation
- Severity threshold boundaries tested directly on `_build_alert`

```bash
pytest tests/ -v
```