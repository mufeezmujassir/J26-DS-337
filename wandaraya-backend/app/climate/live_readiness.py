"""Read-only checks used before a historical import can be considered.

Passing these checks does not authorize an import. In particular the backup
restore attestation and an independently issued approval must be validated.
"""
import hashlib
from sqlalchemy import text

from scripts.stage12_4b7_readonly_audit import PILOT, TABLES

CONSTRAINTS = {
    'uq_climate_daily_observation': 'UNIQUE (dataset_version_id, grid_cell_id, observation_date)',
    'uq_climate_checkpoint_sample': 'UNIQUE (dataset_version_id, sample_id)',
    'climate_historical_import_checkpoints_pkey': 'PRIMARY KEY (dataset_version_id, grid_cell_id)',
    'uq_climate_grid_cell_version_source': 'UNIQUE (dataset_version_id, source_grid_identifier)',
    'uq_climate_dataset_source_version': 'UNIQUE (provider_name, product_name, product_version)',
    'climate_grid_cells_dataset_version_id_fkey': 'FOREIGN KEY (dataset_version_id) REFERENCES climate_dataset_versions(id)',
    'climate_daily_observations_dataset_version_id_fkey': 'FOREIGN KEY (dataset_version_id) REFERENCES climate_dataset_versions(id)',
    'climate_daily_observations_grid_cell_id_fkey': 'FOREIGN KEY (grid_cell_id) REFERENCES climate_grid_cells(id)',
    'climate_historical_import_checkpoints_dataset_version_id_fkey': 'FOREIGN KEY (dataset_version_id) REFERENCES climate_dataset_versions(id)',
    'climate_historical_import_checkpoints_grid_cell_id_fkey': 'FOREIGN KEY (grid_cell_id) REFERENCES climate_grid_cells(id)',
}


def check_constraint_definitions(actual):
    for name, definition in CONSTRAINTS.items():
        if actual.get(name) != definition:
            raise ValueError('missing or different schema constraint: ' + name)


def inspect_read_only(conn, baseline):
    """Compare live protected content, exact constraints and named-collation references."""
    constraints = dict(conn.execute(text("""SELECT conname, pg_get_constraintdef(oid)
        FROM pg_constraint WHERE convalidated AND conrelid IN
        ('public.climate_daily_observations'::regclass, 'public.climate_historical_import_checkpoints'::regclass,
         'public.climate_grid_cells'::regclass, 'public.climate_dataset_versions'::regclass)""")).all())
    check_constraint_definitions(constraints)
    if baseline.get('format') != 'postgresql-17-jsonb-text-utc-sorted-C-v1' or set(baseline.get('tables', {})) != set(TABLES):
        raise ValueError('invalid protected-content baseline')
    conn.execute(text("SET LOCAL TIME ZONE 'UTC'"))
    actual = {}
    for name, query in TABLES.items():
        rows = conn.execute(text('SELECT to_jsonb(r)::text FROM (' + query + ') r ORDER BY to_jsonb(r)::text COLLATE "C"'), {'pilot': PILOT}).scalars()
        digest = hashlib.sha256()
        count = 0
        for row in rows:
            encoded = row.encode('utf-8')
            digest.update(len(encoded).to_bytes(8, 'big'))
            digest.update(encoded)
            count += 1
        actual[name] = {'rows': count, 'sha256': digest.hexdigest()}
    if actual != baseline['tables']:
        changed = sorted(name for name in actual if actual[name] != baseline['tables'].get(name))
        raise ValueError('protected-content baseline mismatch: ' + ', '.join(changed))
    # Fail closed for named collation dependencies on any user index/column.
    affected = conn.execute(text("""SELECT count(*) FROM (
        SELECT c.oid FROM pg_index i JOIN pg_class t ON t.oid=i.indrelid
        JOIN pg_namespace n ON n.oid=t.relnamespace
        JOIN LATERAL unnest(i.indcollation) k(oid) ON k.oid<>0
        JOIN pg_collation c ON c.oid=k.oid
        WHERE n.nspname NOT IN ('pg_catalog','information_schema') AND n.nspname NOT LIKE 'pg_toast%'
          AND c.collversion IS NOT NULL AND c.collversion IS DISTINCT FROM pg_collation_actual_version(c.oid)
        UNION ALL
        SELECT c.oid FROM pg_attribute a JOIN pg_class t ON t.oid=a.attrelid
        JOIN pg_namespace n ON n.oid=t.relnamespace JOIN pg_collation c ON c.oid=a.attcollation
        WHERE a.attnum>0 AND NOT a.attisdropped AND n.nspname NOT IN ('pg_catalog','information_schema')
          AND n.nspname NOT LIKE 'pg_toast%' AND c.collversion IS NOT NULL
          AND c.collversion IS DISTINCT FROM pg_collation_actual_version(c.oid)
    ) affected""")).scalar_one()
    if affected:
        raise ValueError(f'named collation mismatch affects {affected} user index or column references')
    return {'protected_tables': actual, 'named_collation_references': affected}
