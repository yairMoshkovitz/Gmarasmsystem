
import os
import sys
from datetime import datetime
from database import get_conn, init_db, seed_tractates, seed_sms_templates
from sms_service import receive_sms
from simulation_system import handle_registered_user
from scheduler import run_hour

def setup_test_db():
    # Force use of test.db
    os.environ["DATABASE_URL"] = ""
    db_path = os.path.join(os.getcwd(), "test.db")
    if os.path.exists(db_path):
        try:
            os.remove(db_path)
        except Exception as e:
            print(f"Error removing {db_path}: {e}")
    init_db()
    seed_tractates()
    seed_sms_templates()
    
    conn = get_conn()
    # Create a user
    conn.execute("INSERT INTO users (id, phone, name, registered_at) VALUES (10, '0556622188', 'יאיר', CURRENT_TIMESTAMP)")
    
    # Create two subscriptions
    # Sub 9: Chulin
    conn.execute("INSERT INTO subscriptions (id, user_id, tractate_id, start_daf, end_daf, current_daf, dafim_per_day, send_hour, is_active) "
                 "VALUES (9, 10, (SELECT id FROM tractates WHERE name='חולין'), 2.0, 143.5, 28.0, 0.5, 18, 1)")
    
    # Sub 29: Bava Batra
    conn.execute("INSERT INTO subscriptions (id, user_id, tractate_id, start_daf, end_daf, current_daf, dafim_per_day, send_hour, is_active) "
                 "VALUES (29, 10, (SELECT id FROM tractates WHERE name='בבא בתרא'), 28.0, 36.5, 36.0, 0.5, 18, 1)")
    
    conn.commit()
    conn.close()

def reproduce():
    os.environ["DATABASE_URL"] = "" # Use SQLite for test
    if os.path.exists("test.db"):
        os.remove("test.db")
    
    setup_test_db()
    
    phone = "0556622188"
    
    print("\n--- Phase 1: Trigger Daily (Multi-Sub) ---")
    run_hour(18) 
    # Should send queue_start_menu with 1. חולין 2. בבא בתרא
    
    print("\n--- Phase 2: User selects 1 (Chulin) ---")
    conn = get_conn()
    user = conn.execute("SELECT * FROM users WHERE phone=?", (phone,)).fetchone()
    conn.close()
    handle_registered_user(phone, user, "1")
    # Should send Chulin question 1/2
    
    print("\n--- Phase 3: User answers 'כן' (Chulin 1/2) ---")
    handle_registered_user(phone, user, "כן")
    # Should send Chulin question 2/2
    
    print("\n--- Phase 4: User answers 'כן' (Chulin 2/2) ---")
    handle_registered_user(phone, user, "כן")
    # SHOULD NOT include Chulin in the menu now!
    # Should send queue_next_menu with ONLY 2. בבא בתרא
    # OR if we only have 1 left, send queue_last_one and Bava Batra question.
    
if __name__ == "__main__":
    reproduce()
