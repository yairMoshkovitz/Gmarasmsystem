"""
scheduler.py - Hourly task for sending daily questions
"""
from datetime import datetime, date
from database import get_conn, float_to_daf_str
from sms_service import send_sms
import os
from questions_engine import (
    select_questions_for_range,
    get_already_sent_ids,
    format_question_sms
)
from registration import get_template
from sms_service import get_live_mode
from logging_config import get_logger, log_function_entry

logger = get_logger(__name__)

@log_function_entry
def has_sent_today(user_id: int, sub_id: int) -> bool:
    """Check if questions were already sent to this user today using Israel time."""
    # Use get_israel_time().date() to ensure we are checking against the correct local day
    israel_today = get_israel_time().date().isoformat()
    
    conn = get_conn()
    is_postgres = bool(os.environ.get("DATABASE_URL"))
    if is_postgres:
        # Cast to date for comparison
        row = conn.execute(
            "SELECT id FROM sent_questions WHERE user_id=? AND subscription_id=? AND sent_at::date = ?::date LIMIT 1",
            (user_id, sub_id, israel_today)
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT id FROM sent_questions WHERE user_id=? AND subscription_id=? AND date(sent_at) = date(?) LIMIT 1",
            (user_id, sub_id, israel_today)
        ).fetchone()
    conn.close()
    return row is not None

@log_function_entry
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


@log_function_entry
def advance_subscription(sub_id: int, dafim_per_day: float):
    """
    Update current_daf for the next day.
    If reached end_daf, deactivate the subscription and send a completion message.
    """
    conn = get_conn()
    sub = conn.execute(
        "SELECT s.*, t.name as tractate_name, u.phone, u.id as user_id FROM subscriptions s "
        "JOIN tractates t ON s.tractate_id = t.id "
        "JOIN users u ON s.user_id = u.id "
        "WHERE s.id=?", (sub_id,)
    ).fetchone()
    
    if not sub:
        conn.close()
        return

    new_daf = sub["current_daf"] + dafim_per_day
    
    if new_daf > sub["end_daf"]:
        # Subscription completed!
        conn.execute("UPDATE subscriptions SET is_active=0, current_daf=? WHERE id=?", (sub["end_daf"], sub_id))
        conn.commit()
        
        range_str = f"{float_to_daf_str(sub['start_daf'])} - {float_to_daf_str(sub['end_daf'])}"
        msg = get_template("subscription_completed", 
                           tractate_name=sub["tractate_name"],
                           range=range_str)
        send_sms(sub["phone"], msg, sub["user_id"])
    else:
        conn.execute(
            "UPDATE subscriptions SET current_daf = ? WHERE id=?",
            (new_daf, sub_id),
        )
        conn.commit()
    
    conn.close()

@log_function_entry
def format_sub_status(sub: dict) -> str:
    """Format a standard status line for a subscription using sub_status_info template."""
    # current_daf = the next daf to study (what we'll study tomorrow/today)
    next_start = sub["current_daf"]

    sub_range = f"{float_to_daf_str(sub['start_daf'])} - {float_to_daf_str(sub['end_daf'])}"

    # If already past end_daf, subscription is finished
    if next_start > sub["end_daf"] + 0.01:
        return get_template("sub_status_finished",
                          tractate_name=sub['tractate_name'],
                          range=sub_range)

    # Calculate study range end: next_start + rate - 0.5 (covers both amudim of a daf)
    next_end = next_start + sub["dafim_per_day"] - 0.5

    # Cap next_end at subscription's end_daf
    is_last_day_tomorrow = False
    if next_end >= sub["end_daf"] - 0.01:
        next_end = sub["end_daf"]
        is_last_day_tomorrow = True
        
    tomorrow_study = f"{float_to_daf_str(next_start)}"
    if next_start < next_end:
        tomorrow_study += f" עד {float_to_daf_str(next_end)}"
    
    status = get_template("sub_status_info", 
                        tractate_name=sub['tractate_name'],
                        range=sub_range,
                        next_study=tomorrow_study,
                        hour=sub["send_hour"])
                        
    if is_last_day_tomorrow:
        status += "\n(מחר נסיים את לימוד הטווח המוגדר!)"
        
    return status

