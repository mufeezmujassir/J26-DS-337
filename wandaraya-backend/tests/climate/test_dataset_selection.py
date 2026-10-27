import pytest
from app.climate.dataset_selection import PILOT, HISTORICAL_BATCH01, select_one_version


def test_pilot_and_historical_overlap_does_not_double_count():
    rows = [
        {'dataset_version': PILOT, 'sample_id': 'sample-1', 'observation_date': '2024-01-01'},
        {'dataset_version': HISTORICAL_BATCH01, 'sample_id': 'sample-1', 'observation_date': '2024-01-01'},
    ]
    assert select_one_version(rows, dataset_version=HISTORICAL_BATCH01) == [rows[1]]
    assert select_one_version(rows, dataset_version=PILOT) == [rows[0]]


def test_duplicate_sample_day_in_same_version_is_rejected():
    row = {'dataset_version': PILOT, 'sample_id': 'sample-1', 'observation_date': '2024-01-01'}
    with pytest.raises(ValueError, match='duplicate'):
        select_one_version([row, row], dataset_version=PILOT)


def test_sample_identity_is_required():
    with pytest.raises(ValueError, match='sample_id'):
        select_one_version([{'dataset_version': PILOT, 'observation_date': '2024-01-01'}], dataset_version=PILOT)


def test_unknown_dataset_is_rejected():
    with pytest.raises(ValueError, match='unknown'):
        select_one_version([], dataset_version='unknown')
