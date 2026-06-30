from tests.helpers import create_user_with_subscription, get_last_sms
from scheduler import advance_subscription
from database import get_conn
from sms_service import set_live_mode

def test_subscription_completion_logic():
    phone = "0501112223"
    # Create sub
    user_id, sub_id = create_user_with_subscription(phone, "Finisher")
    
    conn = get_conn()
    # Set current_daf to the last daf and end_daf to same
    conn.execute("UPDATE subscriptions SET current_daf=5.0, end_daf=5.0, dafim_per_day=1.0 WHERE id=?", (sub_id,))
    conn.commit()
    conn.close()
    
    set_live_mode(True)
    
    # Trigger completion
    advance_subscription(sub_id, 1.0)
    
    conn = get_conn()
    sub = conn.execute("SELECT is_active, current_daf FROM subscriptions WHERE id=?", (sub_id,)).fetchone()
    assert sub['is_active'] == 0
    assert sub['current_daf'] == 5.0
    conn.close()
    
    last_sms = get_last_sms(phone)
    assert "מזל טוב" in last_sms or "סיימת" in last_sms
    
    set_live_mode(False)
