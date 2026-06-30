import unittest
import os
import json
from datetime import datetime
from database import get_conn, init_db, seed_tractates, seed_sms_templates
from sms_service import send_sms
import scheduler
import simulation_system
from unittest.mock import patch, MagicMock

class TestReproduction(unittest.TestCase):
    def setUp(self):
        # Use a test database
        if os.path.exists("test_qa.db"):
            try:
                # Close any existing connections by letting the garbage collector handle it or importing database and calling something if it had a close all
                import gc
                gc.collect()
                os.remove("test_qa.db")
            except Exception as e:
                print(f"DEBUG: Failed to remove test_qa.db: {e}")
        os.environ["DATABASE_URL"] = "" # Force SQLite
        # We need to monkeypatch get_conn to use our test db
        self.db_path = "test_qa.db"
        
        import database
        database.DATABASE_URL = ""
        database.DB_PATH = self.db_path
        
        init_db()
        seed_tractates()
        seed_sms_templates()
        
        # Add a user and subscription
        conn = get_conn()
        conn.execute("INSERT INTO users (phone, name) VALUES (?, ?)", ("0501234567", "Test User"))
        user_id = conn.execute("SELECT id FROM users WHERE phone=?", ("0501234567",)).fetchone()[0]
        # Tractate 1 (usually Berachos)
        conn.execute("INSERT INTO subscriptions (user_id, tractate_id, start_daf, end_daf, current_daf, dafim_per_day, send_hour, is_active) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                     (user_id, 1, 2.0, 10.0, 2.0, 1.0, 8, 1))
        self.user_id = user_id
        conn.commit()
        conn.close()
        
        simulation_system.USER_STATES.clear()

    def tearDown(self):
        import database
        database.DB_PATH = "gemara_sms.db" # Restore
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except:
                pass

    @patch('sms_service.get_live_mode')
    @patch('sms_service.send_real_sms')
    def test_reproduce_out_of_order(self, mock_send_real, mock_live):
        """
        Reproduce scenario: System sends 'study_closure' (last message) BEFORE 'question'.
        """
        mock_live.return_value = True
        # Ensure we use the real send_sms behavior but mocked for actual delivery
        def side_effect(phone, msg, uid=None):
            print(f"DEBUG: Mock send_sms called with: {msg[:50]}...")
        mock_send_real.side_effect = side_effect

        from scheduler import send_daily_questions
        from simulation_system import handle_registered_user

        conn = get_conn()
        sub = conn.execute("SELECT s.*, t.name as tractate_name, u.phone, u.name as user_name FROM subscriptions s JOIN tractates t ON s.tractate_id = t.id JOIN users u ON s.user_id = u.id WHERE u.phone=?", ("0501234567",)).fetchone()
        user = conn.execute("SELECT * FROM users WHERE phone=?", ("0501234567",)).fetchone()
        conn.close()

        # 1. Trigger daily questions
        print("\n--- Triggering daily questions ---")
        send_daily_questions(dict(sub))
        
        # Verify first message is a question
        self.assertTrue(len(mock_send_real.call_args_list) > 0, "No messages sent")
        self.assertIn("דף ב", mock_send_real.call_args_list[0][0][1])
        
        # 2. User answers "כן"
        mock_send_real.reset_mock()
        handle_registered_user("0501234567", dict(user), "כן")
        
        # In current logic:
        # Question 1 answered -> call send_next_question_or_finish
        # selects Question 2 -> sends Question 2
        
        self.assertIn("דף ב", mock_send_real.call_args_list[0][0][1])
        
        # 3. User answers "כן" to Question 2
        mock_send_real.reset_mock()
        handle_registered_user("0501234567", dict(user), "כן")
        
        # Question 2 answered -> call send_next_question_or_finish
        # count_row[0] is 2 (daily_limit) -> calls finish_subscription_day
        # finish_subscription_day -> advance_subscription -> sends completion msg if end reached
        # advance_subscription -> sends 'study_closure'
        
        print("\nMessages sent after 2nd answer:")
        for i, call in enumerate(mock_send_real.call_args_list):
            print(f"{i}: {call[0][1][:50]}...")

        # If the user says they get Question 2 (last) AFTER Closure, it's weird.
        # BUT wait! If they are at the END of the subscription:
        # advance_subscription sends 'subscription_completed'
        # AND then finish_subscription_day sends 'study_closure'.

    @patch('sms_service.get_live_mode')
    @patch('sms_service.send_real_sms')
    def test_reproduce_no_questions_then_question(self, mock_send_real, mock_live):
        """
        Reproduce: System sends 'no_questions_today' then a question.
        """
        mock_live.return_value = True
        # Ensure we use the real send_sms behavior but mocked for actual delivery
        def side_effect(phone, msg, uid=None):
            print(f"DEBUG: Mock send_sms called with: {msg[:50]}...")
        mock_send_real.side_effect = side_effect

        from scheduler import send_daily_questions
        import time

        conn = get_conn()
        # Create a fresh subscription with a high current_daf where we know there are no questions
        # Berachos usually ends around 64. Let's use 100.
        conn.execute("INSERT INTO subscriptions (user_id, tractate_id, start_daf, end_daf, current_daf, dafim_per_day, send_hour, is_active) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                     (self.user_id, 1, 2.0, 150.0, 140.0, 1.0, 8, 1))
        sub_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        sub = conn.execute("SELECT s.*, t.name as tractate_name, u.phone, u.name as user_name FROM subscriptions s JOIN tractates t ON s.tractate_id = t.id JOIN users u ON s.user_id = u.id WHERE s.id=?", (sub_id,)).fetchone()
        conn.close()

        # 1. Trigger daily questions for a daf with NO questions
        print("\n--- Running daily questions for daf 140 (expecting NO questions) ---")
        
        conn = get_conn()
        conn.execute("INSERT INTO tractates (name, json_path) VALUES (?, ?)", ("EmptyTractate", "empty.json"))
        t_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute("INSERT INTO subscriptions (user_id, tractate_id, start_daf, end_daf, current_daf, dafim_per_day, send_hour, is_active) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                     (self.user_id, t_id, 2.0, 10.0, 2.0, 1.0, 8, 1))
        sub_id_empty = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        sub_empty = conn.execute("SELECT s.*, t.name as tractate_name, u.phone, u.name as user_name FROM subscriptions s JOIN tractates t ON s.tractate_id = t.id JOIN users u ON s.user_id = u.id WHERE s.id=?", (sub_id_empty,)).fetchone()
        conn.close()

        print(f"DEBUG: Starting send_daily_questions for sub {sub_id_empty}")
        send_daily_questions(dict(sub_empty))
        
        # Should send 'no_questions_today'
        self.assertTrue(len(mock_send_real.call_args_list) > 0, "No messages sent")
        msgs = [call[0][1] for call in mock_send_real.call_args_list]
        self.assertTrue(any("היום אין שאלות" in m for m in msgs), f"Expected 'no_questions_today' message, got: {msgs}")

if __name__ == "__main__":
    unittest.main()
