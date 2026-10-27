"""Test the batch orchestrator against a fresh, verified isolated database."""
import json
import os
import subprocess
import sys
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from app.climate.historical_orchestrator import import_isolated_batch
from scripts.test_stage12_4b5_postgres_executor import load_verified

CONTAINER = 'wandaraya-climate-executor-integration-test'
DATABASE = 'climate_orchestrator_isolated_test'
USER = 'climate_executor_test'


def docker(*args):
    return subprocess.run(['docker', *args], text=True, capture_output=True, check=True).stdout.strip()


def main():
    info = json.loads(docker('inspect', CONTAINER))[0]
    ports = info['NetworkSettings']['Ports']['5432/tcp']
    env = dict(item.split('=', 1) for item in info['Config']['Env'] if '=' in item)
    if (info['Config']['Image'] != 'postgis/postgis:17-3.5' or len(ports) != 1 or ports[0]['HostIp'] != '127.0.0.1'
            or env.get('POSTGRES_USER') != USER or env.get('POSTGRES_DB') != 'climate_executor_isolated_test'
            or any(m.get('Source', '').lower().endswith('postgres-data') for m in info['Mounts'])):
        raise RuntimeError('test target failed container identity checks')
    if docker('exec', CONTAINER, 'psql', '-U', USER, '-d', 'postgres', '-tAc', "SELECT 1 FROM pg_database WHERE datname='climate_orchestrator_isolated_test'"):
        raise RuntimeError('test database exists; refusing to overwrite or reuse it')
    verified = load_verified()
    docker('exec', CONTAINER, 'createdb', '-U', USER, DATABASE)
    docker('exec', CONTAINER, 'psql', '-v', 'ON_ERROR_STOP=1', '-U', USER, '-d', DATABASE, '-c', 'CREATE EXTENSION postgis')
    url = URL.create('postgresql+psycopg', username=USER, password=env['POSTGRES_PASSWORD'], host='127.0.0.1', port=int(ports[0]['HostPort']), database=DATABASE)
    run_env = os.environ.copy()
    run_env['DATABASE_URL'] = url.render_as_string(hide_password=False)
    migration = subprocess.run([sys.executable, '-m', 'alembic', 'upgrade', 'f78a9b0c1d2e'], env=run_env, capture_output=True, text=True)
    if migration.returncode:
        raise RuntimeError('isolated migration failed: ' + migration.stderr.replace(env['POSTGRES_PASSWORD'], '[redacted]'))
    engine = create_engine(url)
    try:
        results = [import_isolated_batch(engine, batch, verified) for batch in ('batch01', 'batch02', 'batch01', 'batch02')]
        assert [r['inserted'] for r in results] == [17532, 146100, 0, 0]
        assert [r['unchanged'] for r in results] == [0, 0, 17532, 146100]
        with engine.connect() as conn:
            total = conn.execute(text('SELECT count(*) FROM climate_daily_observations')).scalar_one()
            checkpoints = conn.execute(text('SELECT count(*) FROM climate_historical_import_checkpoints')).scalar_one()
        assert (total, checkpoints) == (163632, 28)
        report = {'status': 'ISOLATED_BATCH_ORCHESTRATOR_PASSED', 'database': DATABASE, 'results': results, 'observations': total, 'checkpoints': checkpoints, 'production_postgresql_writes': False, 'limitations': ['Not a production execution path', 'No full CLI authorization or backup gate tested', 'No nonempty pilot/weather records seeded in this test; see Stage 12.4B.9 for lower-level preservation test']}
        Path('data/reports/historical_orchestrator_isolated_test.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(report, indent=2))
    finally:
        engine.dispose()


if __name__ == '__main__':
    main()
