
import os
import json
import sqlite3
from database import init_db, get_conn, seed_tractates, seed_sms_templates
from registration import register_user, subscribe
from scheduler import send_next_question_or_finish
from sms_service import get_sms_history

def test_fix():
    # Use a fresh DB for each test run to avoid "already sent" issues
    db_file = "test_fresh.db"
    if os.path.exists(db_file):
        os.remove(db_file)
    
    # Force use of this fresh SQLite DB
    os.environ["DATABASE_URL"] = "" 
    
    # Patch get_conn to use our fresh DB
    import database
    original_get_conn = database.get_conn
    database.get_conn = lambda: sqlite3.connect(db_file)
    
    try:
        init_db()
        seed_tractates()
        seed_sms_templates()
        
        phone = "0509999999"
        user_id = register_user(phone, "Test", "User", "Bnei Brak", 30)
        
        # Subscribe to Berachos
        conn = database.get_conn()
        berachos = conn.execute("SELECT id FROM tractates WHERE name='ברכות'").fetchone()
        sub_id = subscribe(user_id, berachos[0], 2.0, 10.0, 1.0, 18)
        
        # Get full sub info
        sub_row = conn.execute("SELECT s.*, t.name as tractate_name, u.phone, u.name as user_name FROM subscriptions s JOIN tractates t ON s.tractate_id = t.id JOIN users u ON s.user_id = u.id WHERE s.id=?", (sub_id,)).fetchone()
        sub = dict(zip([column[0] for column in conn.execute("SELECT s.*, t.name as tractate_name, u.phone, u.name as user_name FROM subscriptions s JOIN tractates t ON s.tractate_id = t.id JOIN users u ON s.user_id = u.id WHERE s.id=?", (sub_id,)).description], sub_row))
        conn.close()
        
        print("\n--- Sending Question 1 ---")
        send_next_question_or_finish(sub)
        
        # Simulate answer
        conn = database.get_conn()
        last_q = conn.execute("SELECT id FROM sent_questions ORDER BY sent_at DESC LIMIT 1").fetchone()
        conn.execute("UPDATE sent_questions SET responded_at='2026-05-12 21:00:00', response_text='כן' WHERE id=?", (last_q[0],))
        conn.commit()
        conn.close()
        
        print("\n--- Sending Question 2 ---")
        send_next_question_or_finish(sub)
        
    finally:
        database.get_conn = original_get_conn
        if os.path.exists(db_file):
            os.remove(db_file)

if __name__ == "__main__":
    test_fix()
