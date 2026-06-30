from tests.helpers import simulate_inbound, get_last_sms, create_user_with_subscription
from database import get_conn, float_to_daf_str
from simulation_system import USER_STATES

def test_option_1_manual_question():
    phone = "0501110001"
    create_user_with_subscription(phone, "User1")
    
    simulate_inbound(phone, "1")
    last_sms = get_last_sms(phone)
    assert "מסכת ברכות, דף ב ע\"א" in last_sms
    assert phone in USER_STATES
    assert USER_STATES[phone]['state'] == "AWAITING_ANSWER"

def test_option_2_update_daf():
    phone = "0501110002"
    user_id, sub_id = create_user_with_subscription(phone, "User2")
    
    simulate_inbound(phone, "2")
    assert "לאיזה דף הגעת" in get_last_sms(phone)
    
    simulate_inbound(phone, "ג ע\"ב")
    assert "עודכן ל-ג ע\"ב" in get_last_sms(phone)
    
    conn = get_conn()
    sub = conn.execute("SELECT current_daf FROM subscriptions WHERE id=?", (sub_id,)).fetchone()
    assert sub['current_daf'] == 3.5
    conn.close()

def test_option_3_pause():
    phone = "0501110003"
    user_id, sub_id = create_user_with_subscription(phone, "User3")
    
    simulate_inbound(phone, "3")
    assert "לכמה ימים תרצה להקפיא" in get_last_sms(phone)
    
    simulate_inbound(phone, "5")
    assert "הוקפא ל-5 ימים" in get_last_sms(phone)
    
    conn = get_conn()
    sub = conn.execute("SELECT pause_until FROM subscriptions WHERE id=?", (sub_id,)).fetchone()
    assert sub['pause_until'] is not None
    conn.close()

def test_option_4_resume():
    phone = "0501110004"
    user_id, sub_id = create_user_with_subscription(phone, "User4")
    
    # First pause it
    conn = get_conn()
    conn.execute("UPDATE subscriptions SET pause_until='2026-01-01' WHERE id=?", (sub_id,))
    conn.commit()
    conn.close()
    
    simulate_inbound(phone, "4")
    assert "ההקפאה בוטלה" in get_last_sms(phone)
    
    conn = get_conn()
    sub = conn.execute("SELECT pause_until FROM subscriptions WHERE id=?", (sub_id,)).fetchone()
    assert sub['pause_until'] is None
    conn.close()

def test_option_5_change_hour():
    phone = "0501110005"
    user_id, sub_id = create_user_with_subscription(phone, "User5")
    
    simulate_inbound(phone, "5")
    assert "באיזו שעה תרצה לקבל" in get_last_sms(phone)
    
    simulate_inbound(phone, "20")
    assert "עודכנה ל-20:00" in get_last_sms(phone)
    
    conn = get_conn()
    sub = conn.execute("SELECT send_hour FROM subscriptions WHERE id=?", (sub_id,)).fetchone()
    assert sub['send_hour'] == 20
    conn.close()

def test_option_7_unsubscribe():
    phone = "0501110007"
    user_id, sub_id = create_user_with_subscription(phone, "User7")
    
    simulate_inbound(phone, "7")
    assert "הסרתך מהשירות בוצעה בהצלחה" in get_last_sms(phone)
    
    conn = get_conn()
    sub = conn.execute("SELECT is_active FROM subscriptions WHERE id=?", (sub_id,)).fetchone()
    assert sub['is_active'] == 0
    conn.close()

def test_option_8_support():
    phone = "0501110008"
    user_id, _ = create_user_with_subscription(phone, "User8")
    
    simulate_inbound(phone, "8")
    assert "במה נוכל לעזור" in get_last_sms(phone)
    
    simulate_inbound(phone, "1") # Bug
    assert "אנא כתוב את תוכן הפנייה" in get_last_sms(phone)
    
    simulate_inbound(phone, "יש לי תקלה")
    assert "הפנייה שלך התקבלה" in get_last_sms(phone)
    
    conn = get_conn()
    req = conn.execute("SELECT * FROM support_requests WHERE user_id=?", (user_id,)).fetchone()
    assert req is not None
    assert req['category'] == "באג/תקלה"
    assert req['message'] == "יש לי תקלה"
    conn.close()

def test_return_to_menu_with_zero():
    phone = "0501110009"
    create_user_with_subscription(phone, "User9")
    
    # Start an action (Update Daf)
    simulate_inbound(phone, "2")
    assert phone in USER_STATES
    
    # Send 0 to reset
    simulate_inbound(phone, "0")
    assert phone not in USER_STATES
    assert "בחר אפשרות" in get_last_sms(phone)
