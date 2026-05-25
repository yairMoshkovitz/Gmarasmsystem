import os
import sqlite3
from database import get_conn, float_to_daf_str
from scheduler import format_sub_status, finish_subscription_day
from simulation_system import USER_STATES
import json

def setup_test_db():
    conn = get_conn()
    conn.execute("DELETE FROM sent_questions")
    conn.execute("DELETE FROM subscriptions")
    conn.execute("DELETE FROM users")
    conn.execute("DELETE FROM tractates")
    
    conn.execute("INSERT INTO tractates (id, name, json_path) VALUES (1, 'ברכות', 'ברכות.json')")
    conn.execute("INSERT INTO users (id, phone, name) VALUES (1, '051111117', 'משה')")
    
    # Register like in the example: ברכות ב ע"א עד יד ע"ב (2.0 to 14.5)
    # 8.0 pages per day
    conn.execute("""
        INSERT INTO subscriptions (id, user_id, tractate_id, start_daf, end_daf, current_daf, dafim_per_day, send_hour, is_active)
        VALUES (1, 1, 1, 2.0, 14.5, 2.0, 8.0, 8, 1)
    """)
    conn.commit()
    conn.close()

def reproduce():
    setup_test_db()
    
    conn = get_conn()
    sub = conn.execute("SELECT s.*, t.name as tractate_name, u.phone FROM subscriptions s JOIN tractates t ON s.tractate_id = t.id JOIN users u ON s.user_id = u.id WHERE s.id=1").fetchone()
    sub = dict(sub)
    conn.close()
    
    print("\n--- Testing format_sub_status ---")
    status = format_sub_status(sub)
    print(f"Status output:\n{status}")
    
    # Expected: should say today was B to I and tomorrow is ...
    # Current: says tomorrow is B to I
    
if __name__ == "__main__":
    reproduce()
