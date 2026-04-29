
import os
from database import get_conn
from simulation_system import handle_unregistered_user, handle_registered_user, USER_STATES
from sms_service import send_sms

def test_two_step_registration():
    test_phone = "0509999999"
    
    # 1. Clear previous test data
    conn = get_conn()
    user = conn.execute("SELECT id FROM users WHERE phone=?", (test_phone,)).fetchone()
    if user:
        conn.execute("DELETE FROM sent_questions WHERE user_id=?", (user['id'],))
        conn.execute("DELETE FROM subscriptions WHERE user_id=?", (user['id'],))
        conn.execute("DELETE FROM users WHERE id=?", (user['id'],))
        conn.commit()
    conn.close()
    if test_phone in USER_STATES:
        del USER_STATES[test_phone]
    
    print(f"--- Testing Two-Step Registration Flow for {test_phone} ---")
    
    # Step 1: Personal Details
    # Format: שם, שם משפחה, עיר, גיל
    step1_msg = "מנחם, לוי, צפת, 28"
    print(f"\nStep 1: Sending personal details...")
    handle_unregistered_user(test_phone, step1_msg)
    
    # Verify user was created and state is correct
    conn = get_conn()
    user = conn.execute("SELECT * FROM users WHERE phone=?", (test_phone,)).fetchone()
    conn.close()
    
    if user:
        print(f"SUCCESS: User {user['name']} created.")
    else:
        print("FAILURE: User not created.")
        return

    # Step 2: Tractate Details
    # Format: מסכת, דף התחלה עד דף סיום, קצב, שעה
    step2_msg = "ברכות, ב ע\"א עד י ע\"ב, 1, 19"
    print(f"\nStep 2: Sending tractate details...")
    handle_registered_user(test_phone, user, step2_msg)
    
    # Verify subscription was created
    conn = get_conn()
    sub = conn.execute("SELECT * FROM subscriptions WHERE user_id=?", (user['id'],)).fetchone()
    conn.close()
    
    if sub:
        print(f"SUCCESS: Subscription created for user {user['id']}.")
    else:
        print("FAILURE: Subscription not created.")

if __name__ == "__main__":
    test_two_step_registration()
