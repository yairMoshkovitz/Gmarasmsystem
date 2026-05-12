
import os
import sys
from datetime import datetime
from database import get_conn, init_db, seed_tractates, seed_sms_templates
from sms_service import get_sms_history
from simulation_system import handle_unregistered_user, handle_registered_user

def clear_db_logs():
    conn = get_conn()
    conn.execute("DELETE FROM sms_log")
    conn.commit()
    conn.close()

def test_new_flow():
    print("Testing New 4-Step Registration Flow...")
    
    # Reset DB for clean test
    init_db()
    seed_tractates()
    seed_sms_templates()
    clear_db_logs()
    
    phone = "0501112222"
    
    # 1. Step 1: Personal Details
    print("\n--- Sending Step 1: משה, כהן, בני ברק, 25 ---")
    handle_unregistered_user(phone, "משה, כהן, בני ברק, 25")
    
    history = get_sms_history(phone)
    last_msg = history[0]['message']
    print(f"Bot response (Step 1):\n{last_msg}")
    assert "נגדיר את הלימוד" in last_msg
    assert "מעולה משה" in last_msg
    
    # 2. Step 2: Tractate Details
    print("\n--- Sending Step 2: ברכות ב ע\"א עד י ע\"ב ---")
    conn = get_conn()
    user = conn.execute("SELECT * FROM users WHERE phone=?", (phone,)).fetchone()
    conn.close()
    
    clear_db_logs()
    handle_registered_user(phone, user, "ברכות ב ע\"א עד י ע\"ב")
    
    history = get_sms_history(phone)
    last_msg = history[0]['message']
    print(f"Bot response (Step 2):\n{last_msg}")
    assert "להגדיר את ההספק היומי" in last_msg
    
    # 3. Step 3: Study Preferences
    print("\n--- Sending Step 3: 1.5, 18 ---")
    clear_db_logs()
    handle_registered_user(phone, user, "1.5, 18")
    
    history = get_sms_history(phone)
    last_msg = history[0]['message']
    print(f"Bot response (Step 3):\n{last_msg}")
    assert "נרשמת ל" in last_msg
    assert "ברכות" in last_msg
    assert "1.5" in last_msg
    assert "18:00" in last_msg
    assert "צוות \"בפינו\"" in last_msg

    print("\nFlow Test Passed!")

if __name__ == "__main__":
    test_new_flow()
