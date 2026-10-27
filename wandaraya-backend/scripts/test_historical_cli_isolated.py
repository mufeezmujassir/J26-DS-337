"""Exercise the real CLI only against a freshly created isolated test DB."""
import json
import os
import subprocess
import sys
from pathlib import Path
from sqlalchemy.engine import URL

CONTAINER = 'wandaraya-climate-executor-integration-test'
DATABASE = 'climate_cli_reconcile_isolated_test'
USER = 'climate_executor_test'
MANIFEST = 'data/reports/stage12_4b5_source_provenance.json'
VERSIONS = ['nasa_power_daily_v2.10.0_historical_2010_2025_batch01', 'nasa_power_daily_v2.10.0_historical_2010_2025_batch02']


def docker(*args):
    return subprocess.run(['docker', *args], text=True, capture_output=True, check=True).stdout.strip()


def main():
    info = json.loads(docker('inspect', CONTAINER))[0]
    ports = info['NetworkSettings']['Ports']['5432/tcp']
    env = dict(item.split('=', 1) for item in info['Config']['Env'] if '=' in item)
    if (info['Config']['Image'] != 'postgis/postgis:17-3.5' or len(ports) != 1 or ports[0]['HostIp'] != '127.0.0.1'
            or env.get('POSTGRES_USER') != USER or env.get('POSTGRES_DB') != 'climate_executor_isolated_test'
            or any(m.get('Source', '').lower().endswith('postgres-data') for m in info['Mounts'])):
        raise RuntimeError('isolated container identity verification failed')
    if docker('exec', CONTAINER, 'psql', '-U', USER, '-d', 'postgres', '-tAc', "SELECT 1 FROM pg_database WHERE datname='climate_cli_reconcile_isolated_test'"):
        raise RuntimeError('target already exists; refusing to reuse it')
    docker('exec', CONTAINER, 'createdb', '-U', USER, DATABASE)
    docker('exec', CONTAINER, 'psql', '-v', 'ON_ERROR_STOP=1', '-U', USER, '-d', DATABASE, '-c', 'CREATE EXTENSION postgis')
    url = URL.create('postgresql+psycopg', username=USER, password=env['POSTGRES_PASSWORD'], host='127.0.0.1', port=int(ports[0]['HostPort']), database=DATABASE)
    run_env = os.environ.copy()
    run_env['DATABASE_URL'] = url.render_as_string(hide_password=False)
    migration = subprocess.run([sys.executable, '-m', 'alembic', 'upgrade', 'f78a9b0c1d2e'], capture_output=True, text=True, env=run_env)
    if migration.returncode:
        raise RuntimeError('isolated migration failed: ' + migration.stderr.replace(env['POSTGRES_PASSWORD'], '[redacted]'))
    results = []
    for version in (VERSIONS[0], VERSIONS[1], VERSIONS[0], VERSIONS[1]):
        p = subprocess.run([sys.executable, '-m', 'scripts.ingest_stage12_4b5_historical', '--manifest', MANIFEST,
                            '--dataset-version', version, '--isolated-test'], capture_output=True, text=True, env=run_env)
        if p.returncode:
            raise RuntimeError('isolated CLI failed: ' + p.stderr.replace(env['POSTGRES_PASSWORD'], '[redacted]'))
        results.append(json.loads(p.stdout))
    assert [r['inserted'] for r in results] == [17532, 146100, 0, 0]
    assert [r['unchanged'] for r in results] == [0, 0, 17532, 146100]
    p = subprocess.run([sys.executable, '-m', 'scripts.ingest_stage12_4b5_historical', '--manifest', MANIFEST,
                        '--dataset-version', VERSIONS[0], '--apply', '--confirm-apply'], capture_output=True, text=True, env=run_env)
    assert p.returncode != 0 and 'Historical writes disabled' in p.stderr
    report = {'status': 'ISOLATED_CLI_IMPORT_AND_REPEAT_PASSED', 'database': DATABASE, 'results': results,
              'apply_rejected_even_with_confirmation': True, 'production_writes': False,
              'limitations': ['No independent operator authorization mechanism integrated', 'Full production preflight and production execution path remain disabled', 'This CLI test does not exercise all requested failure scenarios or nonempty pilot and weather fixtures']}
    Path('data/reports/stage12_4b10_cli_reconciliation_test.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
