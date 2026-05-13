import unittest
from app import app
from database import init_db, get_conn, set_setting, get_setting
from sms_service import get_live_mode, set_live_mode
import time

class TestLiveModeToggle(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        self.client = app.test_client()
        init_db()
        # Clean sms_log for clean testing
        conn = get_conn()
        conn.execute("DELETE FROM sms_log")
        conn.commit()
        conn.close()
        # Ensure we start with LIVE mode OFF
        set_live_mode(False)

    def test_admin_toggle_on(self):
        admin_phone = "0584555723"
        # Simulate incoming SMS from admin to turn LIVE ON
        response = self.client.post('/send', json={
            "phone": admin_phone,
            "message": "LIVE ON"
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(get_live_mode())
        
        # Check if confirmation was logged in sms_log
        conn = get_conn()
        log = conn.execute("SELECT * FROM sms_log WHERE phone=? AND direction='out' ORDER BY sent_at DESC LIMIT 1", (admin_phone,)).fetchone()
        conn.close()
        self.assertIn("הופעל בהצלחה", log['message'])

    def test_admin_toggle_off(self):
        admin_phone = "0584555723"
        set_live_mode(True)
        # Simulate incoming SMS from admin to turn LIVE OFF
        response = self.client.post('/send', json={
            "phone": admin_phone,
            "message": "לייב כבוי"
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(get_live_mode())
        
        # Check if confirmation was logged
        conn = get_conn()
        log = conn.execute("SELECT * FROM sms_log WHERE phone=? AND direction='out' ORDER BY sent_at DESC LIMIT 1", (admin_phone,)).fetchone()
        conn.close()
        self.assertIn("כובה", log['message'])

    def test_non_admin_cannot_toggle(self):
        other_phone = "0541234567"
        response = self.client.post('/send', json={
            "phone": other_phone,
            "message": "LIVE ON"
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(get_live_mode())

if __name__ == '__main__':
    unittest.main()
