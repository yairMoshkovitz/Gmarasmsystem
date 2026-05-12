
import sqlite3
import os
import json
from datetime import datetime, date
from unittest.mock import patch

# Setup
os.environ["DATABASE_URL"] = ""
import database
from database import get_conn, init_db, seed_tractates, seed_sms_templates
import scheduler
from scheduler import run_hour
import simulation_system
import app
import sms_service

def run_documented_flow():
    # 1. Setup Database
    db_file = "flow_output.db"
    if os.path.exists(db_file): os.remove(db_file)
    database.DB_PATH = db_file
    init_db()
    seed_tractates()
    seed_sms_templates()

    output = []
    def log(msg):
        print(msg)
        output.append(msg)

    log("=== תחילת תיעוד זרימה: הרשמה כפולה לאותה שעה ===")
    
    conn = get_conn()
    # יצירת שני משתמשים
    conn.execute("INSERT INTO users (id, phone, name) VALUES (1, '0501111111', 'משה')")
    conn.execute("INSERT INTO users (id, phone, name) VALUES (2, '0502222222', 'אהרון')")
    
    # שליפת מסכתות
    tractates = conn.execute("SELECT id, name FROM tractates LIMIT 2").fetchall()
    t1_id, t1_name = tractates[0]['id'], tractates[0]['name']
    t2_id, t2_name = tractates[1]['id'], tractates[1]['name']
    
    # תרחיש א': שני משתמשים שונים באותה שעה (8:00)
    conn.execute("INSERT INTO subscriptions (user_id, tractate_id, send_hour, current_daf, dafim_per_day, is_active, end_daf) VALUES (1, ?, 8, 2.0, 1.0, 1, 281)", (t1_id,))
    conn.execute("INSERT INTO subscriptions (user_id, tractate_id, send_hour, current_daf, dafim_per_day, is_active, end_daf) VALUES (2, ?, 8, 2.0, 1.0, 1, 281)", (t1_id,))
    
    # תרחיש ב': משתמש אחד עם שתי מסכתות באותה שעה (9:00)
    conn.execute("INSERT INTO users (id, phone, name) VALUES (3, '0503333333', 'יצחק')")
    conn.execute("INSERT INTO subscriptions (user_id, tractate_id, send_hour, current_daf, dafim_per_day, is_active, end_daf) VALUES (3, ?, 9, 2.0, 1.0, 1, 281)", (t1_id,))
    conn.execute("INSERT INTO subscriptions (user_id, tractate_id, send_hour, current_daf, dafim_per_day, is_active, end_daf) VALUES (3, ?, 9, 2.0, 1.0, 1, 281)", (t2_id,))
    
    conn.commit()
    conn.close()

    log("\n--- שלב 1: הרצת סקדיולר לשעה 8:00 (שני משתמשים שונים) ---")
    with patch('scheduler.get_live_mode', return_value=True), \
         patch('sms_service.get_live_mode', return_value=False):
        run_hour(8)

    conn = get_conn()
    logs_8 = conn.execute("SELECT phone, message FROM sms_log WHERE direction='out'").fetchall()
    for row in logs_8:
        log(f"נשלח ל-{row['phone']}: {row['message'][:100]}...")
    conn.execute("DELETE FROM sms_log")
    conn.commit()

    log("\n--- שלב 2: הרצת סקדיולר לשעה 9:00 (משתמש אחד, שתי מסכתות) ---")
    simulation_system.USER_STATES = {}
    with patch('scheduler.get_live_mode', return_value=True), \
         patch('sms_service.get_live_mode', return_value=False):
        run_hour(9)

    last_log = conn.execute("SELECT phone, message FROM sms_log WHERE phone='0503333333' AND direction='out' ORDER BY id DESC LIMIT 1").fetchone()
    log(f"נשלח ליצחק (0503333333):\n{last_log['message']}")
    
    log("\n--- שלב 3: יצחק בוחר במסכת הראשונה (שליחת '1') ---")
    conn.execute("DELETE FROM sms_log")
    conn.commit()
    
    with patch('sms_service.get_live_mode', return_value=False):
        app.process_incoming_sms('0503333333', '1')
    
    q_log = conn.execute("SELECT message FROM sms_log WHERE phone='0503333333' AND direction='out' ORDER BY id DESC LIMIT 1").fetchone()
    log(f"תגובת המערכת ליצחק:\n{q_log['message']}")
    
    # Refresh sub info to see where we are
    sub1_id = conn.execute("SELECT id FROM subscriptions WHERE user_id=3 LIMIT 1").fetchone()['id']

    log("\n--- שלב 4: יצחק עונה על השאלות של המסכת הראשונה ---")
    with patch('sms_service.get_live_mode', return_value=False):
        log("יצחק עונה 'כן' לשאלה הראשונה...")
        app.process_incoming_sms('0503333333', 'כן')
        q2_log = conn.execute("SELECT message FROM sms_log WHERE phone='0503333333' AND direction='out' ORDER BY id DESC LIMIT 1").fetchone()
        log(f"תגובת המערכת (שאלה 2):\n{q2_log['message']}")
        
        log("יצחק עונה 'כן' לשאלה השנייה (סיום מסכת ראשונה להיום)...")
        # For documentation, we clear the count of sent_questions for this sub to allow finishing it
        # Or we ensure we are under the limit. scheduler says limit is 2.
        app.process_incoming_sms('0503333333', 'כן')
        
    next_menu_log = conn.execute("SELECT message FROM sms_log WHERE phone='0503333333' AND direction='out' ORDER BY id DESC LIMIT 1").fetchone()
    log(f"תגובת המערכת (מעבר למסכת הבאה):\n{next_menu_log['message']}")

    log("\n--- שלב 5: יצחק מסיים את המסכת השנייה ---")
    with patch('sms_service.get_live_mode', return_value=False):
        log("יצחק עונה 'כן' לשאלה הראשונה במסכת השנייה...")
        app.process_incoming_sms('0503333333', 'כן')
        log("יצחק עונה 'כן' לשאלה השנייה במסכת השנייה...")
        app.process_incoming_sms('0503333333', 'כן')

    closure_log = conn.execute("SELECT message FROM sms_log WHERE phone='0503333333' AND direction='out' ORDER BY id DESC LIMIT 1").fetchone()
    log(f"תגובת המערכת הסופית (סיום כל הלימוד היומי):\n{closure_log['message']}")

    log("\n=== סיום תיעוד מלא ===")
    
    with open("flow_result.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(output))
    
    conn.close()
    if os.path.exists(db_file): os.remove(db_file)

if __name__ == "__main__":
    run_documented_flow()
