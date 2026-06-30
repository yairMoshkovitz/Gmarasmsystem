import os
import sqlite3
from database import get_conn, float_to_daf_str
from scheduler import format_sub_status
from simulation_system import handle_registered_user, USER_STATES
from sms_service import get_sms_history
import json

def setup_test_db():
    conn = get_conn()
    conn.execute("DELETE FROM sent_questions")
    conn.execute("DELETE FROM subscriptions")
    conn.execute("DELETE FROM users")
    conn.execute("DELETE FROM tractates")
    conn.execute("DELETE FROM sms_log")
    conn.execute("DELETE FROM user_states")
    
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

def verify():
    setup_test_db()
    
    conn = get_conn()
    sub = conn.execute("SELECT s.*, t.name as tractate_name, u.phone FROM subscriptions s JOIN tractates t ON s.tractate_id = t.id JOIN users u ON s.user_id = u.id WHERE s.id=1").fetchone()
    sub = dict(sub)
    user = conn.execute("SELECT * FROM users WHERE id=1").fetchone()
    user = dict(user)
    conn.close()
    
    print("\n--- 1. Testing format_sub_status (Next Study Calculation) ---")
    status = format_sub_status(sub)
    print(f"Status output:\n{status}")
    # Expected: Tomorrow should be (2.0 + 8.0) = 10.0 (יא ע"א) to (10.0 + 8.0 - 0.5) = 17.5 (יח ע"א) -> Wait, 14.5 is the limit.
    # Calculation for next_end: 10.0 + 8.0 - 0.5 = 17.5. Cap at 14.5.
    # So tomorrow: יא ע"א עד יד ע"ב.
    
    print("\n--- 2. Testing Update Daf Flow ---")
    phone = '051111117'
    # Step 1: User asks to update daf
    handle_registered_user(phone, user, "2")
    history = get_sms_history(phone)
    print(f"Bot asked for daf:\n{history[-1]['message']}")
    
    # Step 2: User sends new daf (e.g., ד ע"א = 4.0)
    handle_registered_user(phone, user, "ד ע\"א")
    history = get_sms_history(phone)
    print(f"Bot confirmation:\n{history[-1]['message']}")
    
    # Check DB
    conn = get_conn()
    updated_sub = conn.execute("SELECT current_daf FROM subscriptions WHERE id=1").fetchone()
    print(f"Updated current_daf in DB: {updated_sub['current_daf']} (Expected 4.0)")
    conn.close()

if __name__ == "__main__":
    verify()
