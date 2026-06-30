import os
import sys
import time
import logging
from datetime import datetime
from database import get_conn, init_db
from state_manager import get_user_state, set_user_state
from simulation_system import receive_sms, USER_STATES, handle_registered_user
from sms_service import get_sms_history, set_live_mode
from scheduler import run_hour

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def simulate_inbound(phone, msg):
    print(f"\n[User {phone}]: {msg}")
    receive_sms(phone, msg)
    conn = get_conn()
    user = conn.execute("SELECT * FROM users WHERE phone=?", (phone,)).fetchone()
    conn.close()
    handle_registered_user(phone, user, msg)

def test_concurrent_multi_sub_sending():
    print("--- Starting Concurrent Multi-Subscription Test ---")
    
    os.environ["SIMULATION_MODE"] = "True"
    set_live_mode(True) 
    init_db()
    
    # CLEAR ALL STATES AND LOGS for this phone to avoid interference
    phone = "0501112333"
    conn = get_conn()
    conn.execute("DELETE FROM user_states WHERE phone=?", (phone,))
    conn.execute("DELETE FROM sms_log WHERE phone=?", (phone,))
    conn.execute("DELETE FROM sent_questions WHERE user_id IN (SELECT id FROM users WHERE phone=?)", (phone,))
    conn.execute("DELETE FROM subscriptions WHERE user_id IN (SELECT id FROM users WHERE phone=?)", (phone,))
    conn.execute("DELETE FROM users WHERE phone=?", (phone,))
    conn.commit()

    conn.execute("INSERT OR IGNORE INTO tractates (id, name) VALUES (1, 'ברכות')")
    conn.execute("INSERT OR IGNORE INTO tractates (id, name) VALUES (2, 'שבת')")
    conn.execute("INSERT INTO users (phone, name, last_name, city, age) VALUES (?, 'Concurrent', 'Tester', 'Bnei Brak', 25)", (phone,))
    user_id = conn.execute("SELECT id FROM users WHERE phone=?", (phone,)).fetchone()[0]
    
    # Create 2 subs at 18:00
    conn.execute("INSERT INTO subscriptions (user_id, tractate_id, start_daf, end_daf, current_daf, dafim_per_day, send_hour) VALUES (?, 1, 2.0, 50.0, 2.0, 1.0, 18)", (user_id,))
    conn.execute("INSERT INTO subscriptions (user_id, tractate_id, start_daf, end_daf, current_daf, dafim_per_day, send_hour) VALUES (?, 2, 2.0, 50.0, 2.0, 1.0, 18)", (user_id,))
    conn.commit()
    conn.close()

    print(f"\n[Action]: Running scheduler for hour 18...")
    run_hour(18)
    
    history = get_sms_history(phone)
    print(f"\n[Result]: Latest SMS (should be menu):")
    # print(f"  - {history[0]['message']}")
    
    # 1. User selects 1 (Berachos)
    simulate_inbound(phone, "1")
    history = get_sms_history(phone)
    print(f"\n[Result after selecting 1 (should be question)]: ")
    # print(f"  - {history[0]['message']}")
    
    # 2. Answer "כן" (First question)
    simulate_inbound(phone, "כן")
    history = get_sms_history(phone)
    print(f"\n[Result after answering 'כן' (should be second question)]: ")
    # print(f"  - {history[0]['message']}")
    
    # 3. Answer "כן" (Second question - finishes Berachos)
    simulate_inbound(phone, "כן")
    history = get_sms_history(phone)
    print(f"\n[Result after finishing Berachos (should be menu for Shabbat)]: ")
    # Looking for transition messages
    for msg in history[:3]:
        print(f"  - {msg['message']}")
        
    set_live_mode(False)
    print("\n--- Test Finished ---")

if __name__ == "__main__":
    test_concurrent_multi_sub_sending()
