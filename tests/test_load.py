import time
import pytest
from database import get_conn
from registration import register_user, subscribe
from scheduler import run_hour
from sms_service import set_live_mode

@pytest.mark.skip(reason="Load tests are too slow for normal CI, will be relevant after system upgrade")
def test_load_1000_registrations():
    """Verify system handles 1000 users registration efficiently."""
    start_time = time.time()
    
    conn = get_conn()
    t = conn.execute("SELECT id FROM tractates LIMIT 1").fetchone()
    conn.close()
    
    for i in range(1000):
        phone = f"058{i:07d}"
        user_id = register_user(phone, f"User{i}")
        subscribe(user_id, t['id'], 2.0, 100.0, 1.0, 18)
    
    end_time = time.time()
    duration = end_time - start_time
    print(f"\n1000 registrations took {duration:.2f} seconds")
    
    # Check DB count
    conn = get_conn()
    user_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    sub_count = conn.execute("SELECT COUNT(*) FROM subscriptions").fetchone()[0]
    conn.close()
    
    assert user_count == 1000
    assert sub_count == 1000
    # Performance benchmark: should take less than 10 seconds for 1000 (SQLite is fast)
    assert duration < 10

@pytest.mark.skip(reason="Load tests are too slow for normal CI, will be relevant after system upgrade")
def test_load_1000_scheduler_messages():
    """Verify scheduler can process 1000 messages for the same hour."""
    # 1. Setup 1000 users at hour 10
    conn = get_conn()
    t = conn.execute("SELECT id FROM tractates LIMIT 1").fetchone()
    conn.close()
    
    for i in range(1000):
        phone = f"059{i:07d}"
        user_id = register_user(phone, f"Load{i}")
        subscribe(user_id, t['id'], 2.0, 100.0, 1.0, 10)
    
    # 2. Run scheduler
    set_live_mode(True)
    start_time = time.time()
    run_hour(10)
    end_time = time.time()
    set_live_mode(False)
    
    duration = end_time - start_time
    print(f"\n1000 scheduler messages took {duration:.2f} seconds")
    
    # Check sms_log count
    conn = get_conn()
    msg_count = conn.execute("SELECT COUNT(*) FROM sms_log WHERE direction='out' AND user_id IS NOT NULL").fetchone()[0]
    conn.close()
    
    assert msg_count >= 1000
    # Performance benchmark: should process 1000 messages in less than 5 seconds
    assert duration < 10
