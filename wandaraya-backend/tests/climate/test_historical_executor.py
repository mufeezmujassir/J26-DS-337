from datetime import date

import pytest
from sqlalchemy import create_engine, text

from app.climate.historical_executor import checkpoints, import_sample, canonical_records


@pytest.fixture
def engine():
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE climate_dataset_versions (id INTEGER PRIMARY KEY, product_version TEXT NOT NULL)"))
        conn.execute(text("CREATE TABLE climate_grid_cells (id INTEGER PRIMARY KEY, dataset_version_id INTEGER NOT NULL)"))
        conn.execute(text("""CREATE TABLE climate_daily_observations (
            id INTEGER PRIMARY KEY, dataset_version_id INTEGER NOT NULL, grid_cell_id INTEGER NOT NULL,
            observation_date DATE NOT NULL, precipitation_mm FLOAT, temperature_mean_c FLOAT,
            temperature_min_c FLOAT, temperature_max_c FLOAT, relative_humidity_pct FLOAT,
            wind_speed FLOAT, wind_speed_unit TEXT, solar_radiation FLOAT, solar_radiation_unit TEXT,
            quality_status TEXT NOT NULL, source_record_hash TEXT NOT NULL, created_at DATETIME NOT NULL,
            UNIQUE(dataset_version_id, grid_cell_id, observation_date))"""))
        conn.execute(text("INSERT INTO climate_dataset_versions VALUES (1, 'nasa_power_daily_v2.10.0_historical_2010_2025_batch01'), (2, 'nasa_power_daily_v2.10.0_2024_pilot')"))
        conn.execute(text("INSERT INTO climate_grid_cells VALUES (10, 1), (20, 2)"))
    checkpoints.create(engine)
    yield engine
    engine.dispose()


def sample(engine, **overrides):
    args = dict(dataset_version_id=1, grid_cell_id=10, sample_id="test", source_sha256="a" * 64,
                records=[{"date": "2024-01-01", "temperature_mean_c": 20.0},
                         {"date": "2024-01-02", "temperature_mean_c": 21.0}],
                expected_dates={date(2024, 1, 1), date(2024, 1, 2)}, batch_size=1)
    args.update(overrides)
    return import_sample(engine, **args)


def test_import_repeat_and_source_conflict(engine):
    assert sample(engine)["inserted"] == 2
    assert sample(engine)["unchanged"] == 2
    with pytest.raises(ValueError, match="checkpoint conflicts"):
        sample(engine, source_sha256="b" * 64)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM climate_daily_observations")).scalar_one() == 2


def test_interruption_rolls_back_and_resume(engine):
    def fail():
        raise RuntimeError("simulated interruption")
    with pytest.raises(RuntimeError):
        sample(engine, _before_checkpoint=fail)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM climate_daily_observations")).scalar_one() == 0
        assert conn.execute(text("SELECT count(*) FROM climate_historical_import_checkpoints")).scalar_one() == 0
    assert sample(engine)["inserted"] == 2


def test_pilot_is_protected_and_scope_checked(engine):
    with pytest.raises(ValueError, match="not an authorized historical"):
        sample(engine, dataset_version_id=2, grid_cell_id=20)
    with pytest.raises(ValueError, match="date scope"):
        sample(engine, expected_dates={date(2024, 1, 1)})


def test_duplicate_dates_and_nonfinite_values():
    with pytest.raises(ValueError, match="duplicate"):
        canonical_records([{"date": "2024-01-01"}, {"date": "2024-01-01"}])
    with pytest.raises(ValueError, match="invalid"):
        canonical_records([{"date": "2024-01-01", "precipitation_mm": float("nan")}])


def test_cross_dataset_grid_rejected(engine):
    with pytest.raises(ValueError, match="grid belongs"):
        sample(engine, grid_cell_id=20)


def test_inconsistent_checkpoint_rejected(engine):
    sample(engine)
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM climate_daily_observations WHERE observation_date = '2024-01-01'"))
    with pytest.raises(ValueError, match="observations are incomplete"):
        sample(engine)


def test_postgres_nonisolated_target_fails_before_connection():
    engine = create_engine("postgresql+psycopg://postgres@127.0.0.1:5432/wandaraya")
    with pytest.raises(ValueError, match="not an approved isolated"):
        sample(engine)
