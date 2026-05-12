
import sqlite3
import os
import json
from datetime import datetime, date
from unittest.mock import patch

# Force SQLite for testing
os.environ["DATABASE_URL"] = ""

import database
from database import get_conn, init_db, seed_tractates, seed_sms_templates
import scheduler
from scheduler import run_hour
import simulation_system
import app
import sms_service

def run_real_results_test():
    # 1. Setup clean test DB
    db_file = "real_test_results.db"
    if os.path.exists(db_file): os.remove(db_file)
    database.DB_PATH = db_file
    init_db()
    seed_tractates()
    seed_sms_templates()

    results_file = "test_execution_results.txt"
    with open(results_file, "w", encoding="utf-8") as f:
        f.write("=== דוח הרצת טסט חי: הרשמה כפולה לאותה שעה ===\n")
        f.write(f"זמן הרצה: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

        # Setup scenario
        conn = get_conn()
        # User 1: Moshe (0501111111) - 1 tractate at 8:00
        conn.execute("INSERT INTO users (id, phone, name) VALUES (1, '0501111111', 'Moshe')")
        # User 2: Yitzhak (0503333333) - 2 tractates at 8:00
        conn.execute("INSERT INTO users (id, phone, name) VALUES (3, '0503333333', 'Yitzhak')")
        
        tractates = conn.execute("SELECT id, name FROM tractates LIMIT 2").fetchall()
        t1_id, t1_name = tractates[0]['id'], tractates[0]['name']
        t2_id, t2_name = tractates[1]['id'], tractates[1]['name']
        
        conn.execute("INSERT INTO subscriptions (user_id, tractate_id, send_hour, current_daf, dafim_per_day, is_active, end_daf) VALUES (1, ?, 8, 2.0, 1.0, 1, 281)", (t1_id,))
        conn.execute("INSERT INTO subscriptions (user_id, tractate_id, send_hour, current_daf, dafim_per_day, is_active, end_daf) VALUES (3, ?, 8, 2.0, 1.0, 1, 281)", (t1_id,))
        conn.execute("INSERT INTO subscriptions (user_id, tractate_id, send_hour, current_daf, dafim_per_day, is_active, end_daf) VALUES (3, ?, 8, 2.0, 1.0, 1, 281)", (t2_id,))
        conn.commit()

        f.write("--- שלב 1: הפעלת ה-Scheduler לשעה 8:00 ---\n")
        with patch('scheduler.get_live_mode', return_value=True), \
             patch('sms_service.get_live_mode', return_value=False):
            run_hour(8)

        # Capture results from log
        logs = conn.execute("SELECT phone, message FROM sms_log WHERE direction='out' ORDER BY id").fetchall()
        for log in logs:
            f.write(f"הודעה נשלחה ל-{log['phone']}:\n{log['message']}\n")
            f.write("-" * 30 + "\n")

        f.write("\n--- שלב 2: יצחק (Multi-Sub) בוחר במסכת 1 ---\n")
        conn.execute("DELETE FROM sms_log")
        conn.commit()
        
        with patch('sms_service.get_live_mode', return_value=False):
            app.process_incoming_sms('0503333333', '1')
        
        response = conn.execute("SELECT message FROM sms_log WHERE phone='0503333333' AND direction='out' ORDER BY id DESC LIMIT 1").fetchone()
        f.write(f"תגובה ליצחק:\n{response['message']}\n")

        f.write("\n--- שלב 3: יצחק עונה על השאלות ומסיים את המסכת הראשונה ---\n")
        with patch('sms_service.get_live_mode', return_value=False):
            app.process_incoming_sms('0503333333', 'כן') # Answer 1
            app.process_incoming_sms('0503333333', 'כן') # Answer 2
        
        final_logs = conn.execute("SELECT message FROM sms_log WHERE phone='0503333333' AND direction='out' ORDER BY id DESC LIMIT 2").fetchall()
        f.write("הודעות אחרונות ליצחק (מעבר למסכת הבאה):\n")
        for log in reversed(final_logs):
            f.write(f"{log['message']}\n")
            f.write("-" * 20 + "\n")

        f.write("\n--- שלב 4: יצחק מסיים את המסכת השנייה ---\n")
        with patch('sms_service.get_live_mode', return_value=False):
            app.process_incoming_sms('0503333333', 'כן') # Answer 1 of sub 2
            app.process_incoming_sms('0503333333', 'כן') # Answer 2 of sub 2
            
        closure_log = conn.execute("SELECT message FROM sms_log WHERE phone='0503333333' AND direction='out' ORDER BY id DESC LIMIT 1").fetchone()
        f.write(f"הודעת סגירה סופית:\n{closure_log['message']}\n")

        f.write("\n=== סיום הרצה מוצלח ===\n")
        conn.close()

    print(f"Results written to {results_file}")
    if os.path.exists(db_file): os.remove(db_file)

if __name__ == "__main__":
    run_real_results_test()
