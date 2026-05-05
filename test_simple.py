
import os
import json
from database import get_conn, init_db
from sms_service import get_sms_history
from simulation_system import handle_unregistered_user, handle_registered_user

def test_return_to_menu_logic():
    print("Starting Return to Menu (0) Test...")
    
    phone = "0501111111"
    
    # Clean up
    conn = get_conn()
    conn.execute("DELETE FROM users WHERE phone=?", (phone,))
    conn.execute("DELETE FROM sms_log WHERE phone=?", (phone,))
    conn.commit()
    conn.close()
    
    # 1. Unregistered -> Registration Step 1
    print("\n--- Step 1: Registration ---")
    handle_unregistered_user(phone, "ישראל, ישראלי, ירושלים, 30")
    
    conn = get_conn()
    user = conn.execute("SELECT * FROM users WHERE phone=?", (phone,)).fetchone()
    conn.close()
    
    # 2. Registration Step 2 -> Main Menu with "0"
    print("\n--- Step 2: Sending '0' to return to menu ---")
    handle_registered_user(phone, user, "0")
    
    conn = get_conn()
    # Get last outgoing message
    last_msgs = conn.execute("SELECT message FROM sms_log WHERE phone=? ORDER BY sent_at DESC LIMIT 5", (phone,)).fetchall()
    conn.close()
    
    for row in last_msgs:
        print(f"Checking log message: {row[0][:50]}...")

    if any("1." in row[0] and "2." in row[0] for row in last_msgs):
        print("SUCCESS: Main menu detected in log.")
    else:
        print("FAILURE: Main menu NOT detected.")
        if last_msg: print(f"Got: {last_msg[0][:100]}")

if __name__ == "__main__":
    test_return_to_menu_logic()
