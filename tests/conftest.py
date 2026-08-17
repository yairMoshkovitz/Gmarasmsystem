import pytest
import os
import sqlite3
import base64
from pathlib import Path
from database import DB_PATH, SCHEMA_PATH, init_db, seed_tractates, seed_sms_templates, seed_questions, get_conn
from sms_service import set_live_mode
from simulation_system import USER_STATES

# Tables that should be cleared between tests (not questions/tractates/sms_templates)
_PER_TEST_TABLES = ["users", "subscriptions", "sent_questions", "sms_log",
                    "pending_admin_messages", "settings", "support_requests", "assignees"]

TEST_DB = "gemara_sms_test.db"


def _clear_per_test_tables():
    conn = sqlite3.connect(TEST_DB)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    existing = {r[0] for r in cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    for table in _PER_TEST_TABLES:
        if table in existing:
            cursor.execute(f"DELETE FROM {table}")
    conn.commit()
    conn.close()


@pytest.fixture(autouse=True)
def setup_test_db(monkeypatch):
    """Fixture to set up a clean test database for each test."""
    monkeypatch.setenv("DATABASE_URL", "")  # Force SQLite for tests

    import database
    original_db_path = database.DB_PATH
    database.DB_PATH = Path(TEST_DB)

    db_exists = os.path.exists(TEST_DB)

    if not db_exists:
        # First run: full initialization including questions
        init_db()
        seed_tractates()
        seed_sms_templates()
        seed_questions()
    else:
        # Subsequent runs: just clear per-test tables, keep questions
        _clear_per_test_tables()
        init_db()       # ensures schema is up to date
        seed_tractates()
        seed_sms_templates()

    set_live_mode(False)
    USER_STATES.clear()

    yield

    database.DB_PATH = original_db_path


@pytest.fixture
def db_conn():
    """Returns a connection to the test database."""
    conn = get_conn()
    yield conn
    conn.close()


@pytest.fixture
def client():
    """Flask test client."""
    from app import app
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


@pytest.fixture
def auth_headers(monkeypatch):
    """Basic Auth header for hitting @basic_auth_required routes in tests."""
    monkeypatch.setenv("SITE_PASSWORD", "testpass123")
    creds = base64.b64encode(b"admin:testpass123").decode()
    return {"Authorization": f"Basic {creds}"}
