
import sqlite3
import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime, date
import os

# Set environment to use a test database
os.environ["DATABASE_URL"] = "" # Force SQLite for testing

import database
from database import get_conn, init_db, seed_tractates, seed_sms_templates
import scheduler
from scheduler import run_hour
import simulation_system

class TestDoubleRegistration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Create a fresh test database
        if os.path.exists("test_gemara.db"):
            os.remove("test_gemara.db")
        database.DB_PATH = "test_gemara.db"
        init_db()
        seed_tractates()
        seed_sms_templates()

    def setUp(self):
        # Clear users and subscriptions before each test
        conn = get_conn()
        conn.execute("DELETE FROM sent_questions")
        conn.execute("DELETE FROM subscriptions")
        conn.execute("DELETE FROM users")
        conn.commit()
        conn.close()
        # Reset USER_STATES
        simulation_system.USER_STATES = {}

    @patch('scheduler.get_live_mode', return_value=True)
    @patch('scheduler.send_sms')
    def test_two_users_same_hour(self, mock_send_sms, mock_live_mode):
        """Test that two different users registered for the same hour both receive their questions."""
        conn = get_conn()
        # Create 2 users
        conn.execute("INSERT INTO users (id, phone, name) VALUES (1, '0501111111', 'User 1')")
        conn.execute("INSERT INTO users (id, phone, name) VALUES (2, '0502222222', 'User 2')")
        
        # Get a tractate ID (Berachos should be 1 after seed)
        tractate = conn.execute("SELECT id FROM tractates LIMIT 1").fetchone()
        t_id = tractate['id']
        
        # Create subscriptions for both at 8:00
        conn.execute("INSERT INTO subscriptions (user_id, tractate_id, send_hour, current_daf, dafim_per_day, is_active, end_daf) VALUES (1, ?, 8, 2.0, 1.0, 1, 281)", (t_id,))
        conn.execute("INSERT INTO subscriptions (user_id, tractate_id, send_hour, current_daf, dafim_per_day, is_active, end_daf) VALUES (2, ?, 8, 2.0, 1.0, 1, 281)", (t_id,))
        conn.commit()
        conn.close()

        # Run scheduler for 8:00
        print("\nRunning scheduler for hour 8...")
        run_hour(8)

        # Verify send_sms was called for both users
        # Each user should get a question (total 2 calls)
        calls = mock_send_sms.call_args_list
        phones_received = [call.args[0] for call in calls]
        
        print(f"SMS sent to: {phones_received}")
        
        self.assertIn('0501111111', phones_received)
        self.assertIn('0502222222', phones_received)
        self.assertEqual(len(phones_received), 2)

    @patch('scheduler.get_live_mode', return_value=True)
    @patch('scheduler.send_sms')
    def test_one_user_two_tractates_same_hour(self, mock_send_sms, mock_live_mode):
        """Test that one user with two subscriptions for the same hour gets the multi-sub menu."""
        conn = get_conn()
        # Create 1 user
        conn.execute("INSERT INTO users (id, phone, name) VALUES (1, '0501111111', 'User 1')")
        
        # Get tractate IDs
        tractates = conn.execute("SELECT id FROM tractates LIMIT 2").fetchall()
        t1_id = tractates[0]['id']
        t2_id = tractates[1]['id']
        
        # Create 2 subscriptions for the same user at 8:00
        conn.execute("INSERT INTO subscriptions (user_id, tractate_id, send_hour, current_daf, dafim_per_day, is_active, end_daf) VALUES (1, ?, 8, 2.0, 1.0, 1, 281)", (t1_id,))
        conn.execute("INSERT INTO subscriptions (user_id, tractate_id, send_hour, current_daf, dafim_per_day, is_active, end_daf) VALUES (1, ?, 8, 2.0, 1.0, 1, 281)", (t2_id,))
        conn.commit()
        conn.close()

        # Run scheduler for 8:00
        print("\nRunning scheduler for hour 8 (Multi-sub)...")
        run_hour(8)

        # Verify send_sms was called
        calls = mock_send_sms.call_args_list
        self.assertEqual(len(calls), 1)
        
        phone, msg, uid = calls[0].args
        self.assertEqual(phone, '0501111111')
        print(f"Multi-sub message received: {msg}")
        
        # Check if state is PROCESSING_QUESTION_QUEUE
        state = simulation_system.USER_STATES.get('0501111111')
        self.assertIsNotNone(state)
        self.assertEqual(state['state'], 'PROCESSING_QUESTION_QUEUE')
        self.assertEqual(len(state['queue']), 2)

    @classmethod
    def tearDownClass(cls):
        # On Windows, sometimes file is still locked by SQLite
        import gc
        gc.collect()
        try:
            if os.path.exists("test_gemara.db"):
                os.remove("test_gemara.db")
        except:
            pass

if __name__ == "__main__":
    unittest.main()
