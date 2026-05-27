
import pytest
from scheduler import format_sub_status
from database import get_conn, daf_to_float
from tests.helpers import create_user_with_subscription

def test_status_range_8_pages_limit_cap():
    """
    Test Scenario: 8 pages per day, current is 2.0, end is 14.5 (יד ע"ב).
    Tomorrow's start should be 10.0 (י ע"א), and end should be 14.5 (יד ע"ב).
    """
    phone = "0511111111"
    tractate = "ברכות"
    user_id, sub_id = create_user_with_subscription(phone, "RangeTest1", tractate)
    
    conn = get_conn()
    conn.execute("UPDATE subscriptions SET start_daf=?, end_daf=?, current_daf=?, dafim_per_day=? WHERE id=?",
                 (2.0, 14.5, 2.0, 8.0, sub_id))
    conn.commit()
    
    sub = conn.execute("SELECT s.*, t.name as tractate_name FROM subscriptions s JOIN tractates t ON s.tractate_id = t.id WHERE s.id=?", (sub_id,)).fetchone()
    sub_dict = dict(sub)
    conn.close()
    
    status = format_sub_status(sub_dict)
    
    # Should contain י ע"א (10.0) and יד ע"ב (14.5)
    assert "י ע\"א" in status
    assert "יד ע\"ב" in status
    # Should NOT contain טו ע"א (15.0)
    assert "טו ע\"א" not in status
    assert "(מחר נסיים את לימוד הטווח המוגדר!)" in status

def test_status_range_6_pages_already_finished():
    """
    Test Scenario: 6 pages per day, current is 12.0 (יב ע"א), end is 14.5 (יד ע"ב).
    Tomorrow's start would be 12.0+6.0=18.0, which is past 14.5.
    Should show completion message.
    """
    phone = "0511111112"
    tractate = "ברכות"
    user_id, sub_id = create_user_with_subscription(phone, "RangeTest2", tractate)
    
    conn = get_conn()
    conn.execute("UPDATE subscriptions SET start_daf=?, end_daf=?, current_daf=?, dafim_per_day=? WHERE id=?",
                 (2.0, 14.5, 12.0, 6.0, sub_id))
    conn.commit()
    
    sub = conn.execute("SELECT s.*, t.name as tractate_name FROM subscriptions s JOIN tractates t ON s.tractate_id = t.id WHERE s.id=?", (sub_id,)).fetchone()
    sub_dict = dict(sub)
    conn.close()
    
    status = format_sub_status(sub_dict)
    
    # Should show completion message from template
    assert "סיימת את הלימוד המוגדר" in status
    assert "יח ע\"א" not in status
    assert "יד ע\"ב" in status # Range is in the message

def test_status_range_exactly_tomorrow_finish():
    """
    Test Scenario: 1 page per day, current is 2.0, end is 3.0.
    Tomorrow's study should be exactly 3.0.
    """
    phone = "0511111113"
    tractate = "ברכות"
    user_id, sub_id = create_user_with_subscription(phone, "RangeTest3", tractate)
    
    conn = get_conn()
    conn.execute("UPDATE subscriptions SET start_daf=?, end_daf=?, current_daf=?, dafim_per_day=? WHERE id=?",
                 (2.0, 3.0, 2.0, 1.0, sub_id))
    conn.commit()
    
    sub = conn.execute("SELECT s.*, t.name as tractate_name FROM subscriptions s JOIN tractates t ON s.tractate_id = t.id WHERE s.id=?", (sub_id,)).fetchone()
    sub_dict = dict(sub)
    conn.close()
    
    status = format_sub_status(sub_dict)
    
    # Tomorrow study is 3.0 (ג ע"א)
    assert "ג ע\"א" in status
    assert "עד" not in status # Only one page
    assert "(מחר נסיים את לימוד הטווח המוגדר!)" in status
