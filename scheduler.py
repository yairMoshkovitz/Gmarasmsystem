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
from sms_service import get_live_mode

def has_sent_today(user_id: int, sub_id: int) -> bool:
    """Check if questions were already sent to this user today."""
    conn = get_conn()
    today_start = date.today().isoformat() + " 00:00:00"
    row = conn.execute(
        "SELECT id FROM sent_questions WHERE user_id=? AND subscription_id=? AND sent_at >= ? LIMIT 1",
        (user_id, sub_id, today_start)
    ).fetchone()
    conn.close()
    return row is not None

def get_due_subscriptions(current_hour: int, today_str: str = None) -> list:
    """Find active subscriptions that should get questions now."""
    conn = get_conn()
    today = today_str or date.today().isoformat()
    
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

def format_sub_status(sub: dict) -> str:
    """Format a standard status line for a subscription using sub_status_info template."""
    next_start = sub["current_daf"]
    # If it was just advanced, current_daf is already tomorrow's
    # But usually we call this AFTER advance_subscription or when checking status
    
    next_end = next_start + sub["dafim_per_day"] - 0.5
    study_range = f"{float_to_daf_str(next_start)}"
    if sub["dafim_per_day"] > 0.5:
        study_range += f" עד {float_to_daf_str(next_end)}"
    
    sub_range = f"{float_to_daf_str(sub['start_daf'])} - {float_to_daf_str(sub['end_daf'])}"
    
    return get_template("sub_status_info", 
                        tractate_name=sub['tractate_name'],
                        range=sub_range,
                        next_study=study_range,
                        hour=sub["send_hour"])

def finish_subscription_day(sub: dict, override_queue: list = None):
    """Send finishing messages and advance daf."""
    import simulation_system
    
    def _get_local_subs_menu(subs):
        lines = []
        for i, s in enumerate(subs, 1):
            range_str = f"({float_to_daf_str(s['start_daf'])} - {float_to_daf_str(s['end_daf'])})"
            lines.append(f"{i}. {s['tractate_name']} {range_str}")
        return "\n".join(lines)

    # 1. Advance to next day FIRST so we can show tomorrow's study correctly
    advance_subscription(sub["id"], sub["dafim_per_day"])
    
    print(f"DEBUG: Finishing day for sub {sub['id']} ({sub['tractate_name']})")
    
    # Check if there are other subscriptions in the queue for this session
    # We prefer the override_queue parameter passed directly to avoid circular import issues
    queue = override_queue
    if queue is None:
        state_info = simulation_system.USER_STATES.get(sub["phone"])
        if state_info and state_info.get("state") in ["PROCESSING_QUESTION_QUEUE", "AWAITING_ANSWER"]:
            queue = state_info.get("queue", [])
    
    if queue:
        # Still more tractates in queue
        print(f"DEBUG: Found queue with {len(queue)} items left")
        if len(queue) >= 2:
            # Refresh subs data from DB to get latest tractate names/ranges
            conn = get_conn()
            due_subs = []
            for s_id in queue:
                r = conn.execute(
                    "SELECT s.*, t.name as tractate_name FROM subscriptions s JOIN tractates t ON s.tractate_id = t.id WHERE s.id=?", (s_id,)
                ).fetchone()
                if r: due_subs.append(dict(r))
            conn.close()
            
            msg = get_template("queue_next_menu", menu=_get_local_subs_menu(due_subs))
            send_sms(sub["phone"], msg, sub["user_id"])
            # State remains PROCESSING_QUESTION_QUEUE
        else:
            # Only 1 left, send it directly
            last_sub_id = queue.pop(0)
            conn = get_conn()
            last_sub = conn.execute(
                "SELECT s.*, t.name as tractate_name, u.phone, u.name as user_name FROM subscriptions s JOIN tractates t ON s.tractate_id = t.id JOIN users u ON s.user_id = u.id WHERE s.id=?", (last_sub_id,)
            ).fetchone()
            conn.close()
            
            if last_sub:
                last_sub = dict(last_sub)
                range_str = f"{last_sub['tractate_name']} ({float_to_daf_str(last_sub['start_daf'])} - {float_to_daf_str(last_sub['end_daf'])})"
                msg = get_template("queue_last_one", finished_tractate=sub["tractate_name"], next_tractate=range_str)
                send_sms(sub["phone"], msg, sub["user_id"])
                # Recursively pass the empty queue
                send_next_question_or_finish(last_sub, override_queue=queue)
        return

    # No queue or queue finished - Send "Study Closure" message
    print(f"DEBUG: No queue found or queue finished. Sending study closure.")
    
    # Get all active subscriptions for this user to build a combined status message
    conn = get_conn()
    all_user_subs = conn.execute(
        "SELECT s.*, t.name as tractate_name FROM subscriptions s JOIN tractates t ON s.tractate_id = t.id WHERE s.user_id=? AND s.is_active=1", (sub["user_id"],)
    ).fetchall()
    conn.close()
    
    if all_user_subs:
        status_lines = [format_sub_status(dict(s)) for s in all_user_subs]
        combined_status = "\n".join(status_lines)
        closure_msg = get_template("study_closure", sub_info=combined_status)
        send_sms(sub["phone"], closure_msg, sub["user_id"])

    # Clear state completely since day is finished
    if sub["phone"] in simulation_system.USER_STATES:
        del simulation_system.USER_STATES[sub["phone"]]

