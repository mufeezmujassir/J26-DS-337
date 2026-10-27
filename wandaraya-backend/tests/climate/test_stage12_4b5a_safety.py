import subprocess
import sys


def test_production_apply_is_disabled_even_with_confirmation():
    result = subprocess.run(
        [sys.executable, '-m', 'scripts.ingest_stage12_4b5_historical',
         '--manifest', 'missing.json', '--dataset-version',
         'nasa_power_daily_v2.10.0_historical_2010_2025_batch01',
         '--apply', '--confirm-apply'], capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert 'Historical writes disabled' in result.stderr


def test_confirmation_alone_fails_closed():
    result = subprocess.run(
        [sys.executable, '-m', 'scripts.ingest_stage12_4b5_historical',
         '--manifest', 'missing.json', '--dataset-version',
         'nasa_power_daily_v2.10.0_historical_2010_2025_batch01',
         '--confirm-apply'], capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert '--confirm-apply is invalid' in result.stderr
