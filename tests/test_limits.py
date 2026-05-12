from tests.helpers import create_user_with_subscription, simulate_inbound, get_last_sms, get_all_outgoing_sms
from database import get_conn
from sms_service import send_sms, set_live_mode

def test_daily_sms_limit_30():
    phone = "0505550001"
    user_id, _ = create_user_with_subscription(phone, "Limit1")
    
    conn = get_conn()
    conn.execute("DELETE FROM sms_log WHERE phone=?", (phone,))
    conn.commit()
    conn.close()

    # Send 30 messages.
    # The 30th call to send_sms should trigger the warning message.
    # Let's trace: 
    # msg 1: count 0 -> insert msg 1
    # ...
    # msg 29: count 28 -> insert msg 29
    # msg 30: count 29 -> insert msg 30
    # msg 31: count 30 -> trigger warning, insert warning, return False
    for i in range(30):
        send_sms(phone, f"Message {i+1}", user_id)
    
    # Message 31
    result = send_sms(phone, "Message 31", user_id)
    assert result is False

    all_msgs = get_all_outgoing_sms(phone)
    assert any("הגעת למגבלת ההודעות היומית" in m for m in all_msgs)

def test_max_5_subscriptions_limit():
    phone = "0505550002"
    from registration import register_user, subscribe
    user_id = register_user(phone, "Limit2")
    
    conn = get_conn()
    tractates = conn.execute("SELECT id FROM tractates LIMIT 6").fetchall()
    conn.close()
    
    # Add 5 subscriptions
    for i in range(5):
        subscribe(user_id, tractates[i]['id'], 2.0, 10.0, 1.0, 18)
    
    # Try to add 6th
    import pytest
    with pytest.raises(ValueError, match="ניתן להירשם לעד 5 מסכתות"):
        subscribe(user_id, tractates[5]['id'], 2.0, 10.0, 1.0, 18)

def test_invalid_hour_registration():
    phone = "0505550003"
    simulate_inbound(phone, "משה, כהן, בני ברק, 25")
    simulate_inbound(phone, "ברכות ב עד י")
    
    # Clear log to get clean last sms
    conn = get_conn()
    conn.execute("DELETE FROM sms_log WHERE phone=?", (phone,))
    conn.commit()
    conn.close()

    simulate_inbound(phone, "1, 25")
    assert "שעה לא תקינה" in get_last_sms(phone)

def test_daf_out_of_range_update():
    phone = "0505550004"
    user_id, sub_id = create_user_with_subscription(phone, "Limit4") # Range 2.0 - 10.0
    
    simulate_inbound(phone, "2") # Option 2: Update Daf
    simulate_inbound(phone, "טו") # Daf 15.0 - Out of range
    
    assert "מחוץ לטווח המנוי שלך" in get_last_sms(phone)
