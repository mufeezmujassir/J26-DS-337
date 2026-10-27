"""Compare one known isolated restore with production using read-only queries."""
import hashlib
import json
import subprocess
from pathlib import Path

TARGETS = [('wandaraya-postgres', 'postgres', 'wandaraya'),
           ('wandaraya-globals-restore-test', 'restore_test_admin', 'climate_4b9_backup_restore')]
QUERIES = {
    'pilot_observations': "SELECT o.* FROM climate_daily_observations o JOIN climate_dataset_versions v ON v.id=o.dataset_version_id WHERE v.product_version='nasa_power_daily_v2.10.0_2024_pilot'",
    'pilot_dataset': "SELECT * FROM climate_dataset_versions WHERE product_version='nasa_power_daily_v2.10.0_2024_pilot'",
    'pilot_grid_cells': "SELECT g.* FROM climate_grid_cells g JOIN climate_dataset_versions v ON v.id=g.dataset_version_id WHERE v.product_version='nasa_power_daily_v2.10.0_2024_pilot'",
    'climate_attraction_mappings': 'SELECT * FROM climate_attraction_mappings',
    'weather_readings': 'SELECT * FROM weather_readings',
    'district_weather_monthly': 'SELECT * FROM district_weather_monthly',
    'weather_forecasts': 'SELECT * FROM weather_forecasts',
    'checkpoints': 'SELECT * FROM climate_historical_import_checkpoints',
    'active_attractions': 'SELECT * FROM attractions WHERE is_active IS TRUE',
    'alembic_revision': 'SELECT * FROM alembic_version',
    'application_constraints': "SELECT n.nspname, t.relname, c.conname, c.contype, c.convalidated, pg_get_constraintdef(c.oid) AS definition FROM pg_constraint c JOIN pg_class t ON t.oid=c.conrelid JOIN pg_namespace n ON n.oid=t.relnamespace WHERE n.nspname='public'",
}


def docker(*args):
    return subprocess.run(['docker', *args], check=True, capture_output=True).stdout


def main():
    info = json.loads(docker('inspect', 'wandaraya-globals-restore-test'))[0]
    if info['HostConfig']['NetworkMode'] != 'none' or not info['Mounts'] or any(m.get('Type') != 'volume' for m in info['Mounts']):
        raise RuntimeError('restore environment is not network-isolated with separate volume storage')
    result = {}
    for label, query in QUERIES.items():
        sql = "SELECT to_jsonb(r)::text FROM (" + query + ") r ORDER BY to_jsonb(r)::text COLLATE \"C\""
        hashes = []
        counts = []
        for container, user, database in TARGETS:
            raw = docker('exec', '-e', 'PGOPTIONS=-c default_transaction_read_only=on -c timezone=UTC', container,
                         'psql', '-X', '-v', 'ON_ERROR_STOP=1', '-U', user, '-d', database, '-At', '-c', sql)
            hashes.append(hashlib.sha256(raw).hexdigest())
            counts.append(len(raw.splitlines()))
        result[label] = {'production_count': counts[0], 'restore_count': counts[1], 'production_sha256': hashes[0], 'restore_sha256': hashes[1], 'match': hashes[0] == hashes[1] and counts[0] == counts[1]}
    report = {'restore_target': TARGETS[1][2], 'container': TARGETS[1][0], 'matching': all(v['match'] for v in result.values()),
              'tables': result, 'method': 'sha256 of newline-delimited PostgreSQL 17 jsonb text sorted C, UTC',
              'limitations': ['point-in-time data may change between production reads', 'roles and ownership/ACL equivalence not validated', 'no production restore performed']}
    Path('data/reports/stage12_4b9_restore_content_comparison.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))
    if not report['matching']:
        raise SystemExit('content mismatch; backup not verified as current')


if __name__ == '__main__':
    main()
