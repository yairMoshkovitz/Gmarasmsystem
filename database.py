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


class PostgresRow:
    def __init__(self, colnames, values):
        self.data = dict(zip(colnames, values))
        self.values = values

    def __getitem__(self, key):
        if isinstance(key, int):
            return self.values[key]
        return self.data[key]

    def keys(self):
        return self.data.keys()

    def items(self):
        return self.data.items()

    def __iter__(self):
        return iter(self.values)

    def __len__(self):
        return len(self.values)
    
    def __repr__(self):
        return repr(self.data)


class PostgresCursorWrapper:
    def __init__(self, cursor):
        self.cursor = cursor

    def fetchone(self):
        row = self.cursor.fetchone()
        if row:
            colnames = [desc[0] for desc in self.cursor.description]
            return PostgresRow(colnames, row)
        return None

    def fetchall(self):
        rows = self.cursor.fetchall()
        if not rows:
            return []
        colnames = [desc[0] for desc in self.cursor.description]
        return [PostgresRow(colnames, row) for row in rows]

    def __iter__(self):
        rows = self.fetchall()
        return iter(rows)


class PostgresConnWrapper:
    def __init__(self, conn, pool=None):
        self.conn = conn
        self.pool = pool

    def execute(self, query, params=None):
        stripped_query = query.strip().upper()
        if "LAST_INSERT_ROWID()" in stripped_query:
            cur = self.conn.cursor()
            if "users" in self._last_table:
                 cur.execute(f"SELECT id FROM {self._last_table} ORDER BY id DESC LIMIT 1")
            elif "subscriptions" in self._last_table:
                 cur.execute(f"SELECT id FROM {self._last_table} ORDER BY id DESC LIMIT 1")
            return PostgresCursorWrapper(cur)

        query = query.replace('?', '%s')
        
        if "INSERT INTO" in stripped_query:
            match = re.search(r"INSERT INTO (\w+)", query, re.IGNORECASE)
            if match:
                self._last_table = match.group(1).lower()

        if "INSERT OR REPLACE" in stripped_query:
            query = query.replace("INSERT OR REPLACE", "INSERT")
            if "tractates" in query:
                query += " ON CONFLICT (name) DO UPDATE SET json_path = EXCLUDED.json_path, total_dafim = EXCLUDED.total_dafim"
            elif "users" in query:
                query += " ON CONFLICT (phone) DO UPDATE SET name = EXCLUDED.name"
            elif "settings" in query:
                query += " ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = EXCLUDED.updated_at"
            elif "sms_templates" in query:
                query += " ON CONFLICT (key) DO NOTHING"

        if "INSERT OR IGNORE" in stripped_query:
            query = query.replace("INSERT OR IGNORE", "INSERT")
            if "tractates" in query:
                query += " ON CONFLICT (name) DO NOTHING"
            elif "users" in query:
                query += " ON CONFLICT (phone) DO NOTHING"
            elif "sms_templates" in query:
                query += " ON CONFLICT (key) DO NOTHING"
            elif "settings" in query:
                query += " ON CONFLICT (key) DO NOTHING"
        
        cur = self.conn.cursor()
        cur.execute(query, params)
        return PostgresCursorWrapper(cur)

    _last_table = ""

    def commit(self):
        self.conn.commit()

    def close(self):
        if self.pool:
            self.pool.putconn(self.conn)
        else:
            self.conn.close()

    def fetchone(self, cursor):
        if hasattr(cursor, 'fetchone'):
            return cursor.fetchone()
        return None

    def fetchall(self, cursor):
        if hasattr(cursor, 'fetchall'):
            return cursor.fetchall()
        return []


# Connection pool for PostgreSQL (thread-safe)
_pg_pool = None

