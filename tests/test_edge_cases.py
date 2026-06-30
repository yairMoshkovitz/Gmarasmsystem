from tests.helpers import create_user_with_subscription, simulate_inbound, get_last_sms
from database import get_conn
from simulation_system import USER_STATES

def test_double_hour_input():
    """Verify hour 24 is treated as 0."""
    phone = "0509998886"
    simulate_inbound(phone, "אבי, רלו, תל אביב, 30")
    simulate_inbound(phone, "ברכות ב עד י")
    simulate_inbound(phone, "1, 24")
    
    conn = get_conn()
    user = conn.execute("SELECT id FROM users WHERE phone=?", (phone,)).fetchone()
    sub = conn.execute("SELECT send_hour FROM subscriptions WHERE user_id=?", (user['id'],)).fetchone()
    assert sub['send_hour'] == 0
    conn.close()

def test_punctuation_in_answer():
    """Verify that 'כן.' with period is accepted."""
    phone = "0509998885"
    create_user_with_subscription(phone, "Punct1")
    
    simulate_inbound(phone, "1")
    simulate_inbound(phone, "כן.") # With period
    
    conn = get_conn()
    q = conn.execute("SELECT responded_at FROM sent_questions ORDER BY sent_at DESC LIMIT 1").fetchone()
    assert q['responded_at'] is not None
    conn.close()

def test_long_message_truncation_logic():
    """Verify system handles very long messages without crashing (sms_service simulation)."""
    phone = "0509998884"
    long_msg = "א" * 1000
    simulate_inbound(phone, long_msg)
    # Should just return registration instructions or main menu
    assert "ברוך הבא" in get_last_sms(phone)
