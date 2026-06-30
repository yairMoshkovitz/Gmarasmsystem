
from scheduler import advance_all_subscriptions_daily, run_hour
from database import get_conn
from tests.helpers import create_user_with_subscription
from sms_service import set_live_mode

def test_daily_advancement_at_2355():
    """
    Test that subscriptions are advanced ONLY at 23:55 and not during regular question hours.
    """
    phone = "0509990001"
    # User starts at Daf 2.0
    user_id, sub_id = create_user_with_subscription(phone, "AdvTest", "ברכות")
    
    conn = get_conn()
    sub_before = conn.execute("SELECT current_daf FROM subscriptions WHERE id=?", (sub_id,)).fetchone()
    assert sub_before['current_daf'] == 2.0
    conn.close()

    set_live_mode(True)
    
    # 1. Run at regular hour (e.g., 18:00) - Should NOT advance daf anymore
    # (In the new logic, daf advancement was removed from send_next_question_or_finish)
    run_hour(18)
    
    conn = get_conn()
    sub_after_18 = conn.execute("SELECT current_daf FROM subscriptions WHERE id=?", (sub_id,)).fetchone()
    assert sub_after_18['current_daf'] == 2.0, "Daf should NOT advance during regular hour"
    conn.close()
    
    # 2. Trigger daily advancement manually (simulating 23:55)
    # First, cleanup other active subs to avoid DB locks from completing many subs at once in test env
    conn = get_conn()
    conn.execute("UPDATE subscriptions SET is_active=0 WHERE is_active=1 AND user_id != ?", (user_id,))
    conn.commit()
    conn.close()
    
    advanced, completed = advance_all_subscriptions_daily()
    assert advanced >= 1
    
    conn = get_conn()
    sub_after_adv = conn.execute("SELECT current_daf FROM subscriptions WHERE id=?", (sub_id,)).fetchone()
    assert sub_after_adv['current_daf'] == 3.0, "Daf should advance after daily advancement call"
    conn.close()
    
    set_live_mode(False)
    print("✅ Daily advancement test passed!")

if __name__ == "__main__":
    test_daily_advancement_at_2355()