def get_conn():
    global _pg_pool
    # If we are in test mode (SQLite), skip Postgres logic
    if DATABASE_URL and not str(DB_PATH).endswith("_test.db"):
        import psycopg2
        from psycopg2 import pool
        
        # Initialize pool on first use
        if _pg_pool is None:
            url = DATABASE_URL
            if url.startswith("postgres://"):
                url = url.replace("postgres://", "postgresql://", 1)
            
            try:
                _pg_pool = pool.ThreadedConnectionPool(
                    minconn=2,
                    maxconn=20,
                    dsn=url,
                    sslmode='require'
                )
            except Exception as e:
                print(f"Error creating connection pool: {e}")
                # Fallback to direct connection
                conn = psycopg2.connect(url, sslmode='require')
                return PostgresConnWrapper(conn)
        
        # Get connection from pool
        try:
            conn = _pg_pool.getconn()
            return PostgresConnWrapper(conn, _pg_pool)
        except Exception as e:
            print(f"Error getting connection from pool: {e}")
            # Fallback to direct connection
            url = DATABASE_URL
            if url.startswith("postgres://"):
                url = url.replace("postgres://", "postgresql://", 1)
            conn = psycopg2.connect(url, sslmode='require')
            return PostgresConnWrapper(conn)
    else:
        conn = sqlite3.connect(DB_PATH, timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn


def init_db():
    """Initialize the database schema."""
    conn = get_conn()
    is_postgres = bool(os.environ.get("DATABASE_URL")) and not str(DB_PATH).endswith("_test.db")
    
    # Check if we need to migrate existing tables
    try:
        if is_postgres:
            cur = conn.conn.cursor()
            cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='users' AND column_name='last_name'")
            if not cur.fetchone():
                print("Migrating users table (Postgres)...")
                cur.execute("ALTER TABLE users ADD COLUMN last_name TEXT, ADD COLUMN city TEXT, ADD COLUMN age INTEGER")
            
            cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='subscriptions' AND column_name='pause_until'")
            if not cur.fetchone():
                print("Migrating subscriptions table (Postgres)...")
                cur.execute("ALTER TABLE subscriptions ADD COLUMN pause_until DATE")
            
            cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='subscriptions' AND column_name='question_type'")
            if not cur.fetchone():
                print("Migrating subscriptions table (Postgres) - adding question_type...")
                cur.execute("ALTER TABLE subscriptions ADD COLUMN question_type TEXT DEFAULT 'all'")

            cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='questions' AND column_name='question_type'")
            if not cur.fetchone():
                print("Migrating questions table (Postgres) - adding question_type...")
                cur.execute("ALTER TABLE questions ADD COLUMN question_type TEXT")

            # Remove UNIQUE constraint in Postgres
            try:
                cur.execute("ALTER TABLE subscriptions DROP CONSTRAINT IF EXISTS subscriptions_user_id_tractate_id_key")
            except Exception as e:
                print(f"Postgres constraint removal notice: {e}")

            conn.conn.commit()
            cur.close()
        else:
            cur = conn.cursor()
            # SQLite migration
            cur.execute("PRAGMA table_info(users)")
            cols = [row[1] for row in cur.fetchall()]
            if 'last_name' not in cols:
                print("Migrating users table (SQLite)...")
                conn.execute("ALTER TABLE users ADD COLUMN last_name TEXT")
                conn.execute("ALTER TABLE users ADD COLUMN city TEXT")
                conn.execute("ALTER TABLE users ADD COLUMN age INTEGER")
            
            cur.execute("PRAGMA table_info(subscriptions)")
            cols = [row[1] for row in cur.fetchall()]
            if 'pause_until' not in cols:
                print("Migrating subscriptions table (SQLite)...")
                conn.execute("ALTER TABLE subscriptions ADD COLUMN pause_until DATE")

            cur.execute("PRAGMA table_info(questions)")
            cols = [row[1] for row in cur.fetchall()]
            if 'question_type' not in cols:
                print("Migrating questions table (SQLite) - adding question_type...")
                conn.execute("ALTER TABLE questions ADD COLUMN question_type TEXT")
            
            cur.execute("PRAGMA table_info(subscriptions)")
            cols = [row[1] for row in cur.fetchall()]
            if 'question_type' not in cols:
                print("Migrating subscriptions table (SQLite) - adding question_type...")
                conn.execute("ALTER TABLE subscriptions ADD COLUMN question_type TEXT DEFAULT 'all'")

            # Check for UNIQUE constraint in SQLite (Multi-tractate migration)
            # AND ALSO check for INTEGER vs REAL for end_daf
            cur.execute("PRAGMA table_info(subscriptions)")
            table_info = cur.fetchall()
            end_daf_type = next((col[2] for col in table_info if col[1] == 'end_daf'), 'INTEGER')
            
            cur.execute("PRAGMA index_list(subscriptions)")
            indexes = cur.fetchall()
            has_unique = any(idx[1].startswith('sqlite_autoindex_subscriptions') or idx[2] == 1 for idx in indexes)
            
            if has_unique or end_daf_type.upper() == 'INTEGER':
                print(f"Migrating subscriptions table (SQLite). Unique: {has_unique}, EndDafType: {end_daf_type}")
                cur.execute("CREATE TABLE subscriptions_new (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL REFERENCES users(id), tractate_id INTEGER NOT NULL REFERENCES tractates(id), start_daf REAL NOT NULL DEFAULT 2, end_daf REAL NOT NULL, current_daf REAL NOT NULL DEFAULT 2.0, dafim_per_day REAL NOT NULL DEFAULT 1.0, send_hour INTEGER NOT NULL DEFAULT 8, is_active INTEGER DEFAULT 1, pause_until DATE, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
                cur.execute("INSERT INTO subscriptions_new (id, user_id, tractate_id, start_daf, end_daf, current_daf, dafim_per_day, send_hour, is_active, pause_until, created_at) SELECT id, user_id, tractate_id, CAST(start_daf AS REAL), CAST(end_daf AS REAL), current_daf, dafim_per_day, send_hour, is_active, pause_until, created_at FROM subscriptions")
                cur.execute("DROP TABLE subscriptions")
                cur.execute("ALTER TABLE subscriptions_new RENAME TO subscriptions")
            
            conn.commit()
    except Exception as e:
        print(f"Migration notice: {e}")

    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        schema = f.read()

    if is_postgres:
        schema = schema.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
        schema = schema.replace("REAL", "DOUBLE PRECISION")
        
        raw_conn = conn.conn
        # Drop sms_history if it exists and create sms_log (migration)
        try:
            cur = raw_conn.cursor()
            cur.execute("SELECT 1 FROM information_schema.tables WHERE table_name='sms_history'")
            if cur.fetchone():
                print("Migrating sms_history to sms_log...")
                cur.execute("CREATE TABLE IF NOT EXISTS sms_log (id SERIAL PRIMARY KEY, user_id INTEGER, phone TEXT NOT NULL, direction TEXT NOT NULL, message TEXT NOT NULL, sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
                cur.execute("INSERT INTO sms_log (user_id, phone, direction, message, sent_at) SELECT user_id, phone, direction, message, sent_at FROM sms_history")
                cur.execute("DROP TABLE sms_history")
                raw_conn.commit()
            cur.close()
        except Exception as e:
            print(f"Postgres migration error: {e}")
            raw_conn.rollback()

        for statement in schema.split(';'):
            clean_statement = []
            for line in statement.split('\n'):
                if not line.strip().startswith('--'):
                    clean_statement.append(line)
            
            stmt = '\n'.join(clean_statement).strip()
            if stmt:
                try:
                    cur = raw_conn.cursor()
                    cur.execute(stmt)
                    raw_conn.commit()
                    cur.close()
                except Exception as e:
                    # Check if it's just "already exists" which is fine with IF NOT EXISTS but Postgres might still complain
                    # or if the transaction is aborted
                    raw_conn.rollback()
                    # print(f"Postgres init notice: {e}")
    else:
        conn.executescript(schema)
        conn.commit()
    conn.close()
    try:
        print("✅ Database initialized and migrated.")
    except UnicodeEncodeError:
        print("Database initialized and migrated.")


def int_to_gimatriya(n):
    """Convert integer to Hebrew gimatriya string."""
    if n <= 0: return ""
    units = ["", "א", "ב", "ג", "ד", "ה", "ו", "ז", "ח", "ט"]
    tens = ["", "י", "כ", "ל", "מ", "נ", "ס", "ע", "פ", "צ"]
    hundreds = ["", "ק", "ר", "ש", "ת"]
    
    if n == 15: return "טו"
    if n == 16: return "טז"
    
    res = ""
    h = n // 100
    while h > 4:
        res += "ת"
        h -= 4
    res += hundreds[h]
    
    rem = n % 100
    if rem == 15: res += "טו"
    elif rem == 16: res += "טז"
    else:
        res += tens[rem // 10]
        res += units[rem % 10]
    return res


def gimatriya_to_int(s):
    """Convert Hebrew gimatriya string to integer."""
    hebrew_to_num = {
        "א": 1, "ב": 2, "ג": 3, "ד": 4, "ה": 5, "ו": 6, "ז": 7, "ח": 8, "ט": 9, "י": 10,
        "כ": 20, "ל": 30, "מ": 40, "נ": 50, "ס": 60, "ע": 70, "פ": 80, "צ": 90, "ק": 100,
        "ר": 200, "ש": 300, "ת": 400
    }
    s = s.replace("'", "").replace('"', "").replace(" ", "")
    total = 0
    for char in s:
        total += hebrew_to_num.get(char, 0)
    return total


def extract_daf_number(val):
    if val is None: return 2
    if isinstance(val, (int, float)): return int(val)
    if isinstance(val, str):
        s = val.strip().replace("'", "").replace('"', "")
        if s.isdigit(): return int(s)
        # Try gimatriya
        num = gimatriya_to_int(s)
        if num > 0: return num
        # Fallback to digit search
        match = re.search(r'(\d+)', val)
        if match: return int(match.group(1))
    return 2


def seed_questions():
    """Trigger the smart migration from JSON to DB questions table."""
    try:
        from migrate_questions import migrate
        print("🚀 Starting automated questions migration...")
        migrate()
    except Exception as e:
        print(f"❌ Automated migration failed: {e}")

def seed_sms_templates():
    """Seed SMS templates from JSON to DB if they don't exist."""
    template_path = Path(__file__).parent / "sms_templates.json"
    if not template_path.exists():
        return
    
    try:
        with open(template_path, "r", encoding="utf-8") as f:
            templates = json.load(f)
    except:
        return

    conn = get_conn()
    is_postgres = bool(os.environ.get("DATABASE_URL")) and not str(DB_PATH).endswith("_test.db")
    
    for key, content in templates.items():
        if is_postgres:
            conn.execute("""
                INSERT INTO sms_templates (key, content) VALUES (%s, %s)
                ON CONFLICT (key) DO NOTHING
            """, (key, content))
        else:
            conn.execute("INSERT OR IGNORE INTO sms_templates (key, content) VALUES (?, ?)", (key, content))
    
    conn.commit()
    conn.close()


def seed_tractates():
    """Register tractates from JSON files in data/ directory."""
    conn = get_conn()
    is_postgres = bool(os.environ.get("DATABASE_URL")) and not str(DB_PATH).endswith("_test.db")
    
    # Check multiple locations for JSON files
    search_paths = [DATA_DIR, Path(__file__).parent]
    json_files = []
    for p in search_paths:
        if p.exists():
            json_files.extend(list(p.glob("*.json")))

    seen_names = set()
    for json_file in json_files:
        # Skip system and backup files
        if json_file.name in ("package.json", "tsconfig.json", "package-lock.json", "sms_templates.json") or "backup" in json_file.name.lower():
            continue
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except: continue
        if not isinstance(data, dict) or "questions" not in data: continue
        tractate_name = json_file.stem.strip()
        if tractate_name in seen_names: continue
        seen_names.add(tractate_name)
        max_daf = 2
        for q in data.get("questions", []):
            daf_info = q.get("daf")
            if not daf_info: continue
            if isinstance(daf_info, dict):
                to_info = daf_info.get("to") or daf_info
                if isinstance(to_info, dict):
                    max_daf = max(max_daf, extract_daf_number(to_info.get("daf")))
            else:
                max_daf = max(max_daf, extract_daf_number(daf_info))
        
        # Use UPSERT logic to keep the same ID if the name exists
        if is_postgres:
            conn.execute("""
                INSERT INTO tractates (name, json_path, total_dafim) VALUES (%s, %s, %s)
                ON CONFLICT (name) DO UPDATE SET json_path = EXCLUDED.json_path, total_dafim = EXCLUDED.total_dafim
            """, (tractate_name, str(json_file), max_daf))
        else:
            # For SQLite, check if exists
            existing = conn.execute("SELECT id FROM tractates WHERE name = ?", (tractate_name,)).fetchone()
            if existing:
                conn.execute("UPDATE tractates SET json_path = ?, total_dafim = ? WHERE id = ?",
                             (str(json_file), max_daf, existing[0]))
            else:
                conn.execute("INSERT INTO tractates (name, json_path, total_dafim) VALUES (?, ?, ?)",
                             (tractate_name, str(json_file), max_daf))
    conn.commit()
    conn.close()


def load_questions(tractate_id: int) -> list:
    conn = get_conn()
    row = conn.execute("SELECT json_path FROM tractates WHERE id = ?", (tractate_id,)).fetchone()
    conn.close()
    if not row: return []
    with open(row["json_path"], "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("questions", [])


def daf_to_float(daf_input: str | int, amud: str | None = None) -> float:
    """Convert daf + amud to float. Handles gimatriya and numeric."""
    if isinstance(daf_input, str):
        if 'ע"א' in daf_input:
            amud = "א"
            daf_input = daf_input.replace('ע"א', "").strip()
        elif 'ע"ב' in daf_input:
            amud = "ב"
            daf_input = daf_input.replace('ע"ב', "").strip()
        d = float(extract_daf_number(daf_input))
    else:
        d = float(daf_input)

    if amud in ("ב", "b", "B", "2", 'ע"ב'):
        return d + 0.5
    return d


def float_to_daf_str(val: float) -> str:
    """Convert float position back to human-readable daf string (e.g., ב ע"א)."""
    daf_int = int(val)
    daf_str = int_to_gimatriya(daf_int)
    amud = 'ע"ב' if (val - daf_int) >= 0.5 else 'ע"א'
    return f"{daf_str} {amud}"


def get_setting(key: str, default=None):
    """Retrieve a setting from the database."""
    conn = get_conn()
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    conn.close()
    if row:
        return row["value"]
    return default


def set_setting(key: str, value: str):
    """Save a setting to the database."""
    conn = get_conn()
    is_postgres = bool(os.environ.get("DATABASE_URL")) and not str(DB_PATH).endswith("_test.db")
    if is_postgres:
        conn.execute("""
            INSERT INTO settings (key, value, updated_at) VALUES (%s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = EXCLUDED.updated_at
        """, (key, str(value)))
    else:
        conn.execute("INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)", (key, str(value)))
    conn.commit()
    conn.close()


if __name__ == "__main__":
    init_db()
    seed_tractates()
    seed_sms_templates()
    seed_questions()
