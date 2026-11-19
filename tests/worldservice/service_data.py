"""The world service tests' data: the fixture jobs and which services are present.

SQLite always runs. PostgreSQL and Redis run when SKYVAULT_TEST_POSTGRES (a
DSN) and SKYVAULT_TEST_REDIS (a URL) are set; CI always sets both.
"""

import json
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
JOBS = json.loads(
    (REPO_ROOT / "tests" / "fixtures" / "service" / "jobs.json").read_text()
)["jobs"]
POSTGRES = os.environ.get("SKYVAULT_TEST_POSTGRES")
REDIS = os.environ.get("SKYVAULT_TEST_REDIS")


def job_request(name):
    """A fixture job as a request (a persistent world's advance list is the test's)."""
    return {k: v for k, v in JOBS[name].items() if k != "advance"}
