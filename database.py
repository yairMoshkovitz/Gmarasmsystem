"""
database.py - Database initialization and core models
"""
import sqlite3
import json
import os
import re
from pathlib import Path
from datetime import datetime
import dj_database_url

DB_PATH = Path(__file__).parent / "gemara_sms.db"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"
DATA_DIR = Path(__file__).parent / "data"
DATABASE_URL = os.environ.get("DATABASE_URL")


class PostgresConnWrapper:
    def __init__(self, conn):
        self.conn = conn

    def execute(self, query, params=None):
        # Handle last_insert_rowid()
        if "last_insert_rowid()" in query:
            # We assume it's called right after an insert.
            # In Postgres, we should have used RETURNING id, but to keep it simple
            # we'll try to find the last val. This is NOT thread-safe but ok for this scale.
            # Better: the caller should be updated, but let's try to shim it.
            cur = self.conn.cursor()
            # This is a hacky shim for the specific uses in the code
            if "users" in self._last_table:
                 cur.execute(f"SELECT id FROM {self._last_table} ORDER BY id DESC LIMIT 1")
            elif "subscriptions" in self._last_table:
                 cur.execute(f"SELECT id FROM {self._last_table} ORDER BY id DESC LIMIT 1")
            return cur

        # Convert SQLite '?' to Postgres '%s'
        query = query.replace('?', '%s')
        
        # Track last table for last_insert_rowid shim
        if "INSERT INTO" in query.upper():
            match = re.search(r"INSERT INTO (\w+)", query, re.IGNORECASE)
            if match:
                self._last_table = match.group(1)

        # Convert INSERT OR REPLACE to INSERT ... ON CONFLICT
        if "INSERT OR REPLACE" in query.upper():
            query = query.replace("INSERT OR REPLACE", "INSERT")
            if "tractates" in query:
                query += " ON CONFLICT (name) DO UPDATE SET json_path = EXCLUDED.json_path, total_dafim = EXCLUDED.total_dafim"
            elif "users" in query:
                query += " ON CONFLICT (phone) DO UPDATE SET name = EXCLUDED.name"
        
        cur = self.conn.cursor()
        cur.execute(query, params)
        return cur

    _last_table = ""

    def commit(self):
        self.conn.commit()

    def close(self):
        self.conn.close()

    def fetchone(self, cursor):
        row = cursor.fetchone()
        if row:
            # Convert tuple to dict-like for compatibility with sqlite3.Row
            colnames = [desc[0] for desc in cursor.description]
            return dict(zip(colnames, row))
        return None


def get_conn():
    if DATABASE_URL:
        import psycopg2
        conn = psycopg2.connect(DATABASE_URL, sslmode='require')
        return PostgresConnWrapper(conn)
    else:
        conn = sqlite3.connect(DB_PATH, timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn


def init_db():
    """Initialize the database schema."""
    conn = get_conn()
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        schema = f.read()

    if DATABASE_URL:
        # Convert SQLite schema to Postgres compatible
        schema = schema.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
        schema = schema.replace("REAL", "DOUBLE PRECISION")
        
        # Postgres doesn't like executescript, we use the cursor
        raw_conn = conn.conn
        cur = raw_conn.cursor()
        # Basic split by semicolon
        for statement in schema.split(';'):
            if statement.strip():
                cur.execute(statement)
        raw_conn.commit()
        cur.close()
    else:
        conn.executescript(schema)
        conn.commit()
    conn.close()
    try:
        print("✅ Database initialized.")
    except UnicodeEncodeError:
        print("Database initialized.")

def extract_daf_number(val):
    if val is None:
        return 2
    if isinstance(val, (int, float)):
        return int(val)
    if isinstance(val, str):
        # Handle Hebrew letters (basic mapping)
        hebrew_to_num = {
            "א": 1, "ב": 2, "ג": 3, "ד": 4, "ה": 5, "ו": 6, "ז": 7, "ח": 8, "ט": 9, "י": 10,
            "כ": 20, "ל": 30, "מ": 40, "נ": 50, "ס": 60, "ע": 70, "פ": 80, "צ": 90, "ק": 100,
            "ר": 200, "ש": 300, "ת": 400
        }
        
        # Check if it's a Hebrew representation
        clean_val = val.strip().replace("'", "").replace('"', "")
        if all(c in hebrew_to_num or c.isspace() for c in clean_val) and clean_val:
            total = 0
            for char in clean_val:
                total += hebrew_to_num.get(char, 0)
            if total > 0:
                return total

        # Extract digits from string like "דף 63" or "ב: 9"
        match = re.search(r'(\d+)', val)
        if match:
            return int(match.group(1))
    return 2


def seed_tractates():
    """Register tractates from JSON files in data/ directory."""
    conn = get_conn()
    if not DATA_DIR.exists():
        DATA_DIR.mkdir(parents=True)
        try:
            print(f"📁 Created data directory: {DATA_DIR}")
        except UnicodeEncodeError:
            print(f"Created data directory: {DATA_DIR}")

    registered = 0
    # Also check the root directory for .json files that are tractates
    json_files = list(DATA_DIR.glob("*.json")) + list(Path(__file__).parent.glob("*.json"))
    
    seen_names = set()
    for json_file in json_files:
        if json_file.name in ("package.json", "tsconfig.json", "package-lock.json"):
            continue
        
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        
        if not isinstance(data, dict) or "questions" not in data:
            continue

        tractate_name = json_file.stem
        if tractate_name in seen_names:
            continue
        seen_names.add(tractate_name)

        # Calculate total dafim from questions
        questions = data.get("questions", [])
        max_daf = 2
        for q in questions:
            daf_info = q.get("daf")
            if not daf_info:
                continue
                
            if isinstance(daf_info, dict):
                to_info = daf_info.get("to") or daf_info
                if isinstance(to_info, dict):
                    d = extract_daf_number(to_info.get("daf"))
                    max_daf = max(max_daf, d)
            elif isinstance(daf_info, str):
                d = extract_daf_number(daf_info)
                max_daf = max(max_daf, d)

        conn.execute(
            """
            INSERT OR REPLACE INTO tractates (name, json_path, total_dafim)
            VALUES (?, ?, ?)
            """,
            (tractate_name, str(json_file), max_daf),
        )
        registered += 1
        try:
            print(f"  📖 Registered tractate '{tractate_name}' (max daf: {max_daf})")
        except UnicodeEncodeError:
            print(f"  Registered tractate '{tractate_name}' (max daf: {max_daf})")

    conn.commit()
    conn.close()
    try:
        print(f"✅ Seeded {registered} tractate(s).")
    except UnicodeEncodeError:
        print(f"Seeded {registered} tractate(s).")


def load_questions(tractate_id: int) -> list:
    """Load all questions for a tractate."""
    conn = get_conn()
    row = conn.execute(
        "SELECT json_path FROM tractates WHERE id = ?", (tractate_id,)
    ).fetchone()
    conn.close()

    if not row:
        return []

    with open(row["json_path"], "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("questions", [])


def daf_to_float(daf: str | int, amud: str | None) -> float:
    """Convert daf + amud to float. 2a=2.0, 2b=2.5, 3a=3.0 ..."""
    d = float(extract_daf_number(daf))

    if amud in ("ב", "b", "B", "2"):
        return d + 0.5
    return d


def float_to_daf_str(val: float) -> str:
    """Convert float position back to human-readable daf string."""
    daf = int(val)
    amud = "ב" if (val - daf) >= 0.5 else "א"
    return f"דף {daf} עמוד {amud}"


if __name__ == "__main__":
    init_db()
    seed_tractates()
