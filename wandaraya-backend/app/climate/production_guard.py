"""Pure fail-closed target and schema checks. This does not authorize writes."""
from dataclasses import dataclass
from sqlalchemy import text


@dataclass(frozen=True)
class TargetIdentity:
    identifier: str
    server: str
    database: str
    port: int
    user: str
    server_version: str


def verify_connection_identity(conn, expected: TargetIdentity) -> None:
    row = conn.execute(text("SELECT (pg_control_system()).system_identifier::text, inet_server_addr()::text, current_database(), inet_server_port(), current_user, current_setting('server_version')")).one()
    observed = TargetIdentity(row[0], row[1] or '', row[2], row[3] or 0, row[4], row[5])
    if observed != expected:
        raise ValueError('database target identity mismatch')


def validate_preflight(expected: TargetIdentity, observed: TargetIdentity, *, revision: str,
                       constraints_verified: bool, source_verified: bool,
                       recorded_collation: str | None, actual_collation: str | None) -> None:
    if not expected.identifier or not expected.server or not expected.database or not expected.user or not expected.server_version or not expected.port:
        raise ValueError("incomplete independent target identity")
    if expected != observed:
        raise ValueError("database target identity mismatch")
    if revision != "f78a9b0c1d2e":
        raise ValueError("unexpected Alembic revision")
    if not constraints_verified:
        raise ValueError("schema constraints not verified")
    if not source_verified:
        raise ValueError("source checksums not verified")
    if not recorded_collation or not actual_collation or recorded_collation != actual_collation:
        raise ValueError("default collation mismatch or unknown")
