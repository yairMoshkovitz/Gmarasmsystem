"""
test_performance.py - Performance benchmarks for SMS response time
"""
import time
import pytest
from database import get_conn
from registration import register_user, subscribe
from scheduler import run_hour, send_daily_questions
from sms_service import set_live_mode
from simulation_system import handle_registered_user


def test_sms_response_time_single_user():
    """Measure response time for a single user receiving SMS."""
    # Setup
    phone = "0501234567"
    conn = get_conn()
    t = conn.execute("SELECT id FROM tractates LIMIT 1").fetchone()
    conn.close()
    
    user_id = register_user(phone, "PerfTest", "User", "TestCity", 25)
    subscribe(user_id, t['id'], 2.0, 100.0, 1.0, 18)
    
    # Measure time to send question
    conn = get_conn()
    sub = conn.execute("""
        SELECT s.*, t.name as tractate_name, u.phone, u.name as user_name
        FROM subscriptions s
        JOIN tractates t ON s.tractate_id = t.id
        JOIN users u ON s.user_id = u.id
        WHERE s.user_id = ?
    """, (user_id,)).fetchone()
    conn.close()
    
    start_time = time.time()
    send_daily_questions(dict(sub))
    end_time = time.time()
    
    response_time = (end_time - start_time) * 1000  # Convert to milliseconds
    print(f"\nSingle user SMS response time: {response_time:.2f}ms")
    
    # Should respond in less than 100ms for local operations
    assert response_time < 100


def test_parallel_sms_throughput():
    """Measure throughput of parallel SMS sending (100 users)."""
    # Setup 100 users
    conn = get_conn()
    t = conn.execute("SELECT id FROM tractates LIMIT 1").fetchone()
    conn.close()
    
    user_ids = []
    for i in range(100):
        phone = f"0551{i:06d}"
        user_id = register_user(phone, f"Perf{i}", "Test", "City", 25)
        subscribe(user_id, t['id'], 2.0, 100.0, 1.0, 15)
        user_ids.append(user_id)
    
    # Measure parallel sending
    set_live_mode(True)
    start_time = time.time()
    run_hour(15)
    end_time = time.time()
    set_live_mode(False)
    
    duration = end_time - start_time
    throughput = 100 / duration  # messages per second
    
    print(f"\n100 users processed in {duration:.2f} seconds")
    print(f"Throughput: {throughput:.2f} messages/second")
    
    # With parallel processing, should handle at least 10 messages/second
    assert throughput > 10
    # Should complete in less than 10 seconds
    assert duration < 10


def test_webhook_response_time():
    """Measure webhook processing response time."""
    # Setup user
    phone = "0502345678"
    conn = get_conn()
    user = conn.execute("SELECT * FROM users WHERE phone = ?", (phone,)).fetchone()
    
    if not user:
        t = conn.execute("SELECT id FROM tractates LIMIT 1").fetchone()
        conn.close()
        user_id = register_user(phone, "WebhookTest", "User", "City", 25)
        subscribe(user_id, t['id'], 2.0, 100.0, 1.0, 18)
        
        conn = get_conn()
        user = conn.execute("SELECT * FROM users WHERE phone = ?", (phone,)).fetchone()
    
    conn.close()
    
    # Measure webhook processing time
    start_time = time.time()
    handle_registered_user(phone, dict(user), "1")  # Request manual question
    end_time = time.time()
    
    response_time = (end_time - start_time) * 1000
    print(f"\nWebhook processing time: {response_time:.2f}ms")
    
    # Webhook should respond in less than 200ms
    assert response_time < 200


def test_database_query_performance():
    """Measure database query performance for common operations."""
    # Setup some data
    conn = get_conn()
    t = conn.execute("SELECT id FROM tractates LIMIT 1").fetchone()
    
    # Test 1: User lookup
    start = time.time()
    for i in range(100):
        phone = f"0553{i:06d}"
        conn.execute("SELECT * FROM users WHERE phone = ?", (phone,)).fetchone()
    query1_time = (time.time() - start) * 1000
    
    # Test 2: Subscription lookup
    start = time.time()
    for i in range(100):
        conn.execute("""
            SELECT s.*, t.name as tractate_name
            FROM subscriptions s
            JOIN tractates t ON s.tractate_id = t.id
            WHERE s.is_active = 1
            LIMIT 10
        """).fetchall()
    query2_time = (time.time() - start) * 1000
    
    conn.close()
    
    print(f"\n100 user lookups: {query1_time:.2f}ms ({query1_time/100:.2f}ms avg)")
    print(f"100 subscription queries: {query2_time:.2f}ms ({query2_time/100:.2f}ms avg)")
    
    # Each query should average less than 5ms
    assert query1_time / 100 < 5
    assert query2_time / 100 < 10


def test_state_management_performance():
    """Measure performance of DB-backed state management."""
    from state_manager import set_user_state, get_user_state, clear_user_state
    
    phone = "0504567890"
    
    # Test write performance
    start = time.time()
    for i in range(100):
        set_user_state(phone, "AWAITING_ANSWER", queue=[1, 2, 3], sub_id=i)
    write_time = (time.time() - start) * 1000
    
    # Test read performance
    start = time.time()
    for i in range(100):
        state = get_user_state(phone)
    read_time = (time.time() - start) * 1000
    
    # Test clear performance
    start = time.time()
    clear_user_state(phone)
    clear_time = (time.time() - start) * 1000
    
    print(f"\n100 state writes: {write_time:.2f}ms ({write_time/100:.2f}ms avg)")
    print(f"100 state reads: {read_time:.2f}ms ({read_time/100:.2f}ms avg)")
    print(f"State clear: {clear_time:.2f}ms")
    
    # State operations should be fast
    assert write_time / 100 < 10  # Less than 10ms per write
    assert read_time / 100 < 5    # Less than 5ms per read
