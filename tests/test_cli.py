from unittest.mock import patch

import pytest

from src import run_pipeline as rp


@pytest.fixture
def mocked_stages():
    """Replace every pipeline stage so no test touches BigQuery or disk."""
    with patch.object(rp, "extract_all") as extract, \
         patch.object(rp, "process_all") as process, \
         patch.object(rp, "build_alerts", return_value=[]) as alerts:
        yield extract, process, alerts


def test_default_cli_run_extracts(mocked_stages):
    """A bare `python -m src.run_pipeline` must extract, not reuse raw files."""
    extract, process, alerts = mocked_stages
    rp.main([])
    extract.assert_called_once()
    process.assert_called_once()
    alerts.assert_called_once()


def test_skip_extract_flag_skips_extraction(mocked_stages):
    extract, process, alerts = mocked_stages
    rp.main(["--skip-extract"])
    extract.assert_not_called()
    process.assert_called_once()
    alerts.assert_called_once()


def test_source_defaults_to_sql(mocked_stages):
    args = rp.parse_args([])
    assert args.source == "sql"
    assert args.skip_extract is False


def test_unknown_source_rejected(mocked_stages):
    with pytest.raises(SystemExit):
        rp.parse_args(["--source", "csv"])


def test_dbt_source_not_implemented_yet(mocked_stages):
    extract, process, alerts = mocked_stages
    with pytest.raises(NotImplementedError):
        rp.main(["--source", "dbt"])
    extract.assert_not_called()
    process.assert_not_called()


def test_run_pipeline_signature_still_works(mocked_stages):
    """Existing callers use run_pipeline(skip_extract=...) by keyword."""
    extract, process, alerts = mocked_stages
    rp.run_pipeline(skip_extract=False)
    extract.assert_called_once()
    rp.run_pipeline(skip_extract=True)
    extract.assert_called_once()
    assert process.call_count == 2
