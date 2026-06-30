
import pytest
from scheduler import format_sub_status
from database import get_conn, daf_to_float
from tests.helpers import create_user_with_subscription

def test_status_range_8_pages_limit_cap():
    """
    Test Scenario: 8 pages per day, current is 2.0, end is 14.5 (יד ע"ב).
    current_daf=2.0 means studying daf 2 TODAY. Today's range: ב ע"א עד ט ע"ב (2.0-9.5).
    Next cycle (after advancement) will cover 10.0-14.5.
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

    # Today's study: ב ע"א עד ט ע"ב (2.0 to 9.5)
    assert "ב ע\"א" in status
    assert "ט ע\"ב" in status
    assert "טו ע\"א" not in status

def test_status_range_6_pages_already_finished():
    """
    Test Scenario: 6 pages per day, current is 12.0 (יב ע"א), end is 14.5 (יד ע"ב).
    current_daf=12.0 means studying today. Range caps at end_daf=14.5.
    Since capped range reaches end_daf, shows "last day" notice.
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

    # Range 12.0 to min(17.5, 14.5)=14.5, capped → last day notice
    assert "יב ע\"א" in status
    assert "יד ע\"ב" in status
    assert "יח ע\"א" not in status
    assert "(מחר נסיים את לימוד הטווח המוגדר!)" in status

def test_status_range_exactly_tomorrow_finish():
    """
    Test Scenario: 1 page per day, current is 2.0, end is 3.0.
    Today's study: ב ע"א עד ב ע"ב (2.0 to 2.5). Not last day yet.
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

    # Today: ב ע"א עד ב ע"ב (2.0 to 2.5), not last day
    assert "ב ע\"א" in status
    assert "ב ע\"ב" in status