@log_function_entry
def finish_subscription_day(sub: dict, override_queue: list = None):
    """Send finishing messages. Note: Daf advancement happens at 23:55 daily."""
    import simulation_system
    
    # Ensure we have phone and user_id in the sub dictionary
    if "phone" not in sub or "user_id" not in sub:
        print(f"DEBUG: finish_subscription_day missing phone/user_id in sub. Hydrating for sub_id: {sub.get('id')}")
        conn = get_conn()
        user_info = conn.execute(
            "SELECT u.phone, u.id as user_id FROM users u "
            "JOIN subscriptions s ON s.user_id = u.id "
            "WHERE s.id = ?",
            (sub["id"],)
        ).fetchone()
        conn.close()
        if user_info:
            sub = {**sub, "phone": user_info["phone"], "user_id": user_info["user_id"]}
        else:
            print(f"ERROR: Could not hydrate sub {sub.get('id')} - user not found.")
            return

    def _get_local_subs_menu(subs):
        lines = []
        for i, s in enumerate(subs, 1):
            range_str = f"({float_to_daf_str(s['start_daf'])} - {float_to_daf_str(s['end_daf'])})"
            lines.append(f"{i}. {s['tractate_name']} {range_str}")
        return "\n".join(lines)

    # Note: Daf advancement removed from here - now happens at 23:55 via advance_all_subscriptions_daily()
    
    print(f"DEBUG: Finishing day for sub {sub['id']} ({sub['tractate_name']})")
    
    # Refresh sub data to get current state (daf will be advanced at 23:55)
    conn = get_conn()
    updated_sub = conn.execute(
        "SELECT s.*, t.name as tractate_name FROM subscriptions s JOIN tractates t ON s.tractate_id = t.id WHERE s.id=?", (sub["id"],)
    ).fetchone()
    conn.close()
    
    if updated_sub:
        # We must PRESERVE phone and user_id during refresh if they were hydrated
        saved_phone = sub.get("phone")
        saved_user_id = sub.get("user_id")
        sub = dict(updated_sub)
        if saved_phone: sub["phone"] = saved_phone
        if saved_user_id: sub["user_id"] = saved_user_id
    
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
        
        # FILTER QUEUE: Remove the current sub if it's in the queue, 
        # and also remove any sub that already has sent questions today.
        conn = get_conn()
        filtered_queue = []
        for s_id in queue:
            if s_id == sub["id"]:
                continue
            if not has_sent_today(sub["user_id"], s_id):
                filtered_queue.append(s_id)
        
        if not filtered_queue:
            print(f"DEBUG: Queue was empty after filtering. Proceeding to closure.")
            # We continue to closure below
        elif len(filtered_queue) >= 2:
            due_subs = []
            for s_id in filtered_queue:
                r = conn.execute(
                    "SELECT s.*, t.name as tractate_name FROM subscriptions s JOIN tractates t ON s.tractate_id = t.id WHERE s.id=?", (s_id,)
                ).fetchone()
                if r: due_subs.append(dict(r))
            conn.close()
            
            # Update state with filtered queue
            if sub["phone"] in simulation_system.USER_STATES:
                simulation_system.USER_STATES[sub["phone"]] = {
                    "state": "PROCESSING_QUESTION_QUEUE", 
                    "queue": filtered_queue
                }
            
            msg = get_template("queue_next_menu", menu=_get_local_subs_menu(due_subs))
            send_sms(sub["phone"], msg, sub["user_id"])
            return
        else:
            conn.close()
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
                # Update state to the last sub before sending next question
                if sub["phone"] in simulation_system.USER_STATES:
                     simulation_system.USER_STATES[sub["phone"]] = {
                        "state": "PROCESSING_QUESTION_QUEUE", 
                        "queue": []
                    }
                # Recursively pass the empty queue
                send_next_question_or_finish(last_sub, override_queue=[])
        return

    # No queue or queue finished - Send "Study Closure" message
    print(f"DEBUG: No queue found or queue finished. Sending study closure.")
    
    # Get all active subscriptions for this user to build a combined status message
    conn = get_conn()
    # We only show the status for the specific subscription that just finished, 
    # unless it was a session with multiple subs (handled by queue check above)
    all_user_subs = conn.execute(
        "SELECT s.*, t.name as tractate_name FROM subscriptions s JOIN tractates t ON s.tractate_id = t.id WHERE s.id=? AND s.is_active=1", (sub["id"],)
    ).fetchall()
    conn.close()
    
    if all_user_subs:
        status_lines = [format_sub_status(dict(s)) for s in all_user_subs]
        combined_status = "\n".join(status_lines)
        
        # Check if the subscription that just finished is still active
        is_still_active = any(s['id'] == sub['id'] for s in all_user_subs)
        
        # If it was the last day, we might have already deactivated it or it will be deactivated at 23:55
        # But format_sub_status already adds the "tomorrow we finish" message.
        
        closure_msg = get_template("study_closure", sub_info=combined_status)
        
        # USE A SMALL DELAY TO ENSURE ORDER
        import time
        time.sleep(0.5)
        
        send_sms(sub["phone"], closure_msg, sub["user_id"])

    # Clear state completely since day is finished
    if sub["phone"] in simulation_system.USER_STATES:
        del simulation_system.USER_STATES[sub["phone"]]

