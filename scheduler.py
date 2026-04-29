"""
scheduler.py - Hourly task for sending daily questions
"""
from datetime import datetime, date
from database import get_conn, float_to_daf_str, load_questions
from sms_service import send_sms
from questions_engine import (
    select_questions_for_range,
    get_already_sent_ids,
    format_question_sms
)
from registration import get_template

def has_sent_today(user_id: int, sub_id: int) -> bool:
    """Check if questions were already sent to this user today."""
    conn = get_conn()
    today_start = date.today().isoformat() + "T00:00:00"
    row = conn.execute(
        "SELECT id FROM sent_questions WHERE user_id=? AND subscription_id=? AND sent_at >= ? LIMIT 1",
        (user_id, sub_id, today_start)
    ).fetchone()
    conn.close()
    return row is not None

def get_due_subscriptions(current_hour: int) -> list:
    """Find active subscriptions that should get questions now."""
    conn = get_conn()
    today = date.today().isoformat()
    
    rows = conn.execute(
        """
        SELECT s.*, t.name as tractate_name, u.phone, u.name as user_name
        FROM subscriptions s
        JOIN tractates t ON s.tractate_id = t.id
        JOIN users u ON s.user_id = u.id
        WHERE s.is_active=1 AND s.send_hour=?
        AND (s.pause_until IS NULL OR s.pause_until <= ?)
        """,
        (current_hour, today),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def advance_subscription(sub_id: int, dafim_per_day: float):
    """Update current_daf for the next day."""
    conn = get_conn()
    conn.execute(
        "UPDATE subscriptions SET current_daf = current_daf + ? WHERE id=?",
        (dafim_per_day, sub_id),
    )
    conn.commit()
    conn.close()

def finish_subscription_day(sub: dict):
    """Send finishing messages and advance daf."""
    # 1. Send "Tomorrow's Study" message
    start_f = sub["current_daf"]
    next_start = start_f + sub["dafim_per_day"]
    next_end = next_start + sub["dafim_per_day"] - 0.5
    
    study_range = f"{float_to_daf_str(next_start)}"
    if sub["dafim_per_day"] > 0.5:
        study_range += f" עד {float_to_daf_str(next_end)}"
        
    tomorrow_msg = get_template("tomorrow_study", next_study=study_range)
    send_sms(sub["phone"], tomorrow_msg, sub["user_id"])
    
    # 2. Advance to next day
    advance_subscription(sub["id"], sub["dafim_per_day"])

def send_next_question_or_finish(sub: dict):
    """
    Check for the next question to send in the current range.
    If no more questions (or reached daily limit), send the 'tomorrow study' message.
    """
    # 1. Check daily limit (e.g., 2 questions per day)
    conn = get_conn()
    today_start = date.today().isoformat() + "T00:00:00"
    count_row = conn.execute(
        "SELECT COUNT(*) FROM sent_questions WHERE subscription_id=? AND sent_at >= ?",
        (sub["id"], today_start)
    ).fetchone()
    conn.close()
    
    daily_limit = 2 # This could be configurable in the future
    if count_row[0] >= daily_limit:
        print(f"Sub {sub['id']} reached daily limit of {daily_limit} questions.")
        finish_subscription_day(sub)
        return False

    questions = load_questions(sub["tractate_id"])
    already_sent = get_already_sent_ids(sub["user_id"], sub["id"])
    
    start_f = sub["current_daf"]
    end_f = start_f + sub["dafim_per_day"] - 0.01
    
    daily_selection = select_questions_for_range(
        questions, start_f, end_f, already_sent, max_questions=1
    )

    if daily_selection:
        q = daily_selection[0]
        conn = get_conn()
        conn.execute(
            "INSERT INTO sent_questions (user_id, subscription_id, question_id, question_text) VALUES (?, ?, ?, ?)",
            (sub["user_id"], sub["id"], str(q.get("id")), q.get("text") or q.get("question") or ""),
        )
        conn.commit()
        conn.close()
        
        msg = format_question_sms(q, 1, sub["tractate_name"])
        send_sms(sub["phone"], msg, sub["user_id"])
        return True
    else:
        # No more questions in range for today
        finish_subscription_day(sub)
        return False

def send_daily_questions(sub: dict):
    """Select and send the FIRST question for a single subscription."""
    # Safety check: don't send twice in the same calendar day (initial trigger)
    if has_sent_today(sub["user_id"], sub["id"]):
        print(f"Skipping sub {sub['id']} - already sent today.")
        return

    # Try to send the first question
    send_next_question_or_finish(sub)


def run_hour(hour: int = None):
    """Main entry point for scheduled task."""
    from sms_service import get_live_mode
    if not get_live_mode():
        print(f"⏸️ System in Simulation mode. Skipping scheduled tasks for hour {hour or datetime.now().hour}.")
        return

    if hour is None:
        hour = datetime.now().hour
        
    due = get_due_subscriptions(hour)
    print(f"⏰ Hour {hour}: Processing {len(due)} due subscriptions.")
    
    for sub in due:
        try:
            send_daily_questions(sub)
        except Exception as e:
            print(f"❌ Error sending to sub {sub['id']}: {e}")

if __name__ == "__main__":
    run_hour()
