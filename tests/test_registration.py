from tests.helpers import simulate_inbound, get_last_sms, get_all_outgoing_sms
from database import get_conn
from registration import get_template

def test_full_registration_flow():
    phone = "0501234567"
    
    # Step 1: Personal Details
    simulate_inbound(phone, "משה, כהן, בני ברק, 25")
    
    # Verify Step 1
    conn = get_conn()
    user = conn.execute("SELECT * FROM users WHERE phone=?", (phone,)).fetchone()
    assert user is not None
    assert user['name'] == "משה"
    conn.close()
    
    all_msgs = get_all_outgoing_sms(phone)
    assert any("מעולה משה" in m for m in all_msgs)

    # Step 2: Tractate Details
    simulate_inbound(phone, "ברכות ב ע\"א עד י ע\"ב")
    
    all_msgs = get_all_outgoing_sms(phone)
    assert any("להגדיר את ההספק היומי" in m for m in all_msgs)

    # Step 3: Rate and Hour
    simulate_inbound(phone, "1, 18")
    
    all_msgs = get_all_outgoing_sms(phone)
    assert any("מצויין משה נרשמת" in m for m in all_msgs)

def test_registration_with_gimatriya():
    phone = "0501112222"
    simulate_inbound(phone, "דוד, לוי, ירושלים, 30")
    simulate_inbound(phone, "ברכות כ עד ל")
    simulate_inbound(phone, "1, 10")
    
    conn = get_conn()
    user = conn.execute("SELECT id FROM users WHERE phone=?", (phone,)).fetchone()
    sub = conn.execute("SELECT * FROM subscriptions WHERE user_id=?", (user['id'],)).fetchone()
    assert sub['start_daf'] == 20.0
    conn.close()

def test_registration_masechta_not_found():
    phone = "0503334444"
    simulate_inbound(phone, "ישראל, ישראלי, חולון, 40")
    # We are now in Step 2 state
    simulate_inbound(phone, "מסכת לא קיימת ב ע\"א עד י")
    
    last_sms = get_last_sms(phone)
    assert "לא נמצאה" in last_sms

def test_registration_masechta_not_supported():
    phone = "0505556666"
    simulate_inbound(phone, "יעקב, אבינו, חברון, 100")
    # Step 2
    simulate_inbound(phone, "פאה א עד י")
    
    last_sms = get_last_sms(phone)
    assert "אין שאלות עבור מסכת פאה" in last_sms
