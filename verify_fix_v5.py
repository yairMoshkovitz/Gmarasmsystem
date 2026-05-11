
import os
from database import get_conn, init_db, seed_tractates, daf_to_float
from registration import register_user, subscribe
from simulation_system import handle_registered_user, USER_STATES
from sms_service import get_sms_history, set_live_mode
from scheduler import send_daily_questions
import datetime

def verify():
    # Setup
    if os.path.exists("test_sms.db"):
        os.remove("test_sms.db")
    os.environ["DATABASE_URL"] = "" # Use SQLite
    init_db()
    seed_tractates()
    set_live_mode(False) # don't send real SMS for test
    
    # We need to use a clean phone number because previous tests might have logged 30 messages today in a real DB
    # Actually we just deleted the DB so it should be fine, but let's use a unique one just in case
    phone = "0509999999"
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
    if history:
        print("Last SMS (Update 70a):", history[-1]['message'])
    
    # 2. Verify sub limit in main menu
    print("\n--- 2. Testing 5 subscription limit in Main Menu ---")
    conn = get_conn()
    t_names = ['שבת', 'עירובין', 'פסחים', 'יומא']
    t_ids = []
    for name in t_names:
        res = conn.execute("SELECT id FROM tractates WHERE name=?", (name,)).fetchone()
        if res: t_ids.append(res[0])
    conn.close()
    
    for t_id in t_ids:
        subscribe(user_id, t_id, 2.0, 10.0, 1.0, 18)
    print(f"User now has {len(t_ids) + 1} active subs.")
    
    # Simulating pressing '6' on main menu
    print("User presses '6' to add another subscription...")
    handle_registered_user(phone, user, "6")
    history = get_sms_history(phone)
    if history:
        print("Last SMS (Press 6):", history[-1]['message'])

    # 3. Verify question format
    print("\n--- 3. Testing question format ---")
    conn = get_conn()
    conn.execute("UPDATE subscriptions SET current_daf=2.0 WHERE id=1")
    conn.commit()
    sub = conn.execute("SELECT s.*, t.name as tractate_name FROM subscriptions s JOIN tractates t ON s.tractate_id = t.id WHERE s.id=1").fetchone()
    
    # Clear sent history for this user
    conn.execute("DELETE FROM sent_questions WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()
    
    send_daily_questions(dict(sub))
    history = get_sms_history(phone)
    if history:
        print("Last SMS (Question format):", history[-1]['message'])

    # 4. Verify hard limit of 30 SMS
    print("\n--- 4. Testing daily hard limit of 30 SMS ---")
    conn = get_conn()
    # Inject 29 out messages for today
    today_iso = datetime.datetime.now().isoformat()
    for i in range(29):
        conn.execute("INSERT INTO sms_log (user_id, phone, direction, message, sent_at) VALUES (?,?,?,?,?)",
                     (user_id, phone, 'out', f'spam {i}', today_iso))
    conn.commit()
    conn.close()
    
    # Send 30th message (should be allowed but triggers warning)
    handle_registered_user(phone, user, "something invalid")
    
    # Send 31st message (should be blocked)
    handle_registered_user(phone, user, "something else")
    
    history = get_sms_history(phone, limit=5)
    print("Recent SMS log:")
    for h in reversed(history):
        print(f"[{h['direction']}] {h['message'][:50]}")

if __name__ == "__main__":
    verify()
