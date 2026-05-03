import sqlite3
import os

DB_PATH = "gemara_sms.db"

def migrate_subscriptions():
    if not os.path.exists(DB_PATH):
        print("Database not found.")
        return

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    try:
        print("Starting migration of subscriptions table...")
        
        # 1. Create a new table without the UNIQUE constraint
        cur.execute("""
            CREATE TABLE subscriptions_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                tractate_id INTEGER NOT NULL,
                start_daf INTEGER NOT NULL DEFAULT 2,
                end_daf INTEGER NOT NULL,
                current_daf REAL NOT NULL DEFAULT 2.0,
                dafim_per_day REAL NOT NULL DEFAULT 1.0,
                send_hour INTEGER NOT NULL DEFAULT 8,
                is_active INTEGER DEFAULT 1,
                pause_until DATE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 2. Copy data from old table
        cur.execute("""
            INSERT INTO subscriptions_new (
                id, user_id, tractate_id, start_daf, end_daf, 
                current_daf, dafim_per_day, send_hour, is_active, 
                pause_until, created_at
            )
            SELECT 
                id, user_id, tractate_id, start_daf, end_daf, 
                current_daf, dafim_per_day, send_hour, is_active, 
                pause_until, created_at
            FROM subscriptions
        """)
        
        # 3. Drop old table
        cur.execute("DROP TABLE subscriptions")
        
        # 4. Rename new table to original name
        cur.execute("ALTER TABLE subscriptions_new RENAME TO subscriptions")
        
        conn.commit()
        print("Migration completed successfully.")
        
    except Exception as e:
        conn.rollback()
        print(f"Migration failed: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    migrate_subscriptions()
