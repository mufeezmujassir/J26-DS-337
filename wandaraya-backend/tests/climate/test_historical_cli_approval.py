"""The production CLI must fail closed even after signature verification."""
import hashlib
import json
import sys

import pytest

from scripts import ingest_stage12_4b5_historical as cli


def test_apply_requires_approval_arguments(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, 'argv', ['import', '--manifest', str(tmp_path / 'manifest'),
        '--dataset-version', next(iter(cli.VERSIONS)), '--apply', '--confirm-apply'])
    with pytest.raises(SystemExit, match='requires --confirm-apply'):
        cli.main()


def test_signed_request_rejects_unreviewed_manifest(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    reports = tmp_path / 'data' / 'reports'
    reports.mkdir(parents=True)
    backup = tmp_path / 'backup.dump'
    backup.write_bytes(b'test backup')
    (reports / 'stage12_4b9_backup_readiness.json').write_text(json.dumps({
        'backup': str(backup), 'sha256': hashlib.sha256(b'test backup').hexdigest()}))
    manifest = tmp_path / 'manifest.json'
    manifest.write_text('{}')
    identity = tmp_path / 'target.json'
    identity.write_text(json.dumps({'identifier': 'test', 'server': 'localhost',
        'database': 'test', 'port': 5432, 'user': 'test', 'server_version': '17'}))
    approval = tmp_path / 'approval.json'
    approval.write_text('{}')
    monkeypatch.setenv('CLIMATE_APPROVAL_PUBLIC_KEY', str(tmp_path / 'public.pem'))
    monkeypatch.setenv('CLIMATE_APPROVAL_KEY_SHA256', 'a' * 64)
    seen = []
    monkeypatch.setattr(cli, 'verify_signed_approval', lambda *args: seen.append(args))
    monkeypatch.setattr(sys, 'argv', ['import', '--manifest', str(manifest), '--dataset-version',
        next(iter(cli.VERSIONS)), '--apply', '--confirm-apply', '--target-identity', str(identity),
        '--authorization-file', str(approval)])
    with pytest.raises(SystemExit, match='reviewed provenance manifest'):
        cli.main()
    assert len(seen) == 1
    backup.write_bytes(b'changed')
    with pytest.raises(SystemExit, match='backup checksum mismatch'):
        cli.main()
    assert len(seen) == 1
