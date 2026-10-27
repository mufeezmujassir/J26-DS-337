"""Isolated-test orchestration for verified historical samples.

This module is NOT a production execution entry point. The transaction
primitive enforces its own isolated PostgreSQL target restriction. A future
production path must verify authorization, server identity and backup evidence
before allowing any writes; passing booleans to this module is not approval.
"""
from datetime import date, datetime, timezone
from sqlalchemy import select, text
from app.climate.historical_executor import HISTORICAL_VERSIONS, canonical_records, checkpoints, import_sample
from app.models.climate import ClimateDatasetVersion, ClimateGridCell, ClimateDailyObservation

EXPECTED_DAYS = {date.fromordinal(n) for n in range(date(2010, 1, 1).toordinal(), date(2025, 12, 31).toordinal() + 1)}
EXPECTED_COUNTS = {'batch01': 3, 'batch02': 25}
VERSION_BY_BATCH = {version.rsplit('_', 1)[-1]: version for version in HISTORICAL_VERSIONS}


def validate_batch(batch, verified):
    if batch not in EXPECTED_COUNTS:
        raise ValueError('unknown batch')
    selected = [item for item in verified if item[0].get('batch') == batch]
    if len(selected) != EXPECTED_COUNTS[batch] or len({item[0]['sample_id'] for item in selected}) != len(selected):
        raise ValueError('unexpected batch sample identities or count')
    for sample, records, location, metadata in selected:
        if {day for day, _, _ in canonical_records(records)} != EXPECTED_DAYS:
            raise ValueError('unexpected sample date scope')
        digest = sample.get('original_acquisition_sha256', '')
        if len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
            raise ValueError('invalid source checksum')
        if not (-90 <= location['latitude'] <= 90 and -180 <= location['longitude'] <= 180):
            raise ValueError('invalid coordinates')
    return selected


def validate_reconciliation(selected, ids, checkpoint_rows, grid_rows, observation_counts):
    """Require exact sample, checkpoint and grid coverage, not just totals."""
    expected = {item[0]['sample_id']: item[0]['original_acquisition_sha256'] for item in selected}
    actual_grids = {row['source_grid_identifier']: row['id'] for row in grid_rows}
    if len(actual_grids) != len(grid_rows) or actual_grids != ids or set(actual_grids) != set(expected):
        raise ValueError('batch reconciliation failed: grid/sample coverage mismatch')
    actual_checkpoints = {row['sample_id']: row for row in checkpoint_rows}
    if len(actual_checkpoints) != len(checkpoint_rows) or set(actual_checkpoints) != set(expected):
        raise ValueError('batch reconciliation failed: checkpoint sample coverage mismatch')
    if set(observation_counts) != set(ids.values()):
        raise ValueError('batch reconciliation failed: observation grid coverage mismatch')
    for sample_id, digest in expected.items():
        checkpoint = actual_checkpoints[sample_id]
        if (checkpoint['grid_cell_id'] != ids[sample_id] or checkpoint['source_sha256'] != digest
                or checkpoint['record_count'] != len(EXPECTED_DAYS)
                or observation_counts[ids[sample_id]] != len(EXPECTED_DAYS)):
            raise ValueError('batch reconciliation failed: checkpoint, source or observation count mismatch')


