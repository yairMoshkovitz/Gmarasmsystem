
import os
from database import get_conn
from simulation_system import handle_unregistered_user, handle_registered_user, USER_STATES
from sms_service import send_sms

def test_final_flow():
    test_phone = "0508888888"
    
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
    
    print(f"--- Testing Final Flow for {test_phone} ---")
    
    # Step 1: Personal Details
    print(f"\nStep 1: Registering user (Personal Details)...")
    handle_unregistered_user(test_phone, "אברהם, אבינו, חברון, 99")
    
    conn = get_conn()
    user = conn.execute("SELECT * FROM users WHERE phone=?", (test_phone,)).fetchone()
    conn.close()
    
    # Step 2: Tractate Details
    print(f"\nStep 2: Sending tractate details...")
    handle_registered_user(test_phone, user, "ברכות, ב ע\"א עד י ע\"ב, 1, 10")
    
    # Step 3: Trigger Questions
    print("\nStep 3: Requesting daily questions (sending '1')...")
    handle_registered_user(test_phone, user, "1")
    
    # Step 4: Answer questions (Should stop after 2)
    print("\nStep 4: Answering questions until daily limit...")
    for i in range(5):
        print(f"--- Answer {i+1} ---")
        handle_registered_user(test_phone, user, "כן")

if __name__ == "__main__":
    test_final_flow()
