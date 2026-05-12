from tests.helpers import create_user_with_subscription, get_last_sms
from scheduler import run_hour
from sms_service import set_live_mode
from datetime import datetime, timedelta
import pytest

# Mocking get_israel_time to control day of week in tests
def test_friday_after_16_skips(monkeypatch):
    phone = "0506660001"
    create_user_with_subscription(phone, "Shab1") # Default hour 18
    
    # Mock Friday 18:00
    friday_18 = datetime(2024, 3, 22, 18, 0) # 22 March 2024 is Friday
    assert friday_18.weekday() == 4
    
    import scheduler
    monkeypatch.setattr(scheduler, "get_israel_time", lambda: friday_18)
    
    set_live_mode(True)
    run_hour(18)
    assert get_last_sms(phone) is None # Should be skipped due to Shabbat logic
    set_live_mode(False)

def test_friday_16_triggers_all_evening(monkeypatch):
    phone = "0506660002"
    create_user_with_subscription(phone, "Shab2") # Default hour 18
    
    # Mock Friday 16:00
    friday_16 = datetime(2024, 3, 22, 16, 0)
    import scheduler
    monkeypatch.setattr(scheduler, "get_israel_time", lambda: friday_16)
    
    # Clear log
    from database import get_conn
    conn = get_conn()
    conn.execute("DELETE FROM sms_log WHERE phone=?", (phone,))
    conn.commit()
    conn.close()

    set_live_mode(True)
    run_hour(16)
    # Hour 16 should trigger hour 18 subscription on Friday
    assert "ברכות" in get_last_sms(phone)
    set_live_mode(False)

def test_saturday_before_21_skips(monkeypatch):
    phone = "0506660003"
    create_user_with_subscription(phone, "Shab3")
    
    # Mock Saturday 10:00
    saturday_10 = datetime(2024, 3, 23, 10, 0) # 23 March 2024 is Saturday
    assert saturday_10.weekday() == 5
    
    import scheduler
    monkeypatch.setattr(scheduler, "get_israel_time", lambda: saturday_10)
    
    # Clear log
    from database import get_conn
    conn = get_conn()
    conn.execute("DELETE FROM sms_log WHERE phone=?", (phone,))
    conn.commit()
    conn.close()

    set_live_mode(True)
    run_hour(10)
    assert get_last_sms(phone) is None
    set_live_mode(False)

def test_saturday_21_triggers_all_shabbat(monkeypatch):
    phone = "0506660004"
    from registration import register_user, subscribe
    from database import get_conn
    user_id = register_user(phone, "Shab4")
    conn = get_conn()
    # Explicitly use ברכות to avoid issues with seed data
    t = conn.execute("SELECT id FROM tractates WHERE name='ברכות'").fetchone()
    subscribe(user_id, t[0], 2.0, 10.0, 1.0, 10) # 10:00 AM
    conn.close()
    
    # Mock Saturday 21:00
    saturday_21 = datetime(2024, 3, 23, 21, 0)
    import scheduler
    monkeypatch.setattr(scheduler, "get_israel_time", lambda: saturday_21)
    
    # Clear log
    conn = get_conn()
    conn.execute("DELETE FROM sms_log WHERE phone=?", (phone,))
    conn.commit()
    conn.close()

    set_live_mode(True)
    run_hour(21)
    # Hour 21 should trigger the missed 10:00 AM subscription
    assert "ברכות" in get_last_sms(phone)
    set_live_mode(False)
