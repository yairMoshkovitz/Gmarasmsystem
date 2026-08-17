import pytest
from database import get_conn, float_to_daf_str
from registration import register_user, subscribe
from scheduler import advance_all_subscriptions_daily, format_sub_status
from simulation_system import handle_registered_user, USER_STATES
import os

def test_subscription_completion_exact_daf():
    """Test that a subscription ending in Amud B completes correctly."""
    phone = "0527204623"
    USER_STATES.clear()
    
    conn = get_conn()
    conn.execute("DELETE FROM users WHERE phone=?", (phone,))
    conn.commit()
    
    # 1. Register User
    user_id = register_user(phone, "משה")
    user = {"id": user_id, "phone": phone, "name": "משה"}
    
    # 2. Register for range ending in ע"ב
    # We use handle_registered_user to test the parsing too
    USER_STATES[phone] = {"state": "AWAITING_REG_STEP_2"}
    handle_registered_user(phone, user, "ברכות ב ע\"א עד יד ע\"ב")
    
    # Verify state parsing
    state = USER_STATES[phone]
    assert state["end_daf"] == 14.5
    
    # Complete registration
    handle_registered_user(phone, user, "1") # 1 daf per day
    handle_registered_user(phone, user, "8") # 8 AM
    
    # 3. Check Database Storage
    sub = conn.execute("SELECT * FROM subscriptions WHERE user_id=?", (user_id,)).fetchone()
    assert sub["end_daf"] == 14.5
    assert sub["is_active"] == 1
    
    # 4. Advance multiple times and check "tomorrow" message
    # Day 1: current=2.0 (ב ע"א), end=14.5. Tomorrow=3.0 (ג ע"א)
    # Fast forward to near the end
    conn.execute("UPDATE subscriptions SET current_daf = 13.0 WHERE id=?", (sub["id"],))
    conn.commit()
    
    updated_sub = conn.execute("SELECT s.*, t.name as tractate_name FROM subscriptions s JOIN tractates t ON s.tractate_id = t.id WHERE s.id=?", (sub["id"],)).fetchone()
    status = format_sub_status(dict(updated_sub))
    # next study should be 13.0 to 13.5 (since rate is 1.0)
    assert "יג ע\"א עד יג ע\"ב" in status
    
    # 5. Move to the last day
    # current=14.0 (יד ע"א), end=14.5. Tomorrow would be 15.0 but capped at 14.5.
    conn.execute("UPDATE subscriptions SET current_daf = 14.0 WHERE id=?", (sub["id"],))
    conn.commit()
    
    updated_sub = conn.execute("SELECT s.*, t.name as tractate_name FROM subscriptions s JOIN tractates t ON s.tractate_id = t.id WHERE s.id=?", (sub["id"],)).fetchone()
    status = format_sub_status(dict(updated_sub))
    assert "יד ע\"א עד יד ע\"ב" in status
    assert "מחר נסיים" in status
    
    # 6. Test partial range logic (the problem the user reported)
    # current=8.0 (ח ע"א), end=10.5 (י ע"ב), rate=6.0.
    conn.execute("UPDATE subscriptions SET current_daf = 8.0, end_daf = 10.5, dafim_per_day = 6.0 WHERE id=?", (sub["id"],))
    conn.commit()
    
    updated_sub = conn.execute("SELECT s.*, t.name as tractate_name FROM subscriptions s JOIN tractates t ON s.tractate_id = t.id WHERE s.id=?", (sub["id"],)).fetchone()
    status = format_sub_status(dict(updated_sub))
    # Should say "ח ע"א עד י ע"ב" and NOT "עד יג ע"ב"
    assert "ח ע\"א עד י ע\"ב" in status
    assert "יג" not in status
    
    # 7. Perform final advancement (at 23:55)
    # current is 14.0, we advanced today to 14.0. Tomorrow we advance to 14.0 + 1.0 = 15.0
    # Wait, the logic in advance_all_subscriptions_daily:
    # new_daf = 14.0 + 1.0 = 15.0. 15.0 > 14.5 + 0.01. new_daf = 14.5. 
    # Actually, it stays active until it hits exactly or passes.
    
    # Reset to 14.0 for final test
    conn.execute("UPDATE subscriptions SET current_daf = 14.0, end_daf = 14.5, dafim_per_day = 1.0 WHERE id=?", (sub["id"],))
    conn.commit()

    advance_all_subscriptions_daily()
    
    sub_after = conn.execute("SELECT * FROM subscriptions WHERE id=?", (sub["id"],)).fetchone()
    assert sub_after["current_daf"] == 14.5
    assert sub_after["is_active"] == 1 # Still active for the last half-daf? 
    # If rate is 1.0, and they are at 14.0, they study 14.0 and 14.5.
    # So after that day, it should be done.
    
    # Advance again - now it should definitely complete
    advance_all_subscriptions_daily()
    sub_final = conn.execute("SELECT * FROM subscriptions WHERE id=?", (sub["id"],)).fetchone()
    assert sub_final["is_active"] == 0
    
    conn.close()

def test_subscription_partial_last_day_range():
    """Test that the tomorrow-range is capped at end_daf even with large daily rate."""
    phone = "0501234563"
    USER_STATES.clear()
    
    conn = get_conn()
    conn.execute("DELETE FROM users WHERE phone=?", (phone,))
    conn.commit()
    
    user_id = register_user(phone, "משה")
    user = {"id": user_id, "phone": phone, "name": "משה"}
    
    # User registers until י ע"ב (10.5), starting at ב ע"א (2.0)
    USER_STATES[phone] = {"state": "AWAITING_REG_STEP_2"}
    handle_registered_user(phone, user, "ברכות ב ע\"א עד י ע\"ב")
    
    # Rate of 6.0 dafim per day, hour 6
    handle_registered_user(phone, user, "6")
    handle_registered_user(phone, user, "6")
    
    # current_daf=8.0 (ח ע"א), end_daf=10.5 (י ע"ב), rate=6.0
    conn.execute("UPDATE subscriptions SET current_daf = 8.0 WHERE user_id=?", (user_id,))
    conn.commit()
    
    sub = conn.execute("SELECT s.*, t.name as tractate_name FROM subscriptions s JOIN tractates t ON s.tractate_id = t.id WHERE s.user_id=?", (user_id,)).fetchone()
    
    status = format_sub_status(dict(sub))
    
    # MUST say "ח ע"א עד י ע"ב" and NOT "עד יג ע"ב"
    assert "ח ע\"א עד י ע\"ב" in status
    assert "יג" not in status
    assert "מחר נסיים" in status
    
    conn.close()
