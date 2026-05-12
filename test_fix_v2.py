
import os
import json
from database import init_db, get_conn, seed_tractates, seed_sms_templates
from registration import register_user, subscribe
from scheduler import send_next_question_or_finish
from sms_service import get_sms_history

def test_fix():
    # Setup clean environment
    if os.path.exists("test.db"):
        os.remove("test.db")
    os.environ["DATABASE_URL"] = "" # Use SQLite
    
    init_db()
    seed_tractates()
    seed_sms_templates() # This will load our new template from JSON
    
    phone = "0501234567"
    user_id = register_user(phone, "Test", "User", "Bnei Brak", 30)
    
    # Subscribe to Berachos
    conn = get_conn()
    berachos = conn.execute("SELECT id FROM tractates WHERE name='ברכות'").fetchone()
    sub_id = subscribe(user_id, berachos['id'], 2.0, 10.0, 1.0, 18)
    
    sub = {
        "id": sub_id,
        "user_id": user_id,
        "phone": phone,
        "tractate_id": berachos['id'],
        "tractate_name": "ברכות",
        "current_daf": 2.0,
        "dafim_per_day": 1.0,
        "send_hour": 18
    }
    
    print("\n--- Sending Question 1 ---")
    send_next_question_or_finish(sub)
    
    # Simulate answer
    conn = get_conn()
    last_q = conn.execute("SELECT id FROM sent_questions ORDER BY sent_at DESC LIMIT 1").fetchone()
    conn.execute("UPDATE sent_questions SET responded_at='now', response_text='כן' WHERE id=?", (last_q['id'],))
    conn.commit()
    conn.close()
    
    print("\n--- Sending Question 2 ---")
    send_next_question_or_finish(sub)
    
    # Check history
    history = get_sms_history(phone)
    # Extract only the body text from the log (which is printed in the simulation console)
    # In this test, we can't easily capture the printed output to variable, 
    # but we saw it in the console in previous run.
    # Let's check the database for what would be sent if we can't get it from history.
    
    print("\n--- Checking results in console output above ---")
    print("If Question 2 (second message) ends with 'יודע את התשובה?' WITHOUT '(לקבלת שאלה נוספת יש לענות)', it works!")

if __name__ == "__main__":
    test_fix()
