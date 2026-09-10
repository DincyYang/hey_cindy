"""Isolate the test run from the developer's real .env and real databases.

`local/__init__.py` and `cloud/__init__.py` call `load_dotenv()` on import, and
that import can happen before this file runs (coverage resolves `--cov=<module>`
targets at startup). So these assignments overwrite rather than `setdefault` —
otherwise a developer's .env silently decides what the tests talk to.
"""
import os
import tempfile

_TMP_DB = os.path.join(tempfile.mkdtemp(prefix="hey-cindy-tests-"), "test.db")

os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DB}"   # never a real Postgres
os.environ["HEY_CINDY_TOKEN"] = "test-token"
os.environ.pop("ANTHROPIC_API_KEY", None)             # no live API calls from tests
