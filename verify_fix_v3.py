
import os
from database import get_conn, init_db, seed_tractates, daf_to_float
from registration import register_user, subscribe
from simulation_system import handle_registered_user, USER_STATES
from sms_service import get_sms_history, set_live_mode
from scheduler import send_daily_questions

def verify():
    # Setup
    if os.path.exists("test_sms.db"):
        os.remove("test_sms.db")
    os.environ["DATABASE_URL"] = "" # Use SQLite
    init_db()
    seed_tractates()
    set_live_mode(True)
    
    phone = "0501234567"
    user_id = register_user(phone, "Test", "User")
    
    conn = get_conn()
    tractate = conn.execute("SELECT id FROM tractates WHERE name='ברכות'").fetchone()
    conn.close()
    
    # Subscribe Berachos (2a-10b)
    subscribe(user_id, tractate['id'], 2.0, 10.5, 1.0, 18)
    
    # 1. Verify range validation in update
    print("\n--- 1. Testing range validation during update ---")
    USER_STATES[phone] = {"state": "AWAITING_UPDATE_DAF", "sub_id": 1}
    user = {"id": user_id, "name": "Test", "phone": phone}
    handle_registered_user(phone, user, "ע ע\"א") # 70a, should fail
    
    history = get_sms_history(phone)
    print("Last SMS (Update 70a):", history[-1]['message'])
    
    # 3. Verify sub limit
    print("\n--- 3. Testing 5 subscription limit ---")
    conn = get_conn()
    # We already have 1 (Berachos)
    # Adding 4 more: שבת, עירובין, פסחים, יומא
    t_names = ['שבת', 'עירובין', 'פסחים', 'יומא']
    t_ids = []
    for name in t_names:
        res = conn.execute("SELECT id FROM tractates WHERE name=?", (name,)).fetchone()
        if res: t_ids.append(res[0])
    conn.close()
    
    try:
        for t_id in t_ids:
            subscribe(user_id, t_id, 2.0, 10.0, 1.0, 18)
        print("Total active subs:", len(t_ids) + 1)
        
        # Trying 6th one
        print("Adding 6th subscription...")
        subscribe(user_id, 1, 10.5, 20.0, 1.0, 18) # Different range to not trigger update
    except Exception as e:
        print("Caught expected limit error:", e)

    # 4. Verify question format
    print("\n--- 4. Testing question format ---")
    conn = get_conn()
    # Reset Berachos to a page with questions (e.g., 2a)
    conn.execute("UPDATE subscriptions SET current_daf=2.0 WHERE id=1")
    conn.commit()
    sub = conn.execute("SELECT s.*, t.name as tractate_name FROM subscriptions s JOIN tractates t ON s.tractate_id = t.id WHERE s.id=1").fetchone()
    
    # Clear sent history for this user
    conn.execute("DELETE FROM sent_questions WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()
    
    send_daily_questions(dict(sub))
    history = get_sms_history(phone)
    print("Last SMS (Question format):", history[-1]['message'])

    # 2. Verify "no questions found" message
    print("\n--- 2. Testing 'no questions found' message ---")
    # Set current_daf to 10a (where there are no questions in Berachos usually)
    conn = get_conn()
    conn.execute("UPDATE subscriptions SET current_daf=10.0 WHERE id=1")
    conn.commit()
    sub = conn.execute("SELECT s.*, t.name as tractate_name FROM subscriptions s JOIN tractates t ON s.tractate_id = t.id WHERE s.id=1").fetchone()
    
    # Delete sent history again
    conn.execute("DELETE FROM sent_questions WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()
    
    send_daily_questions(dict(sub))
    
    history = get_sms_history(phone)
    print("Last SMS (No questions):", history[-1]['message'])

if __name__ == "__main__":
    verify()
