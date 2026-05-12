import pytest
import os
import sqlite3
import json
from pathlib import Path
from database import DB_PATH, SCHEMA_PATH, init_db, seed_tractates, seed_sms_templates, get_conn
from sms_service import set_live_mode
from simulation_system import USER_STATES

@pytest.fixture(autouse=True)
def setup_test_db(monkeypatch):
    """Fixture to set up a clean test database for each test."""
    test_db = "gemara_sms_test.db"
    monkeypatch.setenv("DATABASE_URL", "") # Force SQLite for tests
    
    # Update DB_PATH in database module
    import database
    original_db_path = database.DB_PATH
    database.DB_PATH = Path(test_db)
    
    # Remove if exists
    if os.path.exists(test_db):
        try:
            os.remove(test_db)
        except PermissionError:
            # If we can't remove it, we'll try to clear the tables instead
            conn = sqlite3.connect(test_db)
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = cursor.fetchall()
            for table in tables:
                if table[0] != 'sqlite_sequence':
                    cursor.execute(f"DELETE FROM {table[0]};")
            conn.commit()
            conn.close()

    init_db()
    seed_tractates()
    seed_sms_templates()
    
    # Ensure simulation mode
    set_live_mode(False)
    
    # Clear USER_STATES
    USER_STATES.clear()
    
    yield
    
    # Cleanup - don't delete if we want to reuse it due to lock, 
    # but the setup will clear it anyway
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
