
import os
import json
from database import get_conn, init_db
from sms_service import get_sms_history
from simulation_system import handle_unregistered_user, handle_registered_user

def test_return_to_menu_logic():
    print("Starting Return to Menu (0) Test...")
    
    # 1. Test for Unregistered User in middle of registration
    phone = "0501111111"
    
    # Clean up if user exists
    conn = get_conn()
    conn.execute("DELETE FROM users WHERE phone=?", (phone,))
    conn.commit()
    conn.close()
    
    print("\n--- Testing Unregistered User ---")
    # Send partial registration
    handle_unregistered_user(phone, "ישראל, ישראלי, ירושלים, 30")
    
    history = get_sms_history(phone)
    print(f"Last message after step 1: {history[0]['message'][:50]}...")
    
    # Send "0" to reset
    # Wait, if user was created, we need to fetch it
    conn = get_conn()
    user = conn.execute("SELECT * FROM users WHERE phone=?", (phone,)).fetchone()
    conn.close()
    
    handle_registered_user(phone, user, "0")
    
    # After handle_registered_user(..., "0"), the last sent SMS should be the main menu
    # Let's check the absolute last message in history (outgoing)
    conn = get_conn()
    last_msg = conn.execute("SELECT message FROM sms_log WHERE phone=? ORDER BY sent_at DESC LIMIT 1", (phone,)).fetchone()
    conn.close()
    
    print(f"Last message after '0': {last_msg['message'][:50]}...")
    # Note: newly registered user is already "registered" in DB, so they see main menu upon "0"
    if "בחר" in last_msg['message']:
        print("SUCCESS: Returned to correct state/menu for unregistered/newly-registered user.")
    else:
        print(f"FAILURE: Did not return to correct menu. Got: {last_msg['message'][:100]}")

    # 2. Test for Registered User in sub-menu
    print("\n--- Testing Registered User in Sub-menu ---")
    handle_registered_user(phone, user, "2") # Enter Update Daf menu
    
    handle_registered_user(phone, user, "0")
    # Check outgoing SMS log
    conn = get_conn()
    last_msg = conn.execute("SELECT message FROM sms_log WHERE phone=? ORDER BY sent_at DESC LIMIT 1", (phone,)).fetchone()
    conn.close()
    
    print(f"Last message after '0': {last_msg['message'][:50]}...")
    if "בחר" in last_msg['message']:
        print("SUCCESS: Returned to main menu.")
    else:
        print(f"FAILURE: Did not return to main menu. Got: {last_msg['message'][:100]}")

if __name__ == "__main__":
    test_return_to_menu_logic()
