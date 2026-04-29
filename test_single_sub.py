
import os
from database import get_conn
from simulation_system import handle_unregistered_user, handle_registered_user
from sms_service import send_sms

def test_single_sub_flow():
    test_phone = "0500000000"
    
    # 1. Clear previous test data for this phone if exists
    conn = get_conn()
    user = conn.execute("SELECT id FROM users WHERE phone=?", (test_phone,)).fetchone()
    if user:
        conn.execute("DELETE FROM sent_questions WHERE user_id=?", (user['id'],))
        conn.execute("DELETE FROM subscriptions WHERE user_id=?", (user['id'],))
        conn.execute("DELETE FROM users WHERE id=?", (user['id'],))
        conn.commit()
    conn.close()
    
    print(f"--- Testing Single Subscription Flow for {test_phone} ---")
    
    # 2. Register user with one tractate (Berachos)
    # Format: הרשמה, שם, שם משפחה, עיר, גיל, מסכת, דף התחלה עד דף סיום, קצב, שעה
    registration_msg = "הרשמה, ישראל, ישראלי, ירושלים, 30, ברכות, ב ע\"א עד ה ע\"ב, 1, 10"
    print(f"\nStep 1: Registering user...")
    handle_unregistered_user(test_phone, registration_msg)
    
    conn = get_conn()
    user = conn.execute("SELECT * FROM users WHERE phone=?", (test_phone,)).fetchone()
    conn.close()
    
    # 3. Trigger questions
    print("\nStep 2: Requesting daily questions (sending '1')...")
    handle_registered_user(test_phone, user, "1")
    
    # 4. Answer questions until completion
    print("\nStep 3: Answering questions...")
    for i in range(5):
        print(f"--- Answer {i+1} ---")
        handle_registered_user(test_phone, user, "כן")

if __name__ == "__main__":
    test_single_sub_flow()