def import_isolated_batch(engine, batch, verified, *, target_identity=None, batch_size=500):
    """Provision batch-specific grid records, execute and reconcile in test DB.

    The caller MUST verify each raw file and acquisition evidence before entry;
    this function never interprets a manifest checksum as proof of source data.
    """
    selected = validate_batch(batch, verified)
    if engine.dialect.name != 'postgresql' or (target_identity is None and (engine.url.username != 'climate_executor_test' or engine.url.host not in {'127.0.0.1', '::1', 'localhost'} or engine.url.database not in {'climate_orchestrator_isolated_test', 'climate_cli_orchestrator_isolated_test', 'climate_cli_reconcile_isolated_test'})):
        raise ValueError('target is not the dedicated isolated orchestrator database')
    versions = ClimateDatasetVersion.__table__
    grids = ClimateGridCell.__table__
    obs = ClimateDailyObservation.__table__
    version = VERSION_BY_BATCH[batch]
    with engine.begin() as conn:
        if target_identity is not None:
            from app.climate.production_guard import verify_connection_identity
            verify_connection_identity(conn, target_identity)
        else:
            actual = conn.execute(text('SELECT current_database(), current_user')).one()
            if actual != (engine.url.database, 'climate_executor_test'):
                raise ValueError('connected database identity mismatch')
        if conn.execute(text('SELECT version_num FROM alembic_version')).scalar_one() != 'f78a9b0c1d2e':
            raise ValueError('unexpected schema revision')
        vid = conn.execute(select(versions.c.id).where(versions.c.product_version == version)).scalar_one_or_none()
        if vid is None:
            vid = conn.execute(versions.insert().returning(versions.c.id), dict(source_name='NASA POWER', provider_name='NASA', product_name='POWER Daily', product_version=version, source_url='https://power.larc.nasa.gov/', license_review_status='not_reviewed', retrieved_at=datetime.now(timezone.utc), source_units_json={}, normalized_units_json={})).scalar_one()
        ids = {}
        for sample, records, location, _ in selected:
            grid = conn.execute(select(grids.c.id, grids.c.latitude, grids.c.longitude, grids.c.metadata_json).where(grids.c.dataset_version_id == vid, grids.c.source_grid_identifier == sample['sample_id'])).mappings().one_or_none()
            if grid is None:
                ids[sample['sample_id']] = conn.execute(grids.insert().returning(grids.c.id), dict(dataset_version_id=vid, source_grid_identifier=sample['sample_id'], latitude=location['latitude'], longitude=location['longitude'], geometry=f"SRID=4326;POINT({location['longitude']} {location['latitude']})", spatial_resolution='representative_only', metadata_json={'source_sha256': sample['original_acquisition_sha256']})).scalar_one()
            else:
                if grid['latitude'] != location['latitude'] or grid['longitude'] != location['longitude'] or grid['metadata_json'].get('source_sha256') != sample['original_acquisition_sha256']:
                    raise ValueError('existing grid conflicts with verified sample')
                ids[sample['sample_id']] = grid['id']
    results = []
    for sample, records, _, _ in selected:
        results.append(import_sample(engine, dataset_version_id=vid, grid_cell_id=ids[sample['sample_id']], sample_id=sample['sample_id'], source_sha256=sample['original_acquisition_sha256'], records=records, expected_dates=EXPECTED_DAYS, target_identity=target_identity, batch_size=batch_size))
    with engine.connect() as conn:
        actual_count = conn.execute(select(text('count(*)')).select_from(obs).where(obs.c.dataset_version_id == vid)).scalar_one()
        committed = conn.execute(select(text('count(*)')).select_from(checkpoints).where(checkpoints.c.dataset_version_id == vid)).scalar_one()
        checkpoint_rows = conn.execute(select(checkpoints).where(checkpoints.c.dataset_version_id == vid)).mappings().all()
        grid_rows = conn.execute(select(grids.c.id, grids.c.source_grid_identifier).where(grids.c.dataset_version_id == vid)).mappings().all()
        observation_counts = dict(conn.execute(select(obs.c.grid_cell_id, text('count(*)')).where(obs.c.dataset_version_id == vid).group_by(obs.c.grid_cell_id)).all())
    expected = len(selected) * len(EXPECTED_DAYS)
    if actual_count != expected or committed != len(selected):
        raise ValueError('batch reconciliation failed')
    validate_reconciliation(selected, ids, checkpoint_rows, grid_rows, observation_counts)
    return {'batch': batch, 'version': version, 'expected': expected, 'observations': actual_count, 'checkpoints': committed, 'inserted': sum(r['inserted'] for r in results), 'unchanged': sum(r['unchanged'] for r in results)}
