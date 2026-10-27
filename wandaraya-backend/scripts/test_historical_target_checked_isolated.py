"""Exercise the target-checked orchestrator against an existing isolated DB."""
import json
import subprocess
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from app.climate.historical_orchestrator import import_isolated_batch
from app.climate.production_guard import TargetIdentity
from scripts.test_stage12_4b5_postgres_executor import load_verified


def main():
    raw = subprocess.run(['docker', 'inspect', 'wandaraya-climate-executor-integration-test'], check=True, capture_output=True, text=True).stdout
    info = json.loads(raw)[0]
    env = dict(item.split('=', 1) for item in info['Config']['Env'] if '=' in item)
    ports = info['NetworkSettings']['Ports']['5432/tcp']
    if (info['Config']['Image'] != 'postgis/postgis:17-3.5' or env.get('POSTGRES_USER') != 'climate_executor_test'
            or env.get('POSTGRES_DB') != 'climate_executor_isolated_test' or len(ports) != 1
            or ports[0]['HostIp'] != '127.0.0.1' or any(m.get('Source', '').lower().endswith('postgres-data') for m in info['Mounts'])):
        raise RuntimeError('test container identity check failed')
    url = URL.create('postgresql+psycopg', username=env['POSTGRES_USER'], password=env['POSTGRES_PASSWORD'],
                     host='127.0.0.1', port=int(ports[0]['HostPort']), database='climate_cli_reconcile_isolated_test')
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            row = conn.execute(text("SELECT (pg_control_system()).system_identifier::text, inet_server_addr()::text, current_database(), inet_server_port(), current_user, current_setting('server_version')")).one()
        target = TargetIdentity(row[0], row[1] or '', row[2], row[3] or 0, row[4], row[5])
        if target.database != 'climate_cli_reconcile_isolated_test' or target.user != 'climate_executor_test':
            raise RuntimeError('test database identity check failed')
        verified = load_verified()
        result = [import_isolated_batch(engine, batch, verified, target_identity=target) for batch in ('batch01', 'batch02')]
        assert [x['inserted'] for x in result] == [0, 0]
        assert [x['unchanged'] for x in result] == [17532, 146100]
        wrong = TargetIdentity('wrong', target.server, target.database, target.port, target.user, target.server_version)
        try:
            import_isolated_batch(engine, 'batch01', verified, target_identity=wrong)
        except ValueError as exc:
            if 'identity mismatch' not in str(exc):
                raise
        else:
            raise AssertionError('wrong target identity accepted')
        print(json.dumps({'status': 'TARGET_CHECKED_ISOLATED_REPEAT_PASSED', 'results': result,
                          'wrong_target_rejected': True, 'production_writes': False,
                          'limitations': ['previously populated isolated database reused', 'signed CLI path not covered']}))
    finally:
        engine.dispose()


if __name__ == '__main__':
    main()
