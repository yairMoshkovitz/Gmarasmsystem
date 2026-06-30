
import pytest
from scheduler import finish_subscription_day, send_next_question_or_finish
from database import get_conn

def test_hydration_missing_phone(monkeypatch):
    """
    Test that scheduler functions can handle a sub dictionary missing 'phone' 
    by hydrating it from the database.
    """
    conn = get_conn()
    
    # 1. Setup: Create a user and a subscription
    conn.execute("INSERT INTO users (phone, name) VALUES (?, ?)", ("0500000000", "Test User"))
    user_id = conn.execute("SELECT id FROM users WHERE phone=?", ("0500000000",)).fetchone()[0]
    
    conn.execute("INSERT INTO tractates (name, json_path, total_dafim) VALUES (?, ?, ?)", 
                 ("Test Tractate", "data/ברכות.json", 60))
    tractate_id = conn.execute("SELECT id FROM tractates WHERE name=?", ("Test Tractate",)).fetchone()[0]
    
    conn.execute("INSERT INTO subscriptions (user_id, tractate_id, start_daf, end_daf, current_daf, dafim_per_day, send_hour, is_active) "
                 "VALUES (?, ?, 2, 20, 2.0, 1.0, 8, 1)", (user_id, tractate_id))
    sub_id = conn.execute("SELECT id FROM subscriptions WHERE user_id=?", (user_id,)).fetchone()[0]
    conn.commit()
    
    # 2. Create a "broken" sub dict (missing phone and user_id)
    broken_sub = {
        "id": sub_id,
        "tractate_id": tractate_id,
        "tractate_name": "Test Tractate",
        "current_daf": 2.0,
        "dafim_per_day": 1.0,
        "send_hour": 8
    }
    
    # Mock send_sms and other external calls to avoid side effects
    monkeypatch.setattr("scheduler.send_sms", lambda *args, **kwargs: None)
    monkeypatch.setattr("scheduler.get_template", lambda *args, **kwargs: "Test Message")
    
    # 3. Test finish_subscription_day
    # This should NOT raise KeyError: 'phone'
    try:
        finish_subscription_day(broken_sub)
        print("\n✅ finish_subscription_day handled missing phone successfully")
    except KeyError as e:
        pytest.fail(f"finish_subscription_day failed with KeyError: {e}")
    except Exception as e:
        pytest.fail(f"finish_subscription_day failed with: {e}")

    # 4. Test send_next_question_or_finish
    # This should NOT raise KeyError: 'phone'
    try:
        send_next_question_or_finish(broken_sub)
        print("✅ send_next_question_or_finish handled missing phone successfully")
    except KeyError as e:
        pytest.fail(f"send_next_question_or_finish failed with KeyError: {e}")
    except Exception as e:
        pytest.fail(f"send_next_question_or_finish failed with: {e}")

    # Cleanup
    conn.execute("DELETE FROM subscriptions WHERE id=?", (sub_id,))
    conn.execute("DELETE FROM users WHERE id=?", (user_id,))
    conn.execute("DELETE FROM tractates WHERE id=?", (tractate_id,))
    conn.commit()
    conn.close()

if __name__ == "__main__":
    # This allow running it directly for quick verification
    import mock
    class MockMocker:
        def patch(self, name, **kwargs):
            return mock.patch(name, **kwargs).start()
    
    try:
        test_hydration_missing_phone(MockMocker())
    except Exception as e:
        print(f"Test failed: {e}")
