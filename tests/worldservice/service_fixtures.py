"""
The world service tests' fixtures: every store the environment offers,
Redis when it is there, and the default policy.

Important:
Not a conftest.py: other test folders import their own conftest by name at
test time, and a second conftest module would shadow theirs. Test files
load this module with pytest_plugins.
"""

import pytest
from service_data import POSTGRES, REDIS

from skyvault.worldservice.governance import load_governance
from skyvault.worldservice.store import PostgresStore, SQLiteStore


def fresh_postgres() -> PostgresStore:
    store = PostgresStore(POSTGRES or "")
    store._run("DROP TABLE IF EXISTS jobs, results, checkpoints, job_events")
    store.setup()
    return store


@pytest.fixture(params=["sqlite", "postgres"])
def store(request, tmp_path):
    if request.param == "sqlite":
        return SQLiteStore(str(tmp_path / "service.sqlite"))
    if not POSTGRES:
        pytest.skip("SKYVAULT_TEST_POSTGRES is not set (CI sets it)")
    return fresh_postgres()


@pytest.fixture
def redis_url():
    if not REDIS:
        pytest.skip("SKYVAULT_TEST_REDIS is not set (CI sets it)")
    return REDIS


@pytest.fixture
def policy():
    return load_governance()
