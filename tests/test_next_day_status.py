"""
Regression tests for the "shows today's daf instead of tomorrow's" bug.

format_sub_status() feeds the sub_status_info template, which always says
"the study TOMORROW will be X". current_daf only advances at 23:55
(see advance_all_subscriptions_daily), so any caller running mid-day
(study closure, status menu) must ask for next_day=True to preview the daf
that tonight's advancement will move to - otherwise it shows the daf that
was already studied/sent today.

Also covers the related regression where nightly advancement itself was
silently skipped whenever live_mode happened to be off at 23:55.
"""
from datetime import datetime

from database import get_conn
from scheduler import format_sub_status, finish_subscription_day
from sms_service import set_live_mode
from tests.helpers import create_user_with_subscription, get_last_sms


def _get_sub(sub_id):
    conn = get_conn()
    row = conn.execute(
        "SELECT s.*, t.name as tractate_name, u.phone, u.id as user_id "
        "FROM subscriptions s "
        "JOIN tractates t ON s.tractate_id = t.id "
        "JOIN users u ON s.user_id = u.id "
        "WHERE s.id=?",
        (sub_id,),
    ).fetchone()
    conn.close()
    return dict(row)


def test_format_sub_status_default_shows_current_daf():
    """Without next_day, must keep showing current_daf as-is (used by resume-from-pause,
    where no advancement happened while paused).

    current_daf is set away from start_daf so the subscription-range display
    (which always includes start_daf) can't be mistaken for the "next study" field.
    """
    phone = "0512220001"
    _, sub_id = create_user_with_subscription(phone, "StatusTest1", "ברכות")
    conn = get_conn()
    conn.execute("UPDATE subscriptions SET current_daf=5.0, dafim_per_day=1.0 WHERE id=?", (sub_id,))
    conn.commit()
    conn.close()

    status = format_sub_status(_get_sub(sub_id))
    assert 'ה ע"א' in status
    assert 'ו ע"א' not in status


def test_format_sub_status_next_day_shows_advanced_daf():
    """next_day=True must preview the daf that 23:55 will advance to."""
    phone = "0512220002"
    _, sub_id = create_user_with_subscription(phone, "StatusTest2", "ברכות")
    conn = get_conn()
    conn.execute("UPDATE subscriptions SET current_daf=5.0, dafim_per_day=1.0 WHERE id=?", (sub_id,))
    conn.commit()
    conn.close()

    status = format_sub_status(_get_sub(sub_id), next_day=True)
    assert 'ו ע"א' in status
    assert 'ה ע"א' not in status


def test_study_closure_shows_tomorrows_daf_not_todays():
    """
    Regression test for the reported bug: the closure message sent right after
    the user answers today's last question must show tomorrow's daf, not
    today's - even though current_daf itself only advances at 23:55.
    """
    phone = "0512220003"
    _, sub_id = create_user_with_subscription(phone, "StatusTest3", "ברכות")
    conn = get_conn()
    conn.execute("UPDATE subscriptions SET current_daf=5.0, dafim_per_day=1.0 WHERE id=?", (sub_id,))
    conn.commit()
    conn.close()

    finish_subscription_day(_get_sub(sub_id))

    msg = get_last_sms(phone)
    assert msg is not None
    assert 'ו ע"א' in msg, f"Closure message should show tomorrow's daf (ו), got: {msg}"
    assert 'ה ע"א' not in msg, f"Closure message should NOT show today's already-sent daf (ה): {msg}"


def test_nightly_advancement_runs_even_when_live_mode_is_off(monkeypatch):
    """
    Regression test: daf advancement at 23:55 must run regardless of live_mode.
    It used to be gated behind get_live_mode(), so if the system happened to be
    in simulation/off mode at that exact minute, the day silently failed to
    advance and users kept getting the same day's daf again.
    """
    import scheduler

    phone = "0512220004"
    _, sub_id = create_user_with_subscription(phone, "StatusTest4", "ברכות")
    conn = get_conn()
    conn.execute("UPDATE subscriptions SET current_daf=2.0, dafim_per_day=1.0 WHERE id=?", (sub_id,))
    conn.commit()
    conn.close()

    set_live_mode(False)
    monkeypatch.setattr(scheduler, "get_israel_time", lambda: datetime(2026, 7, 10, 23, 56))

    scheduler.run_hour(23)

    conn = get_conn()
    row = conn.execute("SELECT current_daf FROM subscriptions WHERE id=?", (sub_id,)).fetchone()
    conn.close()
    assert row["current_daf"] == 3.0, "Daf must advance at 23:55 even when live_mode is off"
