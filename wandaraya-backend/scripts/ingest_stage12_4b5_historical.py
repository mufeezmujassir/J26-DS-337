"""Historical climate validation and signed, target-checked import."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from dataclasses import asdict
from pathlib import Path
from app.climate.production_guard import TargetIdentity, validate_preflight
from app.climate.import_authorization import ImportBinding, EXPECTED_COUNTS, verify_signed_approval
from app.climate.providers.nasa_power import normalize
from scripts.audit_stage12_4b5_historical import audit_sample

VERSIONS = {
    'nasa_power_daily_v2.10.0_historical_2010_2025_batch01': 'batch01',
    'nasa_power_daily_v2.10.0_historical_2010_2025_batch02': 'batch02',
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest', required=True, type=Path, help='verified stage12_4b5_source_provenance.json')
    parser.add_argument('--dataset-version', required=True, choices=VERSIONS)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--dry-run', action='store_true')
    parser.add_argument('--validate-only', action='store_true')
    parser.add_argument('--max-records', type=int, default=200000)
    parser.add_argument('--batch-size', type=int, default=1000)
    parser.add_argument('--resume', action='store_true')
    modes.add_argument('--verify', action='store_true')
    modes.add_argument('--isolated-test', action='store_true')
    parser.add_argument('--target-identity', type=Path, help='independently supplied read-only target identity JSON')
    parser.add_argument('--authorization-file', type=Path, help='signed approval for the exact import request')
    modes.add_argument('--apply', action='store_true')
    parser.add_argument('--confirm-apply', action='store_true')
    args = parser.parse_args()
    if args.apply:
        if not (args.confirm_apply and args.authorization_file and args.target_identity):
            raise SystemExit('Historical writes disabled: --apply requires --confirm-apply, --authorization-file and --target-identity')
        key_path = os.environ.get('CLIMATE_APPROVAL_PUBLIC_KEY')
        key_pin = os.environ.get('CLIMATE_APPROVAL_KEY_SHA256')
        if not key_path or not key_pin:
            raise SystemExit('Historical writes disabled: independently provisioned approval key and pin are required')
        try:
            target = TargetIdentity(**json.loads(args.target_identity.read_text(encoding='utf-8')))
            canonical_target = json.dumps(asdict(target), sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()
            backup_report = json.loads(Path('data/reports/stage12_4b9_backup_readiness.json').read_text(encoding='utf-8'))
            backup_digest = hashlib.sha256(Path(backup_report['backup']).read_bytes()).hexdigest()
            if backup_digest != backup_report['sha256']:
                raise ValueError('backup checksum mismatch')
            binding = ImportBinding('historical_climate_import', hashlib.sha256(canonical_target).hexdigest(),
                                    args.dataset_version, EXPECTED_COUNTS[args.dataset_version],
                                    hashlib.sha256(args.manifest.read_bytes()).hexdigest(), backup_digest)
            approval = json.loads(args.authorization_file.read_text(encoding='utf-8'))
            verify_signed_approval(binding, approval, Path(key_path), key_pin)
        except (OSError, ValueError, TypeError, KeyError) as exc:
            raise SystemExit('Historical writes disabled: signed request verification failed: ' + str(exc)) from exc
        from sqlalchemy import create_engine, text
        from app.config import settings
        from app.climate.historical_orchestrator import import_isolated_batch
        from app.climate.live_readiness import inspect_read_only
        from app.climate.production_guard import verify_connection_identity
        from scripts.test_stage12_4b5_postgres_executor import load_verified
        if args.manifest.resolve() != Path('data/reports/stage12_4b5_source_provenance.json').resolve():
            raise SystemExit('import requires the reviewed provenance manifest')
        if args.max_records < EXPECTED_COUNTS[args.dataset_version] or args.batch_size < 1:
            raise SystemExit('invalid batch size or max-records is below the batch scope')
        if (backup_report.get('pg_restore_exit_code') != 0 or not backup_report.get('protected_counts_and_hashes_match')
                or not backup_report.get('host_container_and_restore_copy_checksums_match')):
            raise SystemExit('Historical writes disabled: isolated backup restore evidence missing')
        created = datetime.fromisoformat(backup_report['created_local'])
        if created.tzinfo is None or not 0 <= (datetime.now(timezone.utc) - created).total_seconds() <= 86400:
            raise SystemExit('Historical writes disabled: backup is older than 24 hours or has an invalid timestamp')
        baseline = json.loads(Path('data/reports/stage12_4b7_content_baseline.json').read_text(encoding='utf-8'))
        if baseline.get('database') != target.database:
            raise SystemExit('Historical writes disabled: protected baseline targets a different database')
        verified = load_verified()
        engine = create_engine(settings.DATABASE_URL)
        try:
            with engine.connect() as lock:
                verify_connection_identity(lock, target)
                if not lock.execute(text('SELECT pg_try_advisory_lock(120412, 510)')).scalar_one():
                    raise ValueError('another historical import is running')
                try:
                    with engine.connect() as conn:
                        conn.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY'))
                        row = conn.execute(text("SELECT current_database(), current_user, inet_server_addr()::text, inet_server_port(), current_setting('server_version'), (pg_control_system()).system_identifier::text, datcollversion, pg_database_collation_actual_version(oid) FROM pg_database WHERE datname=current_database()")).one()
                        observed = TargetIdentity(row[5], row[2] or '', row[0], row[3] or 0, row[1], row[4])
                        revision = conn.execute(text('SELECT version_num FROM alembic_version')).scalar_one()
                        inspect_read_only(conn, baseline)
                        validate_preflight(target, observed, revision=revision, constraints_verified=True,
                                           source_verified=True, recorded_collation=row[6], actual_collation=row[7])
                    result = import_isolated_batch(engine, VERSIONS[args.dataset_version], verified, target_identity=target, batch_size=args.batch_size)
                    with engine.connect() as conn:
                        conn.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY'))
                        verify_connection_identity(conn, target)
                        inspect_read_only(conn, baseline)
                finally:
                    lock.execute(text('SELECT pg_advisory_unlock(120412, 510)'))
        finally:
            engine.dispose()
        print(json.dumps({'status': 'SIGNED_IMPORT_RECONCILED', **result}, indent=2))
        return
    if args.confirm_apply:
        raise SystemExit('--confirm-apply is invalid without an enabled --apply')
    if args.isolated_test:
        from sqlalchemy import create_engine
        from app.config import settings
        from app.climate.historical_orchestrator import import_isolated_batch
        from scripts.test_stage12_4b5_postgres_executor import load_verified
        if args.manifest.resolve() != Path('data/reports/stage12_4b5_source_provenance.json').resolve():
            raise SystemExit('isolated CLI requires the reviewed provenance manifest')
        verified = load_verified()
        engine = create_engine(settings.DATABASE_URL)
        try:
            try:
                result = import_isolated_batch(engine, VERSIONS[args.dataset_version], verified)
            except ValueError as exc:
                raise SystemExit('Isolated import rejected: ' + str(exc)) from exc
        finally:
            engine.dispose()
        print(json.dumps({'status': 'ISOLATED_IMPORT_RECONCILED', **result, 'production_postgresql_writes': False}, indent=2))
        return
    if args.max_records < 1 or args.batch_size < 1:
        raise SystemExit('batch size and maximum records must be positive')
    manifest = json.loads(args.manifest.read_text(encoding='utf-8'))
    samples = [s for s in manifest['samples'] if s['batch'] == VERSIONS[args.dataset_version]]
    expected_samples = 3 if VERSIONS[args.dataset_version] == 'batch01' else 25
    if len(samples) != expected_samples or len({s['sample_id'] for s in samples}) != expected_samples:
        raise SystemExit('manifest has missing or duplicate sample identities')
    for s in samples:
        actual = hashlib.sha256(Path(s['raw_file']).read_bytes()).hexdigest()
        if actual != s['original_acquisition_sha256']:
            raise SystemExit('source checksum mismatch: ' + s['sample_id'])
        # Revalidate the original provider response rather than trusting the
        # report or the processed file to represent current source evidence.
        audit = audit_sample(s, s['original_acquisition_sha256'])
        if audit['structural_errors'] or audit['temperature_min_exceeds_max']:
            raise SystemExit('source validation failure: ' + s['sample_id'])
        if any(p['invalid'] or p['missing'] for p in audit['parameters'].values()):
            raise SystemExit('invalid source values: ' + s['sample_id'])
        processed_path = Path(s['raw_file'].replace('raw/nasa_power/', 'processed/nasa_power/'))
        processed = json.loads(processed_path.read_text(encoding='utf-8'))
        source_records, source_metadata = normalize(json.loads(Path(s['raw_file']).read_bytes()))
        if processed.get('records') != source_records or processed.get('metadata') != source_metadata:
            raise SystemExit('processed file differs from normalized raw source: ' + s['sample_id'])
    count = len(samples)*5844
    if count > args.max_records:
        raise SystemExit('max-records exceeded; no partial scope implicitly selected')
    if args.verify:
        if not args.target_identity:
            raise SystemExit('--verify requires an independently supplied --target-identity JSON file')
        # The preflight may validate identity, schema and source, but it does
        # not establish backup, named-collation or operator authorization.
        from sqlalchemy import create_engine, text
        from app.config import settings
        from app.climate.live_readiness import inspect_read_only
        expected = TargetIdentity(**json.loads(args.target_identity.read_text(encoding='utf-8')))
        baseline = json.loads(Path('data/reports/stage12_4b7_content_baseline.json').read_text(encoding='utf-8'))
        if baseline.get('database') != expected.database:
            raise SystemExit('baseline database does not match the expected target')
        engine = create_engine(settings.DATABASE_URL)
        try:
            with engine.connect() as conn:
                conn.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY'))
                row = conn.execute(text("SELECT current_database(), current_user, inet_server_addr()::text, inet_server_port(), current_setting('server_version'), (pg_control_system()).system_identifier::text, datcollversion, pg_database_collation_actual_version(oid) FROM pg_database WHERE datname=current_database()" )).one()
                observed = TargetIdentity(row[5], row[2] or '', row[0], row[3] or 0, row[1], row[4])
                revision = conn.execute(text('SELECT version_num FROM alembic_version')).scalar_one()
                required = {'uq_climate_daily_observation', 'uq_climate_checkpoint_sample', 'climate_historical_import_checkpoints_pkey', 'climate_grid_cells_dataset_version_id_fkey'}
                names = set(conn.execute(text("SELECT conname FROM pg_constraint WHERE convalidated AND conrelid IN ('public.climate_daily_observations'::regclass, 'public.climate_historical_import_checkpoints'::regclass, 'public.climate_grid_cells'::regclass)" )).scalars())
                validate_preflight(expected, observed, revision=revision, constraints_verified=required <= names,
                                   source_verified=True, recorded_collation=row[6], actual_collation=row[7])
                inspect_read_only(conn, baseline)
        finally:
            engine.dispose()
        raise SystemExit('Read-only identity, constraint, source, direct named-collation and baseline checks passed; NOT READY: independent backup/approval evidence, dynamic collation use and production executor integration are not verified; production apply remains disabled')
    print(json.dumps({'status': 'DRY_RUN_CHECKSUM_SCOPE_VALIDATED', 'dataset_version': args.dataset_version,
                      'samples': len(samples), 'expected_records': count, 'postgresql_writes': False,
                      'qdrant_writes': False, 'network_requests': 0,
                      'limitations': ['no database transaction tested', 'collation state not checked by this file-only dry run',
                                      'historical apply is disabled']}, indent=2))


if __name__ == '__main__':
    main()