def send_next_question_or_finish(sub: dict, override_queue: list = None):
    """
    Check for the next question to send in the current range.
    If no more questions (or reached daily limit), send the 'tomorrow study' message.
    """
    import simulation_system
    # 1. Check daily limit (e.g., 2 questions per day)
    conn = get_conn()
    
    # Use SQLite date function to ensure we count only today's questions
    count_row = conn.execute(
        "SELECT COUNT(*) FROM sent_questions WHERE subscription_id=? AND date(sent_at) = date('now')",
        (sub["id"],)
    ).fetchone()
    
    # Check if we are running in Postgres where 'now' might be slightly different syntax
    # For compatibility, we can check by simple str starts with
    if count_row is None or count_row[0] == 0:
        # Fallback for Postgres or if previous query failed
        today_str = str(date.today())
        count_row = conn.execute(
            "SELECT COUNT(*) FROM sent_questions WHERE subscription_id=? AND sent_at LIKE ?",
            (sub["id"], f"{today_str}%")
        ).fetchone()

    conn.close()
    
    daily_limit = 2 # This could be configurable in the future
    
    if count_row and count_row[0] >= daily_limit:
        print(f"Sub {sub['id']} reached daily limit of {daily_limit} questions (found {count_row[0]}).")
        finish_subscription_day(sub, override_queue=override_queue)
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
        
        # Verify insertion for debug
        c2 = conn.execute("SELECT COUNT(*) FROM sent_questions WHERE subscription_id=?", (sub["id"],)).fetchone()
        print(f"DEBUG: sent_questions count for sub {sub['id']} is now {c2[0]}")
        conn.close()
        
        msg = format_question_sms(q, 1, sub["tractate_name"])
        send_sms(sub["phone"], msg, sub["user_id"])
        
        # Set AWAITING_ANSWER state
        new_state = {"state": "AWAITING_ANSWER"}
        
        # Try to use override queue, or fetch from existing state
        if override_queue is not None:
            new_state["queue"] = override_queue
        else:
            old_state = simulation_system.USER_STATES.get(sub['phone'], {})
            if "queue" in old_state:
                new_state["queue"] = old_state["queue"]
                
        simulation_system.USER_STATES[sub['phone']] = new_state
        
        return True
    else:
        # No more questions in range for today
        # Check if we should send the "no questions today" message instead of just the closure
        if count_row[0] == 0:
            # First attempt today and no questions found
            # Advance for tomorrow
            advance_subscription(sub["id"], sub["dafim_per_day"])
            
            # Refresh sub data to get updated current_daf
            conn = get_conn()
            updated_sub = conn.execute(
                "SELECT s.*, t.name as tractate_name FROM subscriptions s JOIN tractates t ON s.tractate_id = t.id WHERE s.id=?", (sub["id"],)
            ).fetchone()
            conn.close()
            
            if updated_sub:
                updated_sub = dict(updated_sub)
                next_start = updated_sub["current_daf"]
                next_end = next_start + updated_sub["dafim_per_day"] - 0.5
                study_range = f"{float_to_daf_str(next_start)}"
                if updated_sub["dafim_per_day"] > 0.5:
                    study_range += f" עד {float_to_daf_str(next_end)}"
                
                msg = get_template("no_questions_today", next_study=study_range, hour=updated_sub["send_hour"])
                send_sms(sub["phone"], msg, sub["user_id"])
        else:
            finish_subscription_day(sub, override_queue=override_queue)
        return False

def send_daily_questions(sub: dict):
    """Select and send the FIRST question for a single subscription."""
    # Safety check: don't send twice in the same calendar day (initial trigger)
    if has_sent_today(sub["user_id"], sub["id"]):
        # print(f"Skipping sub {sub['id']} - already sent today.")
        return

    # Try to send the first question
    send_next_question_or_finish(sub)


def get_israel_time():
    """Get current time in Israel (UTC+3)."""
    # Assuming the server is in UTC. If it's not, we might need a more robust way.
    # But based on the user's "3 hours back" c
    # ent, UTC+3 is the goal.
    from datetime import datetime, timedelta
    return datetime.utcnow() + timedelta(hours=3)

def has_pending_question(user_id: int, same_day_only: bool = False) -> bool:
    """
    Check if the user has any question that hasn't been answered yet.
    If same_day_only is True, only check for questions sent today.
    """
    conn = get_conn()
    query = "SELECT id FROM sent_questions WHERE user_id=? AND responded_at IS NULL"
    params = [user_id]
    
    if same_day_only:
        today_start = date.today().isoformat() + " 00:00:00"
        query += " AND sent_at >= ?"
        params.append(today_start)
        
    query += " LIMIT 1"
    row = conn.execute(query, params).fetchone()
    conn.close()
    return row is not None

