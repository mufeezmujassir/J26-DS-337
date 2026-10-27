import pytest

from app.climate.live_readiness import CONSTRAINTS, check_constraint_definitions


def test_constraint_definitions_are_verified_not_just_names():
    check_constraint_definitions(dict(CONSTRAINTS))
    changed = dict(CONSTRAINTS)
    changed['uq_climate_daily_observation'] = 'UNIQUE (dataset_version_id)'
    with pytest.raises(ValueError, match='uq_climate_daily_observation'):
        check_constraint_definitions(changed)
    changed = dict(CONSTRAINTS)
    del changed['uq_climate_grid_cell_version_source']
    with pytest.raises(ValueError, match='uq_climate_grid_cell_version_source'):
        check_constraint_definitions(changed)
