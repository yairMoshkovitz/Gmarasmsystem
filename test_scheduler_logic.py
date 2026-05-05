
import os
from datetime import datetime, timedelta
from database import get_conn
from scheduler import run_hour, has_pending_question
from sms_service import set_live_mode, get_sms_history

def test_daily_send_logic():
    print("Testing Daily Send Logic (New day vs same day)...")
    set_live_mode(False) # Use simulation mode for testing
    
    phone = "0509999999"
    
    # 1. Setup - Create user and sub
    from registration import register_user, subscribe
    conn = get_conn()
    conn.execute("DELETE FROM users WHERE phone=?", (phone,))
    conn.commit()
    
    user_id = register_user(phone, "בודק", "בודק", "ירושלים", 30)
    # Get tractate 1
    t = conn.execute("SELECT id FROM tractates LIMIT 1").fetchone()
    sub_id = subscribe(user_id, t[0], 2.0, 10.0, 1.0, 10) # 10:00 AM
    conn.close()
    
    # 2. Simulate an old pending question (from yesterday)
    conn = get_conn()
    yesterday = (datetime.now() - timedelta(days=1)).isoformat()
    conn.execute(
        "INSERT INTO sent_questions (user_id, subscription_id, question_id, question_text, sent_at) VALUES (?, ?, ?, ?, ?)",
        (user_id, sub_id, "test_q", "שאלה מאתמול", yesterday)
    )
    conn.commit()
    conn.close()
    
    print(f"Has pending question (any time): {has_pending_question(user_id)}")
    print(f"Has pending question (today only): {has_pending_question(user_id, same_day_only=True)}")
    
    # 3. Try to run scheduler for today at 10:00
    print("Running scheduler for 10:00...")
    set_live_mode(True) # Temporarily set to True to bypass simulation check, but we won't really send
    # Mocking send_real_sms to avoid errors
    import sms_service
    original_send_real = sms_service.send_real_sms
    sms_service.send_real_sms = lambda p, m: print(f"Mock send to {p}: {m[:30]}...")
    
    run_hour(10)
    
    sms_service.send_real_sms = original_send_real
    set_live_mode(False)
    
    # 4. Verify - Should have sent a new question despite the old one
    history = get_sms_history(phone)
    # Looking for a message that isn't "שאלה מאתמול"
    found_new = False
    for msg in history:
        if "שאלה מאתמול" not in msg['message'] and "מסכת" in msg['message']:
            found_new = True
            print(f"Found new question: {msg['message'][:50]}...")
            break
            
    if found_new:
        print("SUCCESS: Sent new question despite pending question from yesterday.")
    else:
        print("FAILURE: Did not send new question.")

    # 5. Try to run again - should NOT send (same day protection)
    print("\n--- Running scheduler again for 10:00 (same day) ---")
    set_live_mode(True)
    import sms_service
    sms_service.send_real_sms = lambda p, m: print(f"Mock send to {p}: {m[:30]}...")
    
    # Count messages before
    history_before = len(get_sms_history(phone))
    
    run_hour(10)
    
    history_after = len(get_sms_history(phone))
    if history_after == history_before:
        print("SUCCESS: Did not send duplicate question on the same day.")
    else:
        print(f"FAILURE: Sent duplicate question. Before: {history_before}, After: {history_after}")
    set_live_mode(False)
    
if __name__ == "__main__":
    test_daily_send_logic()
