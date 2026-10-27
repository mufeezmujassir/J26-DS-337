from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import base64
import json
import shutil
import subprocess
from dataclasses import asdict
import pytest
from app.climate.import_authorization import ImportBinding, binding_digest, validate_backup, validate_binding, verify_signed_approval


@pytest.fixture
def binding():
    return ImportBinding('historical_climate_import', 'independent-test-server-id', 'nasa_power_daily_v2.10.0_historical_2010_2025_batch01', 17532, 'a'*64, 'b'*64)


def test_approval_bound_to_all_values(binding):
    approval = {'approved': True, 'binding_sha256': binding_digest(binding)}
    validate_binding(binding, approval)
    for change in ({'database_identity': 'other'}, {'dataset_version': 'nasa_power_daily_v2.10.0_historical_2010_2025_batch02', 'expected_count': 146100}, {'manifest_sha256': 'c'*64}, {'backup_sha256': 'd'*64}, {'operation': 'other'}, {'expected_count': 1}):
        with pytest.raises(ValueError):
            validate_binding(replace(binding, **change), approval)


@pytest.mark.parametrize('approval', [None, {}, {'approved': False}, {'approved': True, 'binding_sha256': 'wrong'}])
def test_missing_or_wrong_approval(binding, approval):
    with pytest.raises(ValueError):
        validate_binding(binding, approval)


def test_backup_and_restore_evidence(tmp_path):
    backup = tmp_path / 'backup.dump'
    backup.write_bytes(b'test backup')
    digest = hashlib.sha256(backup.read_bytes()).hexdigest()
    now = datetime(2026, 10, 20, tzinfo=timezone.utc)
    evidence = {'backup_sha256': digest, 'backup_created_at': now.isoformat(), 'restore_passed': True, 'protected_content_matches': True}
    validate_backup(backup, digest, evidence, max_age_seconds=3600, now=now)
    for altered in ({**evidence, 'restore_passed': False}, {**evidence, 'protected_content_matches': False}, {**evidence, 'backup_sha256': 'a'*64}, {**evidence, 'backup_created_at': '2025-01-01T00:00:00+00:00'}):
        with pytest.raises(ValueError):
            validate_backup(backup, digest, altered, max_age_seconds=3600, now=now)
    backup.write_bytes(b'changed')
    with pytest.raises(ValueError):
        validate_backup(backup, digest, evidence, max_age_seconds=3600, now=now)


def test_independent_ed25519_approval(binding, tmp_path):
    openssl = shutil.which('openssl') or shutil.which(r'C:\Program Files\Git\usr\bin\openssl.exe')
    if not openssl:
        pytest.skip('openssl unavailable')
    private = tmp_path / 'private.pem'
    public = tmp_path / 'public.pem'
    message = tmp_path / 'message.json'
    signature = tmp_path / 'signature.bin'
    subprocess.run([openssl, 'genpkey', '-algorithm', 'ED25519', '-out', str(private)], check=True, capture_output=True)
    subprocess.run([openssl, 'pkey', '-in', str(private), '-pubout', '-out', str(public)], check=True, capture_output=True)
    message.write_bytes(json.dumps(asdict(binding), sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode())
    subprocess.run([openssl, 'pkeyutl', '-sign', '-inkey', str(private), '-rawin', '-in', str(message), '-out', str(signature)], check=True, capture_output=True)
    der = subprocess.run([openssl, 'pkey', '-pubin', '-in', str(public), '-outform', 'DER'], check=True, capture_output=True).stdout
    pin = hashlib.sha256(der).hexdigest()
    approval = {'approved': True, 'binding_sha256': binding_digest(binding), 'signature_base64': base64.b64encode(signature.read_bytes()).decode()}
    verify_signed_approval(binding, approval, public, pin, openssl=openssl)
    with pytest.raises(ValueError):
        verify_signed_approval(binding, approval, public, '0'*64, openssl=openssl)
    approval['signature_base64'] = base64.b64encode(b'x'*64).decode()
    with pytest.raises(ValueError):
        verify_signed_approval(binding, approval, public, pin, openssl=openssl)
