
import sqlite3
import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime, date
import os
import json

# Force SQLite for testing
os.environ["DATABASE_URL"] = "" 

import database
from database import get_conn, init_db, seed_tractates, seed_sms_templates
import scheduler
from scheduler import run_hour
import simulation_system
import app
import sms_service

class TestFullDoubleRegistrationFlow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Setup test database
        if os.path.exists("test_full_flow.db"):
            try:
                os.remove("test_full_flow.db")
            except:
                pass
        database.DB_PATH = "test_full_flow.db"
        init_db()
        seed_tractates()
        seed_sms_templates()

    def setUp(self):
        conn = get_conn()
        conn.execute("DELETE FROM sent_questions")
        conn.execute("DELETE FROM subscriptions")
        conn.execute("DELETE FROM users")
        conn.execute("DELETE FROM sms_log")
        conn.commit()
        conn.close()
        simulation_system.USER_STATES = {}
        # Clear any cached templates if necessary
        from registration import clear_template_cache
        clear_template_cache()

    @patch('sms_service.get_live_mode', return_value=False)
    def test_full_flow_two_users(self, mock_live_mode):
        """
        Flow: Two users registered for 8:00.
        1. Scheduler runs at 8:00.
        2. Both get a question.
        3. Both answer correctly.
        """
        conn = get_conn()
        conn.execute("INSERT INTO users (id, phone, name) VALUES (1, '0501111111', 'User 1')")
        conn.execute("INSERT INTO users (id, phone, name) VALUES (2, '0502222222', 'User 2')")
        
        tractate = conn.execute("SELECT id FROM tractates LIMIT 1").fetchone()
        t_id = tractate['id']
        
        conn.execute("INSERT INTO subscriptions (user_id, tractate_id, send_hour, current_daf, dafim_per_day, is_active, end_daf) VALUES (1, ?, 8, 2.0, 1.0, 1, 281)", (t_id,))
        conn.execute("INSERT INTO subscriptions (user_id, tractate_id, send_hour, current_daf, dafim_per_day, is_active, end_daf) VALUES (2, ?, 8, 2.0, 1.0, 1, 281)", (t_id,))
        conn.commit()
        conn.close()

        # We override scheduler.get_live_mode specifically for this call
        with patch('scheduler.get_live_mode', return_value=True):
            print("\n--- STEP 1: Scheduler runs at 8:00 ---")
            run_hour(8)

        # Check sms_log for both users
        conn = get_conn()
        logs = conn.execute("SELECT * FROM sms_log WHERE direction='out'").fetchall()
        phones = [r['phone'] for r in logs]
        print(f"Messages sent to: {phones}")
        self.assertIn('0501111111', phones)
        self.assertIn('0502222222', phones)
        conn.close()

        print("\n--- STEP 2: User 1 answers '1' ---")
        app.process_incoming_sms('0501111111', '1')
        
        # User 1 should have 2 messages sent now (original question + next/closure)
        conn = get_conn()
        user1_logs = conn.execute("SELECT * FROM sms_log WHERE phone='0501111111' AND direction='out'").fetchall()
        self.assertGreaterEqual(len(user1_logs), 2)
        conn.close()

    @patch('sms_service.get_live_mode', return_value=False)
    def test_full_flow_multi_sub(self, mock_live_mode):
        """
        Flow: One user with 2 subscriptions for 8:00.
        """
        conn = get_conn()
        conn.execute("INSERT INTO users (id, phone, name) VALUES (1, '0501111111', 'User 1')")
        tractates = conn.execute("SELECT id FROM tractates LIMIT 2").fetchall()
        t1_id = tractates[0]['id']
        t2_id = tractates[1]['id']
        
        conn.execute("INSERT INTO subscriptions (user_id, tractate_id, send_hour, current_daf, dafim_per_day, is_active, end_daf) VALUES (1, ?, 8, 2.0, 1.0, 1, 281)", (t1_id,))
        conn.execute("INSERT INTO subscriptions (user_id, tractate_id, send_hour, current_daf, dafim_per_day, is_active, end_daf) VALUES (1, ?, 8, 2.0, 1.0, 1, 281)", (t2_id,))
        conn.commit()
        conn.close()

        with patch('scheduler.get_live_mode', return_value=True):
            print("\n--- STEP 1: Scheduler runs (Multi-sub) ---")
            run_hour(8)
        
        # Check for menu message
        conn = get_conn()
        last_log = conn.execute("SELECT * FROM sms_log WHERE phone='0501111111' AND direction='out' ORDER BY id DESC LIMIT 1").fetchone()
        print(f"Menu message: {last_log['message']}")
        self.assertIn("מאיזו מסכת תרצה להתחיל", last_log['message'])
        conn.close()

        print("\n--- STEP 2: User chooses '1' ---")
        app.process_incoming_sms('0501111111', '1')
        
        # State should be AWAITING_ANSWER
        self.assertEqual(simulation_system.USER_STATES['0501111111']['state'], 'AWAITING_ANSWER')

    @classmethod
    def tearDownClass(cls):
        import gc
        gc.collect()
        try:
            if os.path.exists("test_full_flow.db"):
                os.remove("test_full_flow.db")
        except:
            pass

if __name__ == "__main__":
    unittest.main()
