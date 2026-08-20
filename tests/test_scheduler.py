from tests.helpers import create_user_with_subscription, get_last_sms, simulate_inbound
from scheduler import run_hour, get_due_subscriptions
from database import get_conn
from sms_service import set_live_mode
from datetime import date, timedelta

def test_scheduler_triggers_correctly():
    phone = "0502220001"
    create_user_with_subscription(phone, "Sched1") # Default hour is 18
    
    # 1. Run at wrong hour
    set_live_mode(True) # Force live mode to enable scheduler execution
    run_hour(10)
    # Registration success might be there, but no question
    last = get_last_sms(phone)
    if last:
        assert "מסכת ברכות, דף ב ע\"א" not in last
    
    # 2. Run at correct hour
    run_hour(18)
    assert "מסכת ברכות, דף ב ע\"א" in get_last_sms(phone)
    set_live_mode(False)

def test_scheduler_same_day_protection():
    phone = "0502220002"
    user_id, sub_id = create_user_with_subscription(phone, "Sched2")
    
    set_live_mode(True)
    # Clear registration message
    conn = get_conn()
    conn.execute("DELETE FROM sms_log WHERE phone=?", (phone,))
    conn.commit()
    conn.close()

    # System daily limit for questions is 2.
    # run_hour sends the first question only (per-subscription daily limit)
    run_hour(18)
    assert "ברכות" in get_last_sms(phone)

    # Verify it's in sent_questions (1 question sent so far)
    conn = get_conn()
    count = conn.execute("SELECT COUNT(*) FROM sent_questions WHERE user_id=? AND subscription_id=?", (user_id, sub_id)).fetchone()[0]
    assert count == 1

    # Second question is triggered by user ANSWERING the first (not by another run_hour)
    simulate_inbound(phone, "כן")
    assert "ברכות" in get_last_sms(phone)

    count = conn.execute("SELECT COUNT(*) FROM sent_questions WHERE user_id=? AND subscription_id=?", (user_id, sub_id)).fetchone()[0]
    assert count == 2
    conn.close()

    # Clear SMS log to verify protection against a third question
    conn = get_conn()
    conn.execute("DELETE FROM sms_log WHERE phone=?", (phone,))
    conn.commit()
    conn.close()

    # Answering second question should give closure (daily limit reached)
    simulate_inbound(phone, "כן")

    last = get_last_sms(phone)
    assert last is not None
    # We should NOT get a question, we should get the closure message
    assert "תמשיך בהתמדה" in last
    assert "יודע את התשובה?" not in last
    
    set_live_mode(False)

def test_scheduler_paused_subscription():
    phone = "0502220003"
    user_id, sub_id = create_user_with_subscription(phone, "Sched3")
    
    # Clear log to be sure
    conn = get_conn()
    conn.execute("DELETE FROM sms_log WHERE phone=?", (phone,))
    conn.commit()
    conn.close()

    # Pause it until tomorrow
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    conn = get_conn()
    conn.execute("UPDATE subscriptions SET pause_until=? WHERE id=?", (tomorrow, sub_id))
    conn.commit()
    conn.close()
    
    set_live_mode(True)
    run_hour(18)
    assert get_last_sms(phone) is None
    set_live_mode(False)

def test_paused_subscription_does_not_advance_daf():
    """
    Regression: advance_all_subscriptions_daily used to advance current_daf
    for paused subscriptions too, because its query only checked is_active
    and ignored pause_until. That silently un-froze the study range (the
    'page' kept moving forward) even though send_sms was correctly skipped.
    """
    from scheduler import advance_all_subscriptions_daily

    phone = "0502220005"
    user_id, sub_id = create_user_with_subscription(phone, "Sched5")

    conn = get_conn()
    original = conn.execute("SELECT current_daf FROM subscriptions WHERE id=?", (sub_id,)).fetchone()
    original_daf = original["current_daf"]
    conn.close()

    # Freeze for a week
    future = (date.today() + timedelta(days=7)).isoformat()
    conn = get_conn()
    conn.execute("UPDATE subscriptions SET pause_until=? WHERE id=?", (future, sub_id))
    conn.commit()
    conn.close()

    advance_all_subscriptions_daily()

    conn = get_conn()
    still = conn.execute("SELECT current_daf FROM subscriptions WHERE id=?", (sub_id,)).fetchone()
    conn.close()
    assert still["current_daf"] == original_daf

    # Once the pause expires, advancement should resume normally
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    conn = get_conn()
    conn.execute("UPDATE subscriptions SET pause_until=? WHERE id=?", (yesterday, sub_id))
    conn.commit()
    conn.close()

    advance_all_subscriptions_daily()

    conn = get_conn()
    resumed = conn.execute("SELECT current_daf FROM subscriptions WHERE id=?", (sub_id,)).fetchone()
    conn.close()
    assert resumed["current_daf"] == original_daf + 1.0

def test_advance_subscription_logic():
    phone = "0502220004"
    # Create with explicit tractate name
    user_id, sub_id = create_user_with_subscription(phone, "Sched4", "ברכות")
    
    from tests.helpers import simulate_inbound
    from scheduler import send_next_question_or_finish
    
    conn = get_conn()
    # Join with tractates to get tractate_name
    sub = conn.execute(
        "SELECT s.*, t.name as tractate_name, u.phone, u.name as user_name "
        "FROM subscriptions s "
        "JOIN tractates t ON s.tractate_id = t.id "
        "JOIN users u ON s.user_id = u.id "
        "WHERE s.id=?", (sub_id,)
    ).fetchone()
    conn.close()
    
    # Clear log to get clean results
    conn = get_conn()
    conn.execute("DELETE FROM sms_log WHERE phone=?", (phone,))
    conn.commit()
    conn.close()

    # Manual trigger of question
    send_next_question_or_finish(dict(sub))
    
    # Answer 2 questions (daily limit)
    simulate_inbound(phone, "כן")
    simulate_inbound(phone, "כן")

    # Daf advancement happens at 23:55 nightly, not immediately on answer
    from scheduler import advance_all_subscriptions_daily
    advance_all_subscriptions_daily()

    # Verify current_daf advanced
    conn = get_conn()
    updated_sub = conn.execute("SELECT current_daf FROM subscriptions WHERE id=?", (sub_id,)).fetchone()
    # Started at 2.0, rate 1.0 -> should be 3.0
    assert updated_sub['current_daf'] == 3.0
    conn.close()
