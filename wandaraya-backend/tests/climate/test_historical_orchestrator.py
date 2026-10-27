from datetime import date, timedelta
import pytest
from sqlalchemy import create_engine
from app.climate.historical_orchestrator import import_isolated_batch, validate_batch, validate_reconciliation


def sample(n):
    start = date(2010, 1, 1)
    records = [{'date': (start + timedelta(days=i)).isoformat()} for i in range(5844)]
    return ({'batch': 'batch01', 'sample_id': str(n), 'original_acquisition_sha256': 'a' * 64}, records, {'latitude': 6, 'longitude': 80}, {})


def test_invalid_scope_rejected():
    with pytest.raises(ValueError, match='unknown batch'):
        validate_batch('other', [])
    with pytest.raises(ValueError, match='identities or count'):
        validate_batch('batch01', [sample(1)] * 3)


def test_nonisolated_target_rejected_before_connection():
    engine = create_engine('postgresql+psycopg://postgres@127.0.0.1:5432/wandaraya')
    with pytest.raises(ValueError, match='dedicated isolated'):
        import_isolated_batch(engine, 'batch01', [sample(1), sample(2), sample(3)])


def test_reconciliation_checks_exact_samples_grids_and_checkpoints():
    selected = [sample(1), sample(2), sample(3)]
    ids = {str(i): i for i in range(1, 4)}
    grids = [{'id': i, 'source_grid_identifier': str(i)} for i in range(1, 4)]
    checkpoints = [{'sample_id': str(i), 'grid_cell_id': i, 'source_sha256': 'a' * 64,
                    'record_count': 5844} for i in range(1, 4)]
    counts = {i: 5844 for i in range(1, 4)}
    validate_reconciliation(selected, ids, checkpoints, grids, counts)
    corrupted = [dict(row) for row in checkpoints]
    corrupted[0]['grid_cell_id'] = 2
    with pytest.raises(ValueError, match='checkpoint, source or observation'):
        validate_reconciliation(selected, ids, corrupted, grids, counts)
    with pytest.raises(ValueError, match='observation grid coverage'):
        validate_reconciliation(selected, ids, checkpoints, grids, {1: 5844, 2: 5844, 4: 5844})