@log_function_entry
def send_next_question_or_finish(sub: dict, override_queue: list = None):
    """
    Check for the next question to send in the current range.
    If no more questions (or reached daily limit), send the 'tomorrow study' message.
    """
    import simulation_system
    
    # Ensure we have phone and user_id in the sub dictionary
    if "phone" not in sub or "user_id" not in sub or "end_daf" not in sub:
        print(f"DEBUG: send_next_question_or_finish missing phone/user_id in sub. Hydrating for sub_id: {sub.get('id')}")
        conn = get_conn()
        full_sub = conn.execute(
            "SELECT s.*, t.name as tractate_name, t.id as tractate_id, u.phone, u.id as user_id "
            "FROM subscriptions s "
            "JOIN tractates t ON t.id = s.tractate_id "
            "JOIN users u ON u.id = s.user_id "
            "WHERE s.id = ?",
            (sub["id"],)
        ).fetchone()
        conn.close()
        if full_sub:
            sub = dict(full_sub)
        else:
            print(f"ERROR: Could not hydrate sub {sub.get('id')} - not found.")
            return

    # 1. Check daily limit (e.g., 2 questions per day)
    conn = get_conn()
    
    # Use DB specific date functions
    is_postgres = bool(os.environ.get("DATABASE_URL"))
    if is_postgres:
        count_row = conn.execute(
            "SELECT COUNT(*) FROM sent_questions WHERE subscription_id=? AND sent_at::date = CURRENT_DATE",
            (sub["id"],)
        ).fetchone()
    else:
        count_row = conn.execute(
            "SELECT COUNT(*) FROM sent_questions WHERE subscription_id=? AND date(sent_at) = date('now')",
            (sub["id"],)
        ).fetchone()

    conn.close()
    
    daily_limit = 2 # This could be configurable in the future
    
    if count_row and count_row[0] >= daily_limit:
        print(f"Sub {sub['id']} reached daily limit of {daily_limit} questions (found {count_row[0]}).")
        finish_subscription_day(sub, override_queue=override_queue)
        return False

    already_sent = get_already_sent_ids(sub["user_id"], sub["id"])
    
    start_f = sub["current_daf"]
    end_f = start_f + sub["dafim_per_day"] - 0.01
    
    # Cap end_f at subscription's end_daf
    if end_f > sub["end_daf"]:
        end_f = sub["end_daf"]

    daily_selection = select_questions_for_range(
        sub["tractate_id"], start_f, end_f, already_sent, max_questions=1,
        question_type_pref=sub.get("question_type", "all")
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
        
        # We check if this is the last question for today
        # count_row[0] is questions sent BEFORE this one. 
        # c2[0] is questions sent INCLUDING this one.
        is_last = (c2[0] >= daily_limit)
        conn.close()
        
        msg = format_question_sms(q, 1, sub["tractate_name"], is_last=is_last)
        
        # Ensure we don't have a race if finish_subscription_day is somehow called
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
            print(f"DEBUG: No questions found for sub {sub['id']} on daf {sub['current_daf']}")
            
            # Note: Daf advancement removed - happens at 23:55 via advance_all_subscriptions_daily()
            # Calculate what tomorrow's study will be (current_daf will be advanced at 23:55)
            next_start = sub["current_daf"] + sub["dafim_per_day"]
            next_end = next_start + sub["dafim_per_day"] - 0.5
            study_range = f"{float_to_daf_str(next_start)}"
            if sub["dafim_per_day"] > 0.5:
                study_range += f" עד {float_to_daf_str(next_end)}"
            
            msg = get_template("no_questions_today", next_study=study_range, hour=sub["send_hour"])
            
            # Check if this is the end
            if sub["current_daf"] >= sub["end_daf"] - 0.01:
                # No more questions and we reached the end
                range_str = f"{float_to_daf_str(sub['start_daf'])} - {float_to_daf_str(sub['end_daf'])}"
                msg = get_template("subscription_completed", 
                                  tractate_name=sub["tractate_name"],
                                  range=range_str)
                # Deactivate
                conn = get_conn()
                conn.execute("UPDATE subscriptions SET is_active=0 WHERE id=?", (sub["id"],))
                conn.commit()
                conn.close()

            send_sms(sub["phone"], msg, sub["user_id"])
        else:
            print(f"DEBUG: Already sent {count_row[0]} questions today. Finishing day for sub {sub['id']}")
            finish_subscription_day(sub, override_queue=override_queue)
        return False

@log_function_entry
def send_daily_questions(sub: dict):
    """Select and send the FIRST question for a single subscription."""
    # Safety check: don't send twice in the same calendar day (initial trigger)
    if has_sent_today(sub["user_id"], sub["id"]):
        # print(f"Skipping sub {sub['id']} - already sent today.")
        return

    # Check if there are pending admin messages for this user
    conn = get_conn()
    pending = conn.execute(
        "SELECT id, message FROM pending_admin_messages WHERE user_id=? AND sent_at IS NULL",
        (sub["user_id"],)
    ).fetchall()
    
    if pending:
        for p in pending:
            send_sms(sub["phone"], p["message"], sub["user_id"])
            conn.execute(
                "UPDATE pending_admin_messages SET sent_at=CURRENT_TIMESTAMP WHERE id=?",
                (p["id"],)
            )
        conn.commit()
    conn.close()

    # Try to send the first question
    send_next_question_or_finish(sub)


@log_function_entry
def get_israel_time():
    """Get current time in Israel (UTC+3)."""
    # Assuming the server is in UTC. If it's not, we might need a more robust way.
    # But based on the user's "3 hours back" c
    # ent, UTC+3 is the goal.
    from datetime import datetime, timedelta
    return datetime.utcnow() + timedelta(hours=3)

@log_function_entry
def has_pending_question(user_id: int, same_day_only: bool = False) -> bool:
    """
    Check if the user has any question that hasn't been answered yet.
    If same_day_only is True, only check for questions sent today.
    """
    conn = get_conn()
    is_postgres = bool(os.environ.get("DATABASE_URL"))
    query = "SELECT id FROM sent_questions WHERE user_id=? AND responded_at IS NULL"
    params = [user_id]
    
    if same_day_only:
        if is_postgres:
            query += " AND sent_at::date = CURRENT_DATE"
        else:
            query += " AND date(sent_at) = date('now')"
        
    query += " LIMIT 1"
    row = conn.execute(query, params).fetchone()
    conn.close()
    return row is not None

@log_function_entry
def advance_all_subscriptions_daily():
    """
    Run at 23:55 daily to advance all active subscriptions to the next day.
    This ensures daf progression happens once per day, separate from question sending.
    """
    conn = get_conn()
    active_subs = conn.execute(
        """
        SELECT s.id, s.dafim_per_day, s.current_daf, s.end_daf, s.start_daf, t.name as tractate_name, u.phone, u.id as user_id
        FROM subscriptions s
        JOIN tractates t ON s.tractate_id = t.id
        JOIN users u ON s.user_id = u.id
        WHERE s.is_active = 1
        """
    ).fetchall()
    
    advanced_count = 0
    completed_count = 0
    
    # Collect completion messages to send AFTER closing the connection
    completion_messages = []
    
    for sub in active_subs:
        sub_dict = dict(sub)
        # Use small epsilon to prevent float precision issues
        if sub_dict["current_daf"] >= sub_dict["end_daf"] - 0.01:
            # Already reached or passed end_daf yesterday
            conn.execute("UPDATE subscriptions SET is_active=0 WHERE id=?", (sub_dict["id"],))
            
            range_str = f"{float_to_daf_str(sub_dict['start_daf'])} - {float_to_daf_str(sub_dict['end_daf'])}"
            msg = get_template("subscription_completed", 
                              tractate_name=sub_dict["tractate_name"],
                              range=range_str)
            
            completion_messages.append((sub_dict["phone"], msg, sub_dict["user_id"]))
            completed_count += 1
            continue

        new_daf = sub_dict["current_daf"] + sub_dict["dafim_per_day"]
        
        # If the NEXT daf would be past the end, we still advance to it but mark that it's the last day
        # Actually, if we're at 23:55, we're advancing to tomorrow.
        # If current_daf is 14.5 and end_daf is 14.5, we should have completed it today.
        
        if new_daf > sub_dict["end_daf"] + 0.01:
             # This means we would go past the limit tomorrow.
             # We cap it at the end_daf so they at least finish exactly on it.
             new_daf = sub_dict["end_daf"]
        
        conn.execute("UPDATE subscriptions SET current_daf = ? WHERE id=?", 
                    (new_daf, sub_dict["id"]))
        advanced_count += 1
    
    conn.commit()
    conn.close()
    
    # Send completion messages outside the DB connection to avoid locks
    for phone, msg, uid in completion_messages:
        send_sms(phone, msg, uid)
    
    print(f"✅ Daily advancement complete: {advanced_count} subscriptions advanced, {completed_count} completed")
    return advanced_count, completed_count

@log_function_entry
def check_user_inactivity():
    """
    Find users who haven't responded for > 7 days and deactivate their subscriptions.
    Run once daily.
    """
    conn = get_conn()
    is_postgres = bool(os.environ.get("DATABASE_URL"))
    
    # Identify users who haven't responded for 7 days and haven't been notified yet
    if is_postgres:
        query = """
            SELECT id, name, phone FROM users 
            WHERE inactive_notified = 0 
            AND last_response_at < CURRENT_TIMESTAMP - INTERVAL '7 days'
            AND EXISTS (SELECT 1 FROM subscriptions WHERE user_id = users.id AND is_active = 1)
        """
    else:
        query = """
            SELECT id, name, phone FROM users 
            WHERE inactive_notified = 0 
            AND last_response_at < datetime('now', '-7 days')
            AND EXISTS (SELECT 1 FROM subscriptions WHERE user_id = users.id AND is_active = 1)
        """
    
    inactive_users = [dict(u) for u in conn.execute(query).fetchall()]
    
    if not inactive_users:
        conn.close()
        return 0

    processed_count = 0
    for user in inactive_users:
        # 1. Deactivate all their active subscriptions to stop progress
        conn.execute("UPDATE subscriptions SET is_active = 0 WHERE user_id = ?", (user['id'],))
        # 2. Mark user as notified
        conn.execute("UPDATE users SET inactive_notified = 1 WHERE id = ?", (user['id'],))
        processed_count += 1
        
    conn.commit()
    conn.close()
    
    # Send notifications OUTSIDE the main transaction to avoid "database is locked"
    for user in inactive_users:
        msg = get_template("inactivity_pause", name=user['name'])
        send_sms(user['phone'], msg, user['id'])
        
    if processed_count > 0:
        print(f"😴 Inactivity check: {processed_count} users deactivated due to 7+ days of silence.")
    return processed_count

@log_function_entry
def run_hour(hour: int = None, force_date: date = None):
    """Main entry point for scheduled task with parallel SMS sending."""
    import time
    from concurrent.futures import ThreadPoolExecutor, as_completed
    
    israel_now = get_israel_time()
    today = force_date or date.today()
    if hour is None:
        hour = israel_now.hour
    
    # Special case: 23:55 - advance all subscriptions for tomorrow
    if hour == 23 and israel_now.minute >= 55:
        if get_live_mode():
            print("🕐 Running daily subscription advancement and inactivity check at 23:55...")
            advance_all_subscriptions_daily()
            check_user_inactivity()
        return
    
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
    
    # Special case: Saturday 21:00 (or first run after 21:00) - send all Shabbat messages
    elif day_of_week == 5 and hour == 21:
        # We check if we have already run the "catch-up" today to avoid double processing if run twice after 21:00
        # But has_sent_today already protects individual subscriptions.
        conn = get_conn()
        rows = conn.execute(
            """
            SELECT s.*, t.name as tractate_name, u.phone, u.name as user_name
            FROM subscriptions s
            JOIN tractates t ON s.tractate_id = t.id
            JOIN users u ON s.user_id = u.id
            WHERE s.is_active=1
            AND (s.pause_until IS NULL OR s.pause_until <= ?)
            """,
            (today.isoformat(),),
        ).fetchall()
        conn.close()
        
        all_subs = [dict(r) for r in rows]
        for sub in all_subs:
            # Catch all messages from 00:00 to current hour (including 21:00)
            if 0 <= sub['send_hour'] <= hour:
                due.append(sub)
        print(f"Saturday {hour}:00: Catching all Shabbat messages up to now. Count: {len(due)}")

    else:
        # Normal hour processing
        due = get_due_subscriptions(hour, today.isoformat())

    if due:
        start_time = time.time()
        try:
            print(f"Hour {hour}: Processing {len(due)} subscriptions in parallel.")
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

        def process_user_subs(uid, subs):
            """Process subscriptions for a single user (thread-safe)"""
            try:
                # Multi-subscription check: 
                if has_pending_question(uid, same_day_only=True):
                    print(f"User {uid} already has a pending question from today. Skipping for now.")
                    return
                
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

        # Use ThreadPoolExecutor for parallel processing with batching
        # Process in batches of 50 users with 1-second delays between batches
        # This allows webhooks to be processed during the delays
        batch_size = 50
        max_workers = min(20, batch_size)  # Max 20 concurrent threads per batch
        
        user_items = list(user_due.items())
        total_users = len(user_items)
        processed_count = 0
        
        for batch_start in range(0, total_users, batch_size):
            batch_end = min(batch_start + batch_size, total_users)
            batch = user_items[batch_start:batch_end]
            batch_num = (batch_start // batch_size) + 1
            total_batches = (total_users + batch_size - 1) // batch_size
            
            print(f"📦 Processing batch {batch_num}/{total_batches} ({len(batch)} users)...")
            
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {executor.submit(process_user_subs, uid, subs): uid for uid, subs in batch}
                
                for future in as_completed(futures):
                    uid = futures[future]
                    try:
                        future.result()
                        processed_count += 1
                    except Exception as e:
                        print(f"❌ Thread error for user {uid}: {e}")
            
            # Add delay between batches (except after the last batch)
            if batch_end < total_users:
                print(f"⏸️  Pausing 1 second before next batch... ({processed_count}/{total_users} processed)")
                time.sleep(1)
        
        elapsed = time.time() - start_time
        print(f"✅ Completed processing {total_users} users in {elapsed:.2f} seconds")

if __name__ == "__main__":
    run_hour()
