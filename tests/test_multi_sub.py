from tests.helpers import simulate_inbound, get_last_sms, create_user_with_subscription, get_all_outgoing_sms
from database import get_conn
from simulation_system import USER_STATES

def test_multi_sub_manual_question_selection():
    phone = "0504440001"
    user_id, _ = create_user_with_subscription(phone, "Multi1", "ברכות")
    
    # Add second subscription
    conn = get_conn()
    t_shabbat = conn.execute("SELECT id FROM tractates WHERE name='שבת'").fetchone()
    from registration import subscribe
    subscribe(user_id, t_shabbat['id'], 2.0, 10.0, 1.0, 18)
    conn.close()
    
    simulate_inbound(phone, "1")
    last_msg = get_last_sms(phone)
    assert "יש לך מספר מסלולי לימוד פעילים" in last_msg
    assert "1. ברכות" in last_msg
    assert "2. שבת" in last_msg
    assert USER_STATES[phone]['state'] == "AWAITING_SUB_SELECTION_FOR_QUESTION"
    
    simulate_inbound(phone, "1")
    assert "ברכות" in get_last_sms(phone)
    assert USER_STATES[phone]['state'] == "AWAITING_ANSWER"

def test_multi_sub_scheduler_queue():
    phone = "0504440002"
    user_id, _ = create_user_with_subscription(phone, "Multi2", "ברכות")
    
    conn = get_conn()
    t_shabbat = conn.execute("SELECT id FROM tractates WHERE name='שבת'").fetchone()
    from registration import subscribe
    subscribe(user_id, t_shabbat['id'], 2.0, 10.0, 1.0, 18)
    conn.close()
    
    from scheduler import run_hour
    from sms_service import set_live_mode
    set_live_mode(True)
    run_hour(18)
    set_live_mode(False)
    
    last_msg = get_last_sms(phone)
    assert "הגיע הזמן ללימוד" in last_msg
    
    # Select first one
    simulate_inbound(phone, "1")
    
    # Answer until done with first sub
    simulate_inbound(phone, "כן")
    simulate_inbound(phone, "כן")
    
    # Should automatically prompt for the next one or move to it
    all_msgs = get_all_outgoing_sms(phone)
    # The system either sends "כל הכבוד" menu or "מצוין! סיימת... ממשיכים ל..."
    assert any("סיימת את ברכות" in m for m in all_msgs)
    assert any("שבת" in m for m in all_msgs)
