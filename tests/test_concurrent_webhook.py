"""
Test suite for concurrent webhook processing during scheduler runs.
Verifies that the system can receive and process incoming SMS while scheduler is running.
"""
import time
import threading
import pytest
from database import get_conn
from registration import register_user, subscribe
from scheduler import run_hour
from sms_service import set_live_mode, receive_sms
from simulation_system import handle_registered_user

def test_webhook_during_200_user_scheduler():
    """Verify system can process webhooks while scheduler runs with 200 users."""
    # 1. Setup 200 users
    conn = get_conn()
    t = conn.execute("SELECT id FROM tractates LIMIT 1").fetchone()
    conn.close()
    
    print("\n📝 Creating 200 test users...")
    test_users = []
    for i in range(200):
        phone = f"059{i:07d}"
        user_id = register_user(phone, f"Concurrent200_{i}")
        subscribe(user_id, t['id'], 2.0, 100.0, 1.0, 12)
        test_users.append(phone)
    
    # 2. Create a separate user for webhook testing
    webhook_phone = "0521234567"
    webhook_user_id = register_user(webhook_phone, "WebhookTester")
    subscribe(webhook_user_id, t['id'], 2.0, 100.0, 1.0, 12)
    
    # 3. Run scheduler in background thread
    scheduler_done = threading.Event()
    scheduler_error = []
    
    def run_scheduler():
        try:
            print("🚀 Starting scheduler in background...")
            set_live_mode(True)
            run_hour(12)
            set_live_mode(False)
            print("✅ Scheduler completed")
        except Exception as e:
            scheduler_error.append(e)
        finally:
            scheduler_done.set()
    
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    
    # 4. Wait a bit for scheduler to start processing
    time.sleep(2)
    
    # 5. Send webhook requests during scheduler run
    webhook_responses = []
    webhook_errors = []
    
    print("📨 Sending webhook requests during scheduler run...")
    for i in range(5):
        try:
            time.sleep(1)  # Space out requests
            receive_sms(webhook_phone, f"Test message {i+1}")
            response = handle_registered_user(webhook_phone, f"Test message {i+1}")
            webhook_responses.append(response)
            print(f"  ✓ Webhook {i+1}/5 processed")
        except Exception as e:
            webhook_errors.append(e)
            print(f"  ✗ Webhook {i+1}/5 failed: {e}")
    
    # 6. Wait for scheduler to complete (with timeout)
    scheduler_done.wait(timeout=60)
    
    # 7. Verify results
    print("\n" + "="*70)
    print("📊 CONCURRENT WEBHOOK TEST RESULTS")
    print("="*70)
    print(f"🚀 Scheduler completed: {scheduler_done.is_set()}")
    print(f"📬 Webhooks sent: 5")
    print(f"✅ Webhooks processed: {len(webhook_responses)}")
    print(f"❌ Webhook errors: {len(webhook_errors)}")
    if scheduler_error:
        print(f"⚠️  Scheduler errors: {scheduler_error}")
    print("="*70)
    
    # Assertions
    assert scheduler_done.is_set(), "Scheduler did not complete in time"
    assert len(scheduler_error) == 0, f"Scheduler had errors: {scheduler_error}"
    assert len(webhook_responses) >= 4, f"Expected at least 4 webhooks processed, got {len(webhook_responses)}"
    assert len(webhook_errors) <= 1, f"Too many webhook errors: {len(webhook_errors)}"

def test_multiple_webhooks_rapid_fire():
    """Test rapid webhook processing (stress test)."""
    # Create a test user
    phone = "0527654321"
    user_id = register_user(phone, "RapidTester")
    
    conn = get_conn()
    t = conn.execute("SELECT id FROM tractates LIMIT 1").fetchone()
    conn.close()
    subscribe(user_id, t['id'], 2.0, 100.0, 1.0, 15)
    
    # Send first question to get into AWAITING_ANSWER state
    set_live_mode(False)
    run_hour(15)
    
    # Now send rapid-fire responses
    print("\n🔥 Sending 10 rapid-fire webhooks...")
    start_time = time.time()
    responses = []
    errors = []
    
    for i in range(10):
        try:
            receive_sms(phone, "כן")
            response = handle_registered_user(phone, "כן")
            responses.append(response)
        except Exception as e:
            errors.append(e)
    
    duration = time.time() - start_time
    
    print(f"\n✅ Processed {len(responses)}/10 webhooks in {duration:.2f} seconds")
    print(f"📊 Average: {duration/10:.3f} seconds per webhook")
    print(f"❌ Errors: {len(errors)}")
    
    # Assertions
    assert len(responses) >= 8, f"Expected at least 8 successful responses, got {len(responses)}"
    assert duration < 5, f"Expected < 5 seconds for 10 webhooks, took {duration:.2f}"

def test_webhook_response_time_during_load():
    """Measure webhook response time during scheduler load."""
    # Setup 100 users for moderate load
    conn = get_conn()
    t = conn.execute("SELECT id FROM tractates LIMIT 1").fetchone()
    conn.close()
    
    print("\n📝 Creating 100 users for load test...")
    for i in range(100):
        phone = f"059{i:07d}"
        user_id = register_user(phone, f"LoadTest_{i}")
        subscribe(user_id, t['id'], 2.0, 100.0, 1.0, 16)
    
    # Create webhook test user
    webhook_phone = "0523456789"
    webhook_user_id = register_user(webhook_phone, "ResponseTimer")
    subscribe(webhook_user_id, t['id'], 2.0, 100.0, 1.0, 16)
    
    # Start scheduler
    scheduler_done = threading.Event()
    
    def run_scheduler():
        set_live_mode(True)
        run_hour(16)
        set_live_mode(False)
        scheduler_done.set()
    
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    
    # Wait for scheduler to start
    time.sleep(1)
    
    # Measure webhook response times
    response_times = []
    print("\n⏱️  Measuring webhook response times...")
    
    for i in range(3):
        time.sleep(2)
        start = time.time()
        try:
            receive_sms(webhook_phone, f"Response {i+1}")
            handle_registered_user(webhook_phone, f"Response {i+1}")
            response_time = time.time() - start
            response_times.append(response_time)
            print(f"  Webhook {i+1}: {response_time:.3f}s")
        except Exception as e:
            print(f"  Webhook {i+1}: ERROR - {e}")
    
    # Wait for scheduler
    scheduler_done.wait(timeout=30)
    
    # Results
    if response_times:
        avg_response = sum(response_times) / len(response_times)
        max_response = max(response_times)
        
        print("\n" + "="*70)
        print("📊 WEBHOOK RESPONSE TIME DURING LOAD")
        print("="*70)
        print(f"📬 Webhooks tested: {len(response_times)}/3")
        print(f"⏱️  Average response time: {avg_response:.3f}s")
        print(f"⏱️  Max response time: {max_response:.3f}s")
        print("="*70)
        
        # Assertions
        assert len(response_times) >= 2, "At least 2 webhooks should succeed"
        assert avg_response < 1.0, f"Average response time too high: {avg_response:.3f}s"
        assert max_response < 2.0, f"Max response time too high: {max_response:.3f}s"
