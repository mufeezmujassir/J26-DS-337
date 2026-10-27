"""Explicit request binding and evidence checks; not a production write grant.

These checks are deliberately pure and must be coupled to live transaction,
server identity, baseline and restore validation before enabling writes.
"""
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import base64
import subprocess
import tempfile
from pathlib import Path


@dataclass(frozen=True)
class ImportBinding:
    operation: str
    database_identity: str
    dataset_version: str
    expected_count: int
    manifest_sha256: str
    backup_sha256: str


EXPECTED_COUNTS = {
    'nasa_power_daily_v2.10.0_historical_2010_2025_batch01': 17532,
    'nasa_power_daily_v2.10.0_historical_2010_2025_batch02': 146100,
}


def binding_digest(binding: ImportBinding) -> str:
    return hashlib.sha256(json.dumps(asdict(binding), sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()).hexdigest()


def verify_signed_approval(binding: ImportBinding, approval: dict, trusted_public_key: Path,
                           expected_key_sha256: str, *, openssl: str = 'openssl') -> None:
    """Verify Ed25519 approval against an independently provisioned key pin.

    The public key and pin must come from a trusted operator-controlled source,
    never from the approval file itself. This function is not a database grant.
    """
    validate_binding(binding, approval)
    if len(expected_key_sha256) != 64 or any(c not in '0123456789abcdef' for c in expected_key_sha256):
        raise ValueError('invalid trusted key pin')
    try:
        signature = base64.b64decode(approval['signature_base64'], validate=True)
        public = subprocess.run([openssl, 'pkey', '-pubin', '-in', str(trusted_public_key), '-outform', 'DER'], check=True, capture_output=True, timeout=10).stdout
        key_type = subprocess.run([openssl, 'pkey', '-pubin', '-in', str(trusted_public_key), '-text', '-noout'], check=True, capture_output=True, text=True, timeout=10).stdout
        if 'ED25519 Public-Key' not in key_type or hashlib.sha256(public).hexdigest() != expected_key_sha256:
            raise ValueError('untrusted or non-Ed25519 approval key')
        if len(signature) != 64:
            raise ValueError('invalid Ed25519 signature length')
        message = json.dumps(asdict(binding), sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()
        with tempfile.TemporaryDirectory(prefix='climate-approval-') as directory:
            message_path = Path(directory) / 'binding.json'
            signature_path = Path(directory) / 'signature.bin'
            message_path.write_bytes(message)
            signature_path.write_bytes(signature)
            subprocess.run([openssl, 'pkeyutl', '-verify', '-pubin', '-inkey', str(trusted_public_key), '-rawin', '-in', str(message_path), '-sigfile', str(signature_path)], check=True, capture_output=True, timeout=10)
    except (KeyError, TypeError, ValueError, OSError, subprocess.SubprocessError) as exc:
        raise ValueError('independent approval signature verification failed') from exc


def validate_binding(binding: ImportBinding, approval: dict | None) -> None:
    if binding.operation != 'historical_climate_import' or not binding.database_identity:
        raise ValueError('invalid operation or database identity')
    if EXPECTED_COUNTS.get(binding.dataset_version) != binding.expected_count:
        raise ValueError('unexpected historical version or count')
    for digest in (binding.manifest_sha256, binding.backup_sha256):
        if len(digest) != 64 or any(ch not in '0123456789abcdef' for ch in digest):
            raise ValueError('invalid SHA-256')
    if not isinstance(approval, dict) or approval.get('approved') is not True:
        raise ValueError('explicit operator approval missing')
    if approval.get('binding_sha256') != binding_digest(binding):
        raise ValueError('approval does not match requested target, scope, manifest and backup')


def validate_backup(path: Path, expected_sha256: str, restore: dict, *, max_age_seconds: int, now: datetime) -> None:
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected_sha256:
        raise ValueError('backup missing or checksum mismatch')
    if now.tzinfo is None or max_age_seconds <= 0:
        raise ValueError('invalid backup age policy')
    if not isinstance(restore, dict) or restore.get('backup_sha256') != expected_sha256 or restore.get('restore_passed') is not True or restore.get('protected_content_matches') is not True:
        raise ValueError('backup restore evidence missing or failed')
    try:
        captured = datetime.fromisoformat(restore['backup_created_at'])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError('invalid backup timestamp') from exc
    if captured.tzinfo is None:
        raise ValueError('backup timestamp must include a timezone')
    age = (now.astimezone(timezone.utc) - captured.astimezone(timezone.utc)).total_seconds()
    if age < 0 or age > max_age_seconds:
        raise ValueError('backup is outside approved freshness window')
