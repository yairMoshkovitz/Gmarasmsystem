
import os
import json
import logging
import unittest
from database import get_conn, init_db, seed_tractates
from sms_service import receive_sms, INBOX
from simulation_system import handle_registered_user
from scheduler import send_daily_questions

# Configure logging
logging.basicConfig(level=logging.INFO)

class TestQuestionFlow(unittest.TestCase):
    def setUp(self):
        self.db_path = "test_questions_fix.db"
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except:
                pass
        
        import database
        database.DB_PATH = os.path.join(os.getcwd(), self.db_path)
        os.environ["DB_NAME"] = self.db_path
        if "DATABASE_URL" in os.environ:
            del os.environ["DATABASE_URL"]
            
        init_db()
        seed_tractates()
        
        conn = get_conn()
        # Create a user
        conn.execute("INSERT INTO users (phone, name) VALUES ('0509999999', 'בודק')")
        self.user_id = conn.execute("SELECT id FROM users WHERE phone='0509999999'").fetchone()[0]
        
        # Create a subscription
        conn.execute("""
            INSERT INTO subscriptions (user_id, tractate_id, start_daf, end_daf, current_daf, dafim_per_day, send_hour, is_active)
            VALUES (?, 1, 2.0, 10.0, 2.0, 1.0, 18, 1)
        """, (self.user_id,))
        self.sub_id = conn.execute("SELECT id FROM subscriptions WHERE user_id=?", (self.user_id,)).fetchone()[0]
        
        # Add exactly 2 questions
        conn.execute("""
            INSERT INTO questions (tractate_id, external_id, question_text, question_type, start_daf, end_daf)
            VALUES (1, 'ext_q1', 'שאלה 1', 'רש"י', 2.0, 2.0)
        """)
        conn.execute("""
            INSERT INTO questions (tractate_id, external_id, question_text, question_type, start_daf, end_daf)
            VALUES (1, 'ext_q2', 'שאלה 2', 'רש"י', 2.0, 2.0)
        """)
        
        conn.commit()
        conn.close()

    def tearDown(self):
        if os.path.exists(self.db_path):
            try:
                import gc
                gc.collect()
                # os.remove(self.db_path)
            except:
                pass

    def test_no_duplicate_questions(self):
        phone = '0509999999'
        
        # Step 1: Send first question
        conn = get_conn()
        sub = conn.execute("SELECT s.*, t.name as tractate_name, u.phone, u.name as user_name FROM subscriptions s JOIN tractates t ON s.tractate_id = t.id JOIN users u ON s.user_id = u.id WHERE s.id=?", (self.sub_id,)).fetchone()
        conn.close()
        
        INBOX.clear()
        send_daily_questions(dict(sub))
        
        # Step 2: User responds 'כן'
        receive_sms(phone, "כן")
        conn = get_conn()
        user = conn.execute("SELECT * FROM users WHERE phone=?", (phone,)).fetchone()
        conn.close()
        
        handle_registered_user(phone, user, "כן")
        
        # Step 3: Verify no duplicates in DB
        conn = get_conn()
        sent = conn.execute("SELECT question_id FROM sent_questions WHERE subscription_id=? ORDER BY sent_at", (self.sub_id,)).fetchall()
        conn.close()
        
        sent_ids = [r[0] for r in sent]
        print(f"Sent Question IDs: {sent_ids}")
        
        self.assertEqual(len(sent_ids), 2, "Should have sent 2 questions")
        self.assertEqual(len(set(sent_ids)), 2, "Questions should be unique")

if __name__ == "__main__":
    unittest.main()
