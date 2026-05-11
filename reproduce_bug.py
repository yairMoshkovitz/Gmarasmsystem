
import os
import json
from database import init_db, get_conn, seed_tractates, seed_sms_templates
from simulation_system import handle_unregistered_user, handle_registered_user, USER_STATES
from sms_service import get_sms_history

def reproduce_bug():
    # 1. Setup clean environment
    # if os.path.exists("gemara_sms.db"):
    #     os.remove("gemara_sms.db")
    
    init_db()
    seed_tractates()
    seed_sms_templates()
    
    phone = "0501234567"
    
    # 2. Step 1: Register user
    print("\n--- Step 1: Registration ---")
    handle_unregistered_user(phone, "ישראל, ישראלי, ירושלים, 30")
    
    history = get_sms_history(phone)
    print(f"Bot response: {history[0]['message']}")
    
    # 3. Step 2: Subscribe to a tractate
    print("\n--- Step 2: Subscription ---")
    # Using the format that is common: "ברכות ב עד י 1 18"
    handle_unregistered_user(phone, "ברכות ב עד י 1 18")
    
    history = get_sms_history(phone)
    print(f"Bot response: {history[0]['message']}")
    
    # 4. Check if subscription was created
    conn = get_conn()
    user = conn.execute("SELECT * FROM users WHERE phone=?", (phone,)).fetchone()
    sub = conn.execute("SELECT * FROM subscriptions WHERE user_id=?", (user['id'],)).fetchone()
    conn.close()
    
    if sub:
        print(f"SUCCESS: Subscription created for tractate_id {sub['tractate_id']}")
    else:
        print("FAILURE: No subscription created.")

    # 5. Send a question manually and then answer it
    print("\n--- Step 3: Answering a question ---")
    # For this we need a question in the DB or just simulate the state
    conn = get_conn()
    conn.execute("INSERT INTO sent_questions (user_id, subscription_id, question_id, question_text, daf_from) VALUES (?, ?, ?, ?, ?)",
                 (user['id'], sub['id'] if sub else 1, "1", "שאלה כלשהי", "2.0"))
    conn.commit()
    conn.close()
    
    # Now send an answer
    # We simulate being in AWAITING_REG_STEP_2 state as well
    USER_STATES[phone] = {"state": "AWAITING_REG_STEP_2"}
    print(f"Current state before 'כן': {USER_STATES.get(phone)}")
    
    handle_registered_user(phone, user, "כן")
    
    history = get_sms_history(phone)
    print(f"Bot response after 'כן': {history[0]['message']}")
    
    # Check if state was cleared
    print(f"Current state after 'כן': {USER_STATES.get(phone)}")
    
    if "המסכת" in history[0]['message'] and "לא נמצאה" in history[0]['message']:
        print("BUG REPRODUCED: Bot said tractate not found when receiving an answer.")
    else:
        print("Bug not reproduced with 'כן'.")

if __name__ == "__main__":
    reproduce_bug()
