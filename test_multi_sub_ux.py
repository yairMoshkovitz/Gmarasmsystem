import os
import sys
from datetime import datetime, date
from database import get_conn, init_db
from simulation_system import receive_sms, USER_STATES, handle_registered_user
from sms_service import get_sms_history

def simulate_inbound(phone, msg):
    receive_sms(phone, msg)
    conn = get_conn()
    user = conn.execute("SELECT * FROM users WHERE phone=?", (phone,)).fetchone()
    conn.close()
    handle_registered_user(phone, user, msg)

def test_multi_sub_flow():
    # 1. Setup: Clean DB and create user with 2 subs
    os.environ["SIMULATION_MODE"] = "True"
    init_db()
    conn = get_conn()
    conn.execute("INSERT INTO users (phone, name, last_name, city, age) VALUES ('123456', 'TestUser', 'Last', 'City', 30)")
    user_id = conn.execute("SELECT id FROM users WHERE phone='123456'").fetchone()[0]
    
    # Sub 1: Berachos 2-5
    conn.execute("INSERT INTO subscriptions (user_id, tractate_id, start_daf, end_daf, current_daf, dafim_per_day, send_hour) VALUES (?, 1, 2.0, 5.0, 2.0, 1.0, 18)", (user_id,))
    # Sub 2: Berachos 10-15
    conn.execute("INSERT INTO subscriptions (user_id, tractate_id, start_daf, end_daf, current_daf, dafim_per_day, send_hour) VALUES (?, 1, 10.0, 15.0, 10.0, 1.0, 18)", (user_id,))
    conn.commit()
    conn.close()

    print("\n--- Testing Option 2 (Update Daf) for Multi-Sub ---")
    simulate_inbound("123456", "2")
    last_sms = get_sms_history("123456")[-1]["message"]
    print(f"System Response: {last_sms}")
    assert "בחר מנוי לעדכון דף" in last_sms

    print("\n--- Selecting Sub 1 ---")
    simulate_inbound("123456", "1")
    last_sms = get_sms_history("123456")[-1]["message"]
    print(f"System Response: {last_sms}")
    assert "לאיזה דף הגעת" in last_sms

    print("\n--- Sending New Daf ---")
    simulate_inbound("123456", "ג")
    last_sms = get_sms_history("123456")[-1]["message"]
    print(f"System Response: {last_sms}")
    assert "מנוי ברכות (2 - 5) עודכן ל-ג" in last_sms

    print("\n--- Mark both as sent today ---")
    conn = get_conn()
    conn.execute("INSERT INTO sent_questions (user_id, subscription_id, question_id, sent_at) VALUES (?, 1, 'q1', ?)", (user_id, datetime.now().isoformat()))
    conn.execute("INSERT INTO sent_questions (user_id, subscription_id, question_id, sent_at) VALUES (?, 2, 'q2', ?)", (user_id, datetime.now().isoformat()))
    conn.commit()
    conn.close()

    print("\n--- Testing Manual Question (Option 1) when all sent ---")
    simulate_inbound("123456", "1")
    last_sms = get_sms_history("123456")[-1]["message"]
    print(f"System Response:\n{last_sms}")
    assert "כבר קיבלת את כל השאלות" in last_sms
    assert "ברכות (2 - 5): הלימוד מחר" in last_sms
    assert "ברכות (10 - 15): הלימוד מחר" in last_sms

    print("\n--- Multi-Sub Enhanced Flow Test Passed! ---")

if __name__ == "__main__":
    test_multi_sub_flow()
