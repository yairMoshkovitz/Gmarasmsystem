
import os
import json
import sqlite3
from database import get_conn

def test_return_to_menu_manual():
    print("Starting Manual Verification of Return to Menu (0)...")
    
    phone = "0501111111"
    
    # 1. Setup - Create user and put in state
    from simulation_system import USER_STATES, handle_registered_user
    from registration import register_user
    
    # Ensure clean state
    conn = get_conn()
    conn.execute("DELETE FROM users WHERE phone=?", (phone,))
    conn.execute("DELETE FROM sms_log WHERE phone=?", (phone,))
    conn.commit()
    conn.close()
    
    user_id = register_user(phone, "ישראל", "ישראלי", "ירושלים", 30)
    conn = get_conn()
    user = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    conn.close()
    
    # Set state
    USER_STATES[phone] = {"state": "AWAITING_UPDATE_DAF"}
    print(f"Current State before '0': {USER_STATES.get(phone)}")
    
    # 2. Trigger '0'
    print("Sending '0'...")
    handle_registered_user(phone, user, "0")
    
    # 3. Verify
    print(f"Current State after '0': {USER_STATES.get(phone)}")
    
    conn = get_conn()
    # Fetch last 3 messages to be sure we see the menu
    rows = conn.execute("SELECT message FROM sms_log WHERE phone=? ORDER BY sent_at DESC LIMIT 3", (phone,)).fetchall()
    conn.close()
    
    found_menu = False
    for row in rows:
        msg = row[0]
        # In the DB it is stored as Hebrew text.
        if "1." in msg and "2." in msg and "3." in msg:
            found_menu = True
            break
            
    if phone not in USER_STATES and found_menu:
        print("SUCCESS: State cleared and Main Menu sent to log.")
    else:
        print(f"FAILURE: Found menu: {found_menu}, State exists: {phone in USER_STATES}")

if __name__ == "__main__":
    test_return_to_menu_manual()
