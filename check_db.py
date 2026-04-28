import sqlite3
import os
from pathlib import Path

DB_PATH = Path("gemara_sms.db")

def check_db():
    if not DB_PATH.exists():
        print("Database file not found!")
        return
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    
    print("--- Tractates ---")
    rows = conn.execute("SELECT * FROM tractates").fetchall()
    for r in rows:
        print(dict(r))
    
    print("\n--- Users ---")
    rows = conn.execute("SELECT * FROM users").fetchall()
    for r in rows:
        print(dict(r))
        
    conn.close()

if __name__ == "__main__":
    check_db()
