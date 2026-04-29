
from registration import register_user, get_all_tractates, get_user_subscriptions, clear_template_cache
from simulation_system import handle_unregistered_user, handle_registered_user, USER_STATES
from database import get_conn, init_db, seed_tractates, seed_sms_templates
from sms_service import get_sms_history
import os
import sys

# Force UTF-8 for printing to avoid Windows encoding issues
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def test_new_registration_flow():
    init_db()
    seed_tractates()
    seed_sms_templates()
    clear_template_cache()
    
    phone = "0501234567"
    
    # Clean user if exists
    conn = get_conn()
    conn.execute("DELETE FROM users WHERE phone=?", (phone,))
    conn.commit()
    conn.close()

    print("--- Testing Step 1: Personal Info ---")
    handle_unregistered_user(phone, "משה, כהן, בני ברק, 25")
    
    history = get_sms_history(phone)
    print(f"Bot response: {history[-1]['message']}")
    
    print("\n--- Testing Step 2: Flexible Tractate Registration (No Commas) ---")
    # Simulation logic for step 2
    conn = get_conn()
    user = conn.execute("SELECT * FROM users WHERE phone=?", (phone,)).fetchone()
    conn.close()
    
    # Test case 1: "ברכות ב עד י 1 18"
    print("Sending: ברכות ב עד י 1 18")
    handle_registered_user(phone, user, "ברכות ב עד י 1 18")
    
    history = get_sms_history(phone)
    print(f"Bot response: {history[-1]['message']}")
    
    # Verify subscription
    conn = get_conn()
    sub = conn.execute("SELECT * FROM subscriptions WHERE user_id=? ORDER BY id DESC LIMIT 1", (user['id'],)).fetchone()
    if sub:
        print(f"Subscription created! Start: {sub['start_daf']}, End: {sub['end_daf']}")
    conn.close()

    print("\n--- Testing Case 4: Support for ע\"א ע\"ב ---")
    USER_STATES[phone] = {"state": "AWAITING_REG_STEP_2"}
    print("Sending: ברכות כ ע\"א עד כה ע\"ב 1 18")
    handle_registered_user(phone, user, "ברכות כ ע\"א עד כה ע\"ב 1 18")
    history = get_sms_history(phone)
    print(f"Bot response: {history[-1]['message']}")
    
    conn = get_conn()
    sub = conn.execute("SELECT * FROM subscriptions WHERE user_id=? ORDER BY id DESC LIMIT 1", (user['id'],)).fetchone()
    if sub:
        print(f"Subscription created! Start: {sub['start_daf']}, End: {sub['end_daf']}")
    conn.close()

    print("\n--- Testing Case 5: Default Amud Support (End daf should be amud B) ---")
    USER_STATES[phone] = {"state": "AWAITING_REG_STEP_2"}
    print("Sending: ברכות ל עד לא 1 18")
    handle_registered_user(phone, user, "ברכות ל עד לא 1 18")
    
    conn = get_conn()
    sub = conn.execute("SELECT * FROM subscriptions WHERE user_id=? ORDER BY id DESC LIMIT 1", (user['id'],)).fetchone()
    if sub:
        print(f"Subscription created! Start: {sub['start_daf']} (should be 30.0), End: {sub['end_daf']} (should be 31.5)")
    conn.close()

    print("\n--- Testing Case 6: Tractate in Shas but not in DB ---")
    USER_STATES[phone] = {"state": "AWAITING_REG_STEP_2"}
    print("Sending: פאה א עד י 1 18")
    handle_registered_user(phone, user, "פאה א עד י 1 18")
    history = get_sms_history(phone)
    print(f"Bot response: {history[-1]['message']}")

if __name__ == "__main__":
    test_new_registration_flow()
