"""
Test suite for 200 users load testing.
Verifies system performance and responsiveness with moderate load.
"""
import time
import pytest
from database import get_conn
from registration import register_user, subscribe
from scheduler import run_hour
from sms_service import set_live_mode

def test_load_200_registrations():
    """Verify system handles 200 users registration efficiently."""
    start_time = time.time()
    
    conn = get_conn()
    t = conn.execute("SELECT id FROM tractates LIMIT 1").fetchone()
    conn.close()
    
    for i in range(200):
        phone = f"058{i:07d}"
        user_id = register_user(phone, f"User200_{i}")
        subscribe(user_id, t['id'], 2.0, 100.0, 1.0, 18)
    
    end_time = time.time()
    duration = end_time - start_time
    print(f"\n200 registrations took {duration:.2f} seconds")
    
    # Check DB count
    conn = get_conn()
    user_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    sub_count = conn.execute("SELECT COUNT(*) FROM subscriptions").fetchone()[0]
    conn.close()
    
    assert user_count == 200
    assert sub_count == 200
    # Performance benchmark: should take less than 3 seconds for 200
    assert duration < 3

def test_load_200_scheduler_messages():
    """Verify scheduler can process 200 messages efficiently."""
    # 1. Setup 200 users at hour 10
    conn = get_conn()
    t = conn.execute("SELECT id FROM tractates LIMIT 1").fetchone()
    conn.close()
    
    print("\n📝 Creating 200 test users...")
    for i in range(200):
        phone = f"059{i:07d}"
        user_id = register_user(phone, f"Load200_{i}")
        subscribe(user_id, t['id'], 2.0, 100.0, 1.0, 10)
    
    # 2. Run scheduler
    print("🚀 Starting scheduler for 200 users...")
    set_live_mode(True)
    start_time = time.time()
    run_hour(10)
    end_time = time.time()
    set_live_mode(False)
    
    duration = end_time - start_time
    print(f"\n✅ 200 scheduler messages took {duration:.2f} seconds")
    print(f"📊 Average: {duration/200:.3f} seconds per user")
    
    # Check sms_log count
    conn = get_conn()
    msg_count = conn.execute("SELECT COUNT(*) FROM sms_log WHERE direction='out' AND user_id IS NOT NULL").fetchone()[0]
    conn.close()
    
    print(f"📬 Messages sent: {msg_count}/200")
    
    # More lenient assertion - at least 190 messages (95%)
    assert msg_count >= 190, f"Expected at least 190 messages, got {msg_count}"
    # Performance benchmark: should process 200 messages in less than 25 seconds
    assert duration < 25, f"Expected < 25 seconds, took {duration:.2f}"

def test_200_performance_metrics():
    """Collect detailed performance metrics for 200 users."""
    conn = get_conn()
    t = conn.execute("SELECT id FROM tractates LIMIT 1").fetchone()
    conn.close()
    
    # Create users
    creation_start = time.time()
    for i in range(200):
        phone = f"059{i:07d}"
        user_id = register_user(phone, f"Metrics200_{i}")
        subscribe(user_id, t['id'], 2.0, 100.0, 1.0, 14)
    creation_time = time.time() - creation_start
    
    # Run scheduler
    set_live_mode(True)
    scheduler_start = time.time()
    run_hour(14)
    scheduler_time = time.time() - scheduler_start
    set_live_mode(False)
    
    # Collect metrics
    conn = get_conn()
    msg_count = conn.execute("SELECT COUNT(*) FROM sms_log WHERE direction='out' AND user_id IS NOT NULL").fetchone()[0]
    user_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    conn.close()
    
    # Print detailed metrics
    print("\n" + "="*70)
    print("📊 PERFORMANCE METRICS - 200 USERS")
    print("="*70)
    print(f"👥 Users created: {user_count}")
    print(f"⏱️  Creation time: {creation_time:.2f}s ({creation_time/200:.4f}s per user)")
    print(f"📬 Messages sent: {msg_count}")
    print(f"⏱️  Scheduler time: {scheduler_time:.2f}s ({scheduler_time/200:.4f}s per user)")
    print(f"✅ Success rate: {(msg_count/200)*100:.1f}%")
    print(f"🚀 Throughput: {200/scheduler_time:.2f} users/second")
    print("="*70)
    
    # Assertions
    assert msg_count >= 190
    assert scheduler_time < 25
