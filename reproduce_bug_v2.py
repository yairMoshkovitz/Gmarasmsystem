
import os
from database import get_conn, init_db, seed_tractates, daf_to_float
from registration import register_user, subscribe
from simulation_system import handle_registered_user, USER_STATES
from sms_service import get_sms_history

def reproduce():
    # Setup
    if os.path.exists("test_sms.db"):
        os.remove("test_sms.db")
    os.environ["DATABASE_URL"] = "" # Use SQLite
    init_db()
    seed_tractates()
    
    phone = "0501234567"
    user_id = register_user(phone, "Test", "User")
    
    conn = get_conn()
    tractate = conn.execute("SELECT id FROM tractates WHERE name='ברכות'").fetchone()
    conn.close()
    
    # Subscribe Berachos (2a-10b)
    subscribe(user_id, tractate['id'], 2.0, 10.5, 1.0, 18)
    
    # Now simulate update to 70a
    USER_STATES[phone] = {"state": "AWAITING_UPDATE_DAF", "sub_id": 1} # sub_id 1 since it's the first sub
    
    print("\n--- Simulating updating Berachos to 70a (out of 2-10b range) ---")
    user = {"id": user_id, "name": "Test", "phone": phone}
    handle_registered_user(phone, user, "ע ע\"א")
    
    history = get_sms_history(phone)
    print("\nLast SMS sent:")
    if history:
        print(history[-1]['message'])
    
    conn = get_conn()
    sub = conn.execute("SELECT current_daf FROM subscriptions WHERE id=1").fetchone()
    conn.close()
    print(f"\nSubscription current_daf in DB: {sub['current_daf']} (70.0 expected if bug exists)")

if __name__ == "__main__":
    reproduce()