def run_hour(hour: int = None, force_date: date = None):
    """Main entry point for scheduled task."""
    israel_now = get_israel_time()
    today = force_date or date.today()
    if hour is None:
        hour = israel_now.hour
    
    if not get_live_mode():
        try:
            print(f"System in Simulation mode. Skipping scheduled tasks for hour {hour}.")
        except:
            pass
        return

    day_of_week = israel_now.weekday()  # 0=Monday, 4=Friday, 5=Saturday, 6=Sunday
    
    # Shabbat logic: No sending on Shabbat (Friday 16:00 to Saturday 21:00)
    # Friday after 16:00
    if day_of_week == 4 and hour > 16:
        print(f"Friday after 16:00. Skipping hour {hour}.")
        return
    
    # Shabbat day until 21:00
    if day_of_week == 5 and hour < 21:
        print(f"Shabbat day. Skipping hour {hour}.")
        return

    due = []
    
    # Special case: Friday 16:00 - send all Friday 16:00+ messages
    if day_of_week == 4 and hour == 16:
        conn = get_conn()
        today_str = today.isoformat()
        rows = conn.execute(
            """
            SELECT s.*, t.name as tractate_name, u.phone, u.name as user_name
            FROM subscriptions s
            JOIN tractates t ON s.tractate_id = t.id
            JOIN users u ON s.user_id = u.id
            WHERE s.is_active=1 AND s.send_hour >= 16
            AND (s.pause_until IS NULL OR s.pause_until <= ?)
            """,
            (today,),
        ).fetchall()
        conn.close()
        due = [dict(r) for r in rows]
        print(f"Friday 16:00: Catching all Friday evening messages. Count: {len(due)}")
    
    # Special case: Saturday 21:00 - send all Shabbat messages
    elif day_of_week == 5 and hour == 21:
        conn = get_conn()
        today_str = today.isoformat()
        # Find all subscriptions that were supposed to run during Shabbat
        # (Friday > 16:00 OR Saturday < 21:00)
        # Since we run daily, we just need to find all active subs that haven't sent today
        # But specifically those whose send_hour is in the Shabbat range.
        # Actually, simpler: Saturday 21:00 runs for EVERYONE who hasn't sent today? 
        # No, the user said "Shabbat questions will be sent at 21:00".
        # This implies people who usually get it on Shabbat.
        rows = conn.execute(
            """
            SELECT s.*, t.name as tractate_name, u.phone, u.name as user_name
            FROM subscriptions s
            JOIN tractates t ON s.tractate_id = t.id
            JOIN users u ON s.user_id = u.id
            WHERE s.is_active=1
            AND (s.pause_until IS NULL OR s.pause_until <= ?)
            """,
            (today,),
        ).fetchall()
        conn.close()
        
        # Filter in Python for clarity of logic:
        # A sub is "Shabbat sub" if its normal hour is (Friday > 16) OR (Saturday < 21)
        # But wait, send_hour is just an integer 0-23.
        # If it's Saturday 21:00, we should send for everyone whose hour was 0-20 today.
        # AND those whose hour was 17-23 on Friday (if we want to be perfect, but daily check handles it).
        
        all_subs = [dict(r) for r in rows]
        for sub in all_subs:
            # If normal hour is between 0 and 20, they missed it today because of Shabbat
            if 0 <= sub['send_hour'] < 21:
                due.append(sub)
        print(f"Saturday 21:00: Catching all Shabbat messages. Count: {len(due)}")

    else:
        # Normal hour processing
        due = get_due_subscriptions(hour, today.isoformat())

    if due:
        try:
            print(f"Hour {hour}: Processing {len(due)} subscriptions.")
        except:
            pass
        
        # Group by user to handle multi-subscription queue
        user_due = {}
        for sub in due:
            uid = sub["user_id"]
            if uid not in user_due: user_due[uid] = []
            user_due[uid].append(sub)
            
        from simulation_system import USER_STATES
        
        def _get_local_subs_menu(subs):
            lines = []
            for i, s in enumerate(subs, 1):
                range_str = f"({float_to_daf_str(s['start_daf'])} - {float_to_daf_str(s['end_daf'])})"
                lines.append(f"{i}. {s['tractate_name']} {range_str}")
            return "\n".join(lines)

        for uid, subs in user_due.items():
            try:
                # Multi-subscription check: 
                if has_pending_question(uid, same_day_only=True):
                    print(f"User {uid} already has a pending question from today. Skipping for now.")
                    continue
                
                if len(subs) == 1:
                    send_daily_questions(subs[0])
                else:
                    # Multi-sub queue
                    phone = subs[0]["phone"]
                    USER_STATES[phone] = {
                        "state": "PROCESSING_QUESTION_QUEUE",
                        "queue": [s["id"] for s in subs]
                    }
                    msg = get_template("queue_start_menu", menu=_get_local_subs_menu(subs))
                    send_sms(phone, msg, uid)
            except Exception as e:
                print(f"❌ Error processing user {uid}: {e}")

if __name__ == "__main__":
    run_hour()
