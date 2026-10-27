from dataclasses import replace
import pytest
from app.climate.production_guard import TargetIdentity, validate_preflight

IDENTITY = TargetIdentity("independently-configured-test", "127.0.0.1", "isolated", 5432, "tester", "17.5")


def valid(**kwargs):
    args = dict(expected=IDENTITY, observed=IDENTITY, revision="f78a9b0c1d2e", constraints_verified=True,
                source_verified=True, recorded_collation="2.31", actual_collation="2.31")
    args.update(kwargs)
    return validate_preflight(**args)


def test_valid_identity():
    valid()


@pytest.mark.parametrize("field,value", [("identifier", "other"), ("server", "other"), ("database", "production"),
                                         ("port", 1234), ("user", "other"), ("server_version", "18")])
def test_wrong_identity_rejected(field, value):
    with pytest.raises(ValueError, match="identity mismatch"):
        valid(observed=replace(IDENTITY, **{field: value}))


@pytest.mark.parametrize("change", [dict(revision="bad"), dict(constraints_verified=False),
                                    dict(source_verified=False), dict(actual_collation="2.41"),
                                    dict(recorded_collation=None)])
def test_failed_prerequisite_rejected(change):
    with pytest.raises(ValueError):
        valid(**change)
