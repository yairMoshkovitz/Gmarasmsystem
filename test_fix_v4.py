
import os
import json
import sqlite3
from database import init_db, get_conn, seed_tractates, seed_sms_templates
from registration import register_user, subscribe
from scheduler import send_next_question_or_finish
from sms_service import get_sms_history

def test_fix():
    # Use existing test.db or fresh if you want
    db_file = "test_final.db"
    if os.path.exists(db_file):
        try:
            os.remove(db_file)
        except:
            pass
    
    os.environ["DATABASE_URL"] = "" 
    
    init_db()
    # We don't necessarily need to seed all tractates, just create one
    conn = get_conn()
    conn.execute("INSERT OR IGNORE INTO tractates (name, total_dafim) VALUES ('ברכות', 64)")
    berachos_id = conn.execute("SELECT id FROM tractates WHERE name='ברכות'").fetchone()[0]
    conn.commit()
    conn.close()
    
    seed_sms_templates()
    
    phone = "0501112222"
    user_id = register_user(phone, "Test", "User", "Bnei Brak", 30)
    
    # Subscribe
    sub_id = subscribe(user_id, berachos_id, 2.0, 10.0, 1.0, 18)
    
    # Get full sub info
    conn = get_conn()
    sub_row = conn.execute("SELECT s.*, t.name as tractate_name, u.phone, u.name as user_name FROM subscriptions s JOIN tractates t ON s.tractate_id = t.id JOIN users u ON s.user_id = u.id WHERE s.id=?", (sub_id,)).fetchone()
    sub = dict(sub_row)
    conn.close()
    
    print("\n--- Sending Question 1 ---")
    send_next_question_or_finish(sub)
    
    # Simulate answer
    conn = get_conn()
    last_q = conn.execute("SELECT id FROM sent_questions ORDER BY sent_at DESC LIMIT 1").fetchone()
    conn.execute("UPDATE sent_questions SET responded_at=CURRENT_TIMESTAMP, response_text='כן' WHERE id=?", (last_q[0],))
    conn.commit()
    conn.close()
    
    print("\n--- Sending Question 2 ---")
    send_next_question_or_finish(sub)

if __name__ == "__main__":
    test_fix()
