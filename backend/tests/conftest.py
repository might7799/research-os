import os
import secrets
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_TEST_DATABASE_DIRECTORY = tempfile.TemporaryDirectory(prefix="research-os-tests-")
os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_TEST_DATABASE_DIRECTORY.name) / 'research_os_test.db'}"
os.environ["JWT_SECRET"] = secrets.token_urlsafe(48)
os.environ["JWT_ALGORITHM"] = "HS256"


def pytest_unconfigure(config):
    _TEST_DATABASE_DIRECTORY.cleanup()
