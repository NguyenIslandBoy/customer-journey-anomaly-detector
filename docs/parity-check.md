# Parity check: legacy SQL vs dbt marts

**Run date:** 2026-10-13, after renaming the pipeline's `sessions` columns to
`users` (Task 8). The same check also passed earlier that day under the old
names, with the same row counts and alerts.
**Outcome:** PASS. Zero mismatching rows in all three extracts; identical alert lists.

## What was compared

`scripts/parity_check.py` extracts the same three CSVs twice:

- `--source sql`: the legacy queries in `sql/`, written to `data/raw/`
- `--source dbt`: the marts `mart_channel_performance_daily` and
  `mart_tracking_quality_daily` in dataset `cja_dbt`, mapped to the sql mode's
  columns (only `user_conversion_rate` is renamed, to `conversion_rate`),
  written to `data/raw_dbt/`

It then compares each pair exactly: same columns, order and dtypes, rows sorted by
key, every value equal (two nulls count as equal). Floats are read with
`float_precision="round_trip"`. pandas' default parser can be off by 1e-16 on some
values, which would report identical values as different. Finally it runs
`src/process.py` and the three detectors on each side and compares the alert lists.

Data: `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`, all 92 days
(2020-11-01 to 2021-01-31). The marts were rebuilt with `dbt build` right before
the run (PASS=17, WARN=0, ERROR=0).

## Result

| File | Rows (sql) | Rows (dbt) | Mismatching rows |
|---|---:|---:|---:|
| `traffic_by_source.csv` | 825 | 825 | 0 |
| `conversion_rate_by_source.csv` | 828 | 828 | 0 |
| `direct_untagged_traffic.csv` | 92 | 92 | 0 |

| Alerts | sql | dbt |
|---|---:|---:|
| Total | 20 | 20 |
| Identical list | yes | yes |

Ignored alert field: `alert_id`. It is a uuid4 assigned per run in `src/alert.py`,
so it differs on every run by design. Nothing else is ignored.

A full `python -m src.run_pipeline --source dbt` run gives the same 20 alerts
(8 high, 12 medium) as the legacy baseline taken before any change in this
branch, ignoring `alert_id`.

## Does the check catch a difference?

Yes. With `purchasers` changed on one row of the dbt
`conversion_rate_by_source.csv` (2020-12-01, google / organic), the script
reported 1 mismatching row and `PARITY: FAIL`. Restoring the file gave
`PARITY: PASS` again.

## Notes

- The 3 extra rows in `conversion_rate_by_source.csv` compared with
  `traffic_by_source.csv` are source/medium/day combinations with events but no
  `session_start`. The legacy conversion query has no `WHERE`, so it emits them
  with `users = 0` and a null `conversion_rate`. The dbt marts keep every
  event so that they reproduce these rows.
- `users`, `total_users` and `direct_users` count distinct users with a
  `session_start`, not sessions. Before the rename they were called
  `sessions`, `total_sessions` and `direct_sessions`. The rename changed no
  value: before and after, the raw and processed CSVs match row for row and
  the alerts are identical (ignoring `alert_id`).

## Re-run

```powershell
.\venv\Scripts\dbt.exe build --project-dir dbt --profiles-dir dbt
.\venv\Scripts\python.exe scripts\parity_check.py                 # extract both modes, compare
.\venv\Scripts\python.exe scripts\parity_check.py --skip-extract  # compare existing files only
```

Exit code 0 means PASS.
