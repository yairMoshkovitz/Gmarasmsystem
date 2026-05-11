
import os
import json
from database import init_db, get_conn, seed_tractates, seed_sms_templates
from simulation_system import handle_unregistered_user, handle_registered_user, USER_STATES
from sms_service import get_sms_history

def verify_fix():
    # 1. Setup clean environment
    # Note: We don't remove DB because it might be locked, but we clear tables if possible
    init_db()
    seed_tractates()
    seed_sms_templates()
    
    phone_yair = "0501111111"
    phone_other = "0502222222"
    
    # Setup users
    conn = get_conn()
    conn.execute("INSERT OR IGNORE INTO users (phone, name) VALUES (?, ?)", (phone_yair, "יאיר"))
    conn.execute("INSERT OR IGNORE INTO users (phone, name) VALUES (?, ?)", (phone_other, "אחר"))
    user_yair = conn.execute("SELECT * FROM users WHERE phone=?", (phone_yair,)).fetchone()
    user_other = conn.execute("SELECT * FROM users WHERE phone=?", (phone_other,)).fetchone()
    
    # Create sub for Yair
    conn.execute("INSERT OR IGNORE INTO subscriptions (user_id, tractate_id, end_daf, is_active) VALUES (?, ?, ?, ?)",
                 (user_yair['id'], 1, 100, 1))
    sub_yair = conn.execute("SELECT * FROM subscriptions WHERE user_id=?", (user_yair['id'],)).fetchone()
    
    # Insert a pending question for Yair
    conn.execute("INSERT INTO sent_questions (user_id, subscription_id, question_id, question_text, daf_from) VALUES (?, ?, ?, ?, ?)",
                 (user_yair['id'], sub_yair['id'], "א", "שאלה ליאיר", "2.0"))
    conn.commit()
    conn.close()

    print("\n--- Testing Fix: Yair answers 'כן' while state might be messy ---")
    
    # Simulate Other user being in the middle of registration
    USER_STATES[phone_other] = {"state": "AWAITING_REG_STEP_2"}
    
    # Even if Yair somehow had a state (e.g. from previous failed attempt)
    USER_STATES[phone_yair] = {"state": "AWAITING_REG_STEP_2"}
    
    print(f"Yair's state before: {USER_STATES.get(phone_yair)}")
    
    # NEW LOGIC: Test with the correct state 'AWAITING_ANSWER'
    import simulation_system
    simulation_system.USER_STATES[phone_yair] = {"state": "AWAITING_ANSWER"}
    
    print(f"\n[Test 1] Yair sends invalid text 'ברכות'")
    simulation_system.handle_registered_user(phone_yair, user_yair, "ברכות")
    
    history = get_sms_history(phone_yair)
    latest_msg = history[0]['message']
    print(f"Bot response to Yair: {latest_msg}")
    
    if "כדי לענות על השאלה" in latest_msg:
        print("RESULT: Invalid answer handled correctly")
    elif "המסכת" in latest_msg and "לא נמצאה" in latest_msg:
        print("RESULT: FIX FAILED - Still getting 'tractate not found'")
    else:
        print(f"RESULT: UNKNOWN - {latest_msg}")

    print(f"Yair's state after invalid answer: {simulation_system.USER_STATES.get(phone_yair)}")
    
    print(f"\n[Test 2] Yair sends valid answer 'כן'")
    simulation_system.handle_registered_user(phone_yair, user_yair, "כן")
    history = get_sms_history(phone_yair)
    latest_msg = history[0]['message']
    print(f"Bot response to Yair: {latest_msg}")
    
    if "שאלה" in latest_msg or "סיימת" in latest_msg or "יפה" in latest_msg or "מצוין" in latest_msg:
        print("RESULT: FIX WORKING - Valid answer accepted")
    else:
        print(f"RESULT: UNKNOWN - {latest_msg}")

    print(f"Yair's state after valid answer: {simulation_system.USER_STATES.get(phone_yair)}")
    
    # Final check: Is the question marked as answered?
    conn = get_conn()
    q = conn.execute("SELECT * FROM sent_questions WHERE user_id=? AND response_text='כן'", (user_yair['id'],)).fetchone()
    conn.close()
    if q:
        print("CONFIRMED: Question in DB marked as answered.")
    else:
        print("ERROR: Question in DB NOT marked as answered.")

if __name__ == "__main__":
    verify_fix()
