"""
simulation_system.py - SMS bot simulation with numeric menu and states
"""
import os
import sys
from datetime import datetime, timedelta
from registration import register_user, subscribe, get_all_tractates, get_user_subscriptions, get_template, find_tractate_by_name
from scheduler import send_daily_questions, has_sent_today, send_next_question_or_finish
from database import get_conn, float_to_daf_str, daf_to_float
from sms_service import get_sms_history, send_sms, receive_sms
from state_manager import get_user_state, set_user_state, clear_user_state, update_user_state_data

# Backward compatibility: Keep USER_STATES as a proxy to DB
class UserStatesProxy:
    """Proxy dict that reads/writes to database instead of memory"""
    def get(self, phone, default=None):
        state = get_user_state(phone)
        return state if state else default
    
    def __getitem__(self, phone):
        state = get_user_state(phone)
        if state is None:
            raise KeyError(phone)
        return state
    
    def __setitem__(self, phone, value):
        if isinstance(value, dict) and "state" in value:
            state_name = value.pop("state")
            set_user_state(phone, state_name, **value)
        else:
            raise ValueError("State must be a dict with 'state' key")
    
    def __delitem__(self, phone):
        clear_user_state(phone)
    
    def __contains__(self, phone):
        return get_user_state(phone) is not None
    
    def clear(self):
        """Clear all states (for testing)"""
        conn = get_conn()
        conn.execute("DELETE FROM user_states")
        conn.commit()
        conn.close()

USER_STATES = UserStatesProxy()

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def handle_unregistered_user(phone, message):
    # Global "0" handler to reset state/cancel registration
    if message.strip() == "0":
        if phone in USER_STATES:
            del USER_STATES[phone]
        send_sms(phone, get_template("unregistered_instructions"))
        return

    state_info = USER_STATES.get(phone)

    if state_info and state_info["state"] == "AWAITING_REG_STEP_2":
        # We handle this in handle_registered_user since user is already created after step 1
        return

    parts = [p.strip() for p in message.split(',')]
    # Step 1: name, last_name, city, age
    if len(parts) == 4:
        try:
            name, last_name, city = parts[0], parts[1], parts[2]
            age = int(parts[3])
            user_id = register_user(phone, name, last_name, city, age)
            
            # Update state to step 2
            USER_STATES[phone] = {"state": "AWAITING_REG_STEP_2"}
            send_sms(phone, get_template("registration_step_2_instructions", name=name))
            return
        except Exception as e:
            print(f"DEBUG Step 1 Error: {e}")
            send_sms(phone, get_template("error_parsing_registration"))
            return

    send_sms(phone, get_template("unregistered_instructions"))

def get_subs_menu(subs):
    lines = []
    for i, s in enumerate(subs, 1):
        range_str = f"({float_to_daf_str(s['start_daf'])} - {float_to_daf_str(s['end_daf'])})"
        lines.append(f"{i}. {s['tractate_name']} {range_str}")
    return "\n".join(lines)

def handle_registered_user(phone, user, message):
    # Global "0" handler to return to main menu
    clean_msg = message.strip().lower()
    if clean_msg == "0":
        if phone in USER_STATES:
            print(f"DEBUG: Resetting state for {phone} (was {USER_STATES[phone]['state']})")
            del USER_STATES[phone]
        else:
            print(f"DEBUG: No state to reset for {phone}")
        send_sms(phone, get_template(template_name="main_menu", name=user["name"]))
        return

    state_info = USER_STATES.get(phone)
    print(f"DEBUG: Processing message '{clean_msg}' for phone {phone}, current state: {state_info['state'] if state_info else 'None'}")

    # NEW ARCHITECTURE: Check STATE first. Everything depends on the current active process.
    if state_info:
        # 1. State: AWAITING_ANSWER
        if state_info["state"] == "AWAITING_ANSWER":
            # The user is in the middle of answering a question. 
            # We don't try to parse anything else until they answer or press 0.
            
            # Clean punctuation from the end to support "כן." or "לא," etc.
            stripped_msg = clean_msg.strip(".,!?\"'")
            
            if stripped_msg in ["כן", "לא", "ידעתי", "לא ידעתי", "כ", "ל"]:
                conn = get_conn()
                last_q = conn.execute(
                    "SELECT id, subscription_id, question_text FROM sent_questions WHERE user_id=? AND responded_at IS NULL ORDER BY sent_at DESC LIMIT 1", 
                    (user["id"],)
                ).fetchone()
                
                if last_q:
                    conn.execute("UPDATE sent_questions SET responded_at=?, response_text=? WHERE id=?", (datetime.now().isoformat(), message, last_q["id"]))
                    conn.commit()
                    
                    sub_id = last_q["subscription_id"]
                    sub_row = conn.execute(
                        "SELECT s.*, t.name as tractate_name, u.phone, u.name as user_name "
                        "FROM subscriptions s "
                        "JOIN tractates t ON s.tractate_id = t.id "
                        "JOIN users u ON s.user_id = u.id "
                        "WHERE s.id=?", (sub_id,)
                    ).fetchone()
                    conn.close()
                    
                    if sub_row:
                        # Keep the queue if it exists! We only change the state temporarily
                        old_queue = state_info.get("queue")
                        if old_queue:
                            USER_STATES[phone] = {"state": "PROCESSING_QUESTION_QUEUE", "queue": old_queue}
                        else:
                            del USER_STATES[phone] # Clear answer state
                            
                        from scheduler import send_next_question_or_finish
                        send_next_question_or_finish(dict(sub_row))
                        return
                
                # Fallback if DB didn't have the question for some reason
                conn.close()
                if "queue" in state_info:
                    USER_STATES[phone] = {"state": "PROCESSING_QUESTION_QUEUE", "queue": state_info["queue"]}
                else:
                    del USER_STATES[phone]
                send_sms(phone, "לא מצאתי שאלה פתוחה לשייך אליה את התשובה. חזרנו לתפריט הראשי.")
                return
            else:
                # User sent something else while we wait for an answer
                send_sms(phone, "כדי לענות על השאלה יש לשלוח 'כן' או 'לא'.\nלחזרה לתפריט הראשי ולביטול השאלה שלח 0.")
                return

        # 2. State: AWAITING_REG_STEP_2
        if state_info["state"] == "AWAITING_REG_STEP_2":
            # New flexible parsing logic: Masechta [Range]
            match_obj, matched_text, is_in_db = find_tractate_by_name(message)
            
            if matched_text:
                if not is_in_db:
                    send_sms(phone, get_template("tractate_not_supported", tractate=matched_text))
                    return

                tractate_obj = match_obj
                try:
                    remaining = message[len(matched_text):].strip()
                    # Normalizing delimiters
                    norm_rem = remaining.replace(',', ' ')
                    
                    # Defaults
                    start_f = 2.0
                    end_f = 100.0
                    if 'total_dafim' in tractate_obj:
                         end_f = float(tractate_obj['total_dafim'])

                    # Advanced Parsing for Range only
                    if " עד " in norm_rem:
                        parts_range = norm_rem.split(" עד ")
                        start_str = parts_range[0].strip()
                        start_f = daf_to_float(start_str)
                        
                        end_part_full = parts_range[1].strip()
                        end_tokens = end_part_full.split()
                        
                        if len(end_tokens) >= 2 and end_tokens[1] in ('ע"א', 'ע"ב'):
                            end_str = f"{end_tokens[0]} {end_tokens[1]}"
                            end_f = daf_to_float(end_str)
                        else:
                            end_str = end_tokens[0]
                            # if end is just daf, include amud b
                            if 'ע"א' not in end_str and 'ע"ב' not in end_str:
                                 end_f = daf_to_float(end_str) + 0.5
                            else:
                                 end_f = daf_to_float(end_str)
                    else:
                        params = norm_rem.split()
                        if params:
                            if len(params) >= 2 and params[1] in ('ע"א', 'ע"ב'):
                                start_str = f"{params[0]} {params[1]}"
                                idx = 2
                            else:
                                start_str = params[0]
                                idx = 1
                            start_f = daf_to_float(start_str)
                            
                            if idx < len(params) and params[idx] == 'עד':
                                idx += 1
                                if idx < len(params):
                                    if idx + 1 < len(params) and params[idx+1] in ('ע"א', 'ע"ב'):
                                        end_str = f"{params[idx]} {params[idx+1]}"
                                        idx += 2
                                        end_f = daf_to_float(end_str)
                                    else:
                                        end_str = params[idx]
                                        idx += 1
                                        if 'ע"א' not in end_str and 'ע"ב' not in end_str:
                                             end_f = daf_to_float(end_str) + 0.5
                                        else:
                                             end_f = daf_to_float(end_str)
                    
                    USER_STATES[phone] = {
                        "state": "AWAITING_REG_STEP_3",
                        "tractate_id": tractate_obj["id"],
                        "tractate_name": tractate_obj["name"],
                        "start_daf": start_f,
                        "end_daf": end_f
                    }
                    send_sms(phone, get_template("registration_step_3_instructions"))
                    return
                except Exception as e:
                    print(f"DEBUG Step 2 Error: {e}")
                    send_sms(phone, "שגיאה בפרטי המסכת. אנא שלח בפורמט: מסכת דף ועמוד התחלה עד דף ועמוד סיום\nלדוגמה: ברכות ב ע\"א עד י ע\"ב")
                    return
            else:
                send_sms(phone, get_template("tractate_not_found", tractate=message.split()[0] if message.split() else message))
                return

        # 3. State: AWAITING_REG_STEP_3
        if state_info["state"] == "AWAITING_REG_STEP_3":
            try:
                # Expected format: Rate, Hour or Rate Hour
                clean_msg = message.replace(',', ' ').strip()
                parts = clean_msg.split()
                if len(parts) < 2:
                     send_sms(phone, "אנא שלח הספק ושעה מופרדים בפסיק או רווח.\nלדוגמא: 1.5, 18")
                     return
                
                rate = float(parts[0])
                hour = int(parts[1])
                
                if not (0 <= hour <= 23):
                    if hour == 24: hour = 0
                    else:
                        send_sms(phone, "שעה לא תקינה. אנא בחר מספר בין 01 ל-24.")
                        return

                tractate_id = state_info["tractate_id"]
                tractate_name = state_info["tractate_name"]
                start_f = state_info["start_daf"]
                end_f = state_info["end_daf"]

                from registration import subscribe as original_subscribe
                original_subscribe(user["id"], tractate_id, start_f, end_f, rate, hour)
                
                summary = f"מסכת {tractate_name} מדף {float_to_daf_str(start_f)} עד {float_to_daf_str(end_f)} בקצב של {rate} דפים ליום, בשעה {hour:02d}:00"
                
                # Clear state
                del USER_STATES[phone]
                
                send_sms(phone, get_template("registration_final_success", name=user["name"], summary=summary))
                return
            except Exception as e:
                print(f"DEBUG Step 3 Error: {e}")
                send_sms(phone, "שגיאה בפרטי ההספק או השעה. אנא ודא שהכנסת מספרים תקינים.\nלדוגמא: 1, 18")
                return

        if state_info["state"] == "PROCESSING_QUESTION_QUEUE":
            if not message.isdigit():
                send_sms(phone, "בחירה לא תקינה. אנא שלח את מספר המנוי בלבד.")
                return
            
            queue = state_info.get("queue", [])
            idx = int(message) - 1
            if idx < 0 or idx >= len(queue):
                send_sms(phone, "בחירה לא תקינה. אנא שלח מספר מהרשימה.")
                return
            
            selected_sub_id = queue.pop(idx)
            # Update state with the modified queue
            USER_STATES[phone]["queue"] = queue
            
            conn = get_conn()
            sub = conn.execute(
                "SELECT s.*, t.name as tractate_name, u.phone, u.name as user_name FROM subscriptions s JOIN tractates t ON s.tractate_id = t.id JOIN users u ON s.user_id = u.id WHERE s.id=?", (selected_sub_id,)
            ).fetchone()
            conn.close()
            
            if sub:
                from scheduler import send_next_question_or_finish
                send_next_question_or_finish(dict(sub))
            return

        if state_info["state"].startswith("AWAITING_SUB_SELECTION"):
            subs = get_user_subscriptions(user['id'])
            if not message.isdigit():
                send_sms(phone, "בחירה לא תקינה. אנא שלח את מספר המנוי בלבד.")
                return
            idx = int(message) - 1
            if idx < 0 or idx >= len(subs):
                send_sms(phone, "בחירה לא תקינה. אנא שלח מספר מהרשימה.")
                return
            
            selected_sub = subs[idx]
            original_action = state_info.get("action")
            
            if state_info["state"] == "AWAITING_SUB_SELECTION_FOR_QUESTION":
                if has_sent_today(user['id'], selected_sub['id']):
                    send_sms(phone, get_template("already_sent_today"))
                    del USER_STATES[phone]
                else:
                    from scheduler import send_next_question_or_finish
                    send_next_question_or_finish(selected_sub)
                return

            # Logic for other actions
            USER_STATES[phone] = {"state": original_action, "sub_id": selected_sub["id"]}
            if original_action == "AWAITING_UPDATE_DAF":
                send_sms(phone, get_template("ask_update_daf"))
            elif original_action == "AWAITING_PAUSE_DAYS":
                send_sms(phone, get_template("ask_pause_days"))
            elif original_action == "AWAITING_NEW_HOUR":
                send_sms(phone, get_template("ask_new_hour"))
            elif original_action == "AWAITING_UNSUBSCRIBE":
                # For unsubscribe, we don't need another step, just confirm
                conn = get_conn()
                conn.execute("UPDATE subscriptions SET is_active=0 WHERE id=?", (selected_sub["id"],))
                conn.commit()
                conn.close()
                sub_range = f"({float_to_daf_str(selected_sub['start_daf'])} - {float_to_daf_str(selected_sub['end_daf'])})"
                send_sms(phone, f"המנוי ל{selected_sub['tractate_name']} {sub_range} בוטל בהצלחה.")
                del USER_STATES[phone]
            elif original_action == "AWAITING_RESUME":
                conn = get_conn()
                conn.execute("UPDATE subscriptions SET pause_until=NULL WHERE id=?", (selected_sub["id"],))
                conn.commit()
                # Refresh to get current info
                updated = conn.execute("SELECT s.*, t.name as tractate_name FROM subscriptions s JOIN tractates t ON s.tractate_id = t.id WHERE s.id=?", (selected_sub["id"],)).fetchone()
                conn.close()
                
                if updated:
                    from scheduler import format_sub_status
                    status_line = format_sub_status(dict(updated))
                    send_sms(phone, get_template("resume_success", sub_info=status_line))
                else:
                    send_sms(phone, "ההקפאה בוטלה בהצלחה.")
                del USER_STATES[phone]
            return

        if state_info["state"] == "AWAITING_SUPPORT_CATEGORY":
            if message not in ["1", "2", "3"]:
                send_sms(phone, "בחירה לא תקינה. אנא בחר 1, 2 או 3.")
                return
            
            categories = {"1": "באג/תקלה", "2": "הצעת שיפור/שדרוג", "3": "שאלה כללית"}
            USER_STATES[phone] = {
                "state": "AWAITING_SUPPORT_MESSAGE",
                "category": categories[message]
            }
            send_sms(phone, get_template("ask_support_message"))
            return

        if state_info["state"] == "AWAITING_SUPPORT_MESSAGE":
            category = state_info.get("category")
            conn = get_conn()
            conn.execute(
                "INSERT INTO support_requests (user_id, category, message) VALUES (?, ?, ?)",
                (user["id"], category, message)
            )
            conn.commit()
            conn.close()
            
            send_sms(phone, get_template("support_request_confirmed", category=category))
            del USER_STATES[phone]
            return

        if state_info["state"] in ("AWAITING_UPDATE_DAF", "AWAITING_PAUSE_DAYS", "AWAITING_NEW_HOUR"):
            sub_id = state_info.get("sub_id")
            conn = get_conn()
            sub = conn.execute("SELECT s.*, t.name as tractate_name FROM subscriptions s JOIN tractates t ON s.tractate_id = t.id WHERE s.id=?", (sub_id,)).fetchone()
            conn.close()
            if not sub:
                send_sms(phone, "שגיאה: המנוי לא נמצא.")
                del USER_STATES[phone]
                return
            
            sub = dict(sub)
            sub_range = f"({float_to_daf_str(sub['start_daf'])} - {float_to_daf_str(sub['end_daf'])})"

            if state_info["state"] == "AWAITING_UPDATE_DAF":
                try:
                    new_daf_f = daf_to_float(message)
                    # Validation: Ensure new daf is within subscription range
                    if not (sub["start_daf"] <= new_daf_f <= sub["end_daf"]):
                        send_sms(phone, f"הדף שציינת ({float_to_daf_str(new_daf_f)}) מחוץ לטווח המנוי שלך {sub_range}.\nאנא שלח דף בתוך הטווח.")
                        return

                    conn = get_conn()
                    conn.execute("UPDATE subscriptions SET current_daf=? WHERE id=?", (new_daf_f, sub["id"]))
                    conn.commit()
                    conn.close()
                    send_sms(phone, f"מנוי {sub['tractate_name']} {sub_range} עודכן ל-{float_to_daf_str(new_daf_f)}!")
                    del USER_STATES[phone]
                except:
                    send_sms(phone, "פורמט דף לא תקין. נסה שוב.")
                return

            if state_info["state"] == "AWAITING_PAUSE_DAYS":
                if not message.isdigit():
                    send_sms(phone, "אנא ציין מספר ימים (למשל: '5').")
                    return
                days = int(message)
                until_date = (datetime.now() + timedelta(days=days)).date()
                conn = get_conn()
                conn.execute("UPDATE subscriptions SET pause_until=? WHERE id=?", (until_date.isoformat(), sub["id"]))
                conn.commit()
                conn.close()
                send_sms(phone, f"מנוי {sub['tractate_name']} {sub_range} הוקפא ל-{days} ימים.")
                del USER_STATES[phone]
                return

            if state_info["state"] == "AWAITING_NEW_HOUR":
                if not message.isdigit():
                    send_sms(phone, "אנא ציין שעה (למשל: '18').")
                    return
                hour = int(message)
                if 0 <= hour <= 23:
                    conn = get_conn()
                    conn.execute("UPDATE subscriptions SET send_hour=? WHERE id=?", (hour, sub["id"]))
                    conn.commit()
                    conn.close()
                    send_sms(phone, f"שעת השליחה למנוי {sub['tractate_name']} {sub_range} עודכנה ל-{hour}:00.")
                    del USER_STATES[phone]
                else:
                    send_sms(phone, "שעה לא תקינה (0-23).")
                return

    if message == '1':
        all_subs = get_user_subscriptions(user['id'])
        if not all_subs:
            send_sms(phone, "אין לך מנויים פעילים.")
            return

        # Filter only those needing questions
        needing_questions = [s for s in all_subs if not has_sent_today(user['id'], s['id'])]

        if not needing_questions:
            from scheduler import format_sub_status
            summary_lines = [format_sub_status(s) for s in all_subs]
            send_sms(phone, get_template("already_sent_summary", summary="\n".join(summary_lines)))
        elif len(needing_questions) == 1:
            from scheduler import send_next_question_or_finish
            send_next_question_or_finish(needing_questions[0])
        else:
            USER_STATES[phone] = {"state": "AWAITING_SUB_SELECTION_FOR_QUESTION"}
            send_sms(phone, get_template("choose_subscription_manual_question", menu=get_subs_menu(needing_questions)))

    elif message == '2':
        subs = get_user_subscriptions(user['id'])
        if len(subs) > 1:
            USER_STATES[phone] = {"state": "AWAITING_SUB_SELECTION", "action": "AWAITING_UPDATE_DAF"}
            send_sms(phone, get_template("choose_subscription_update_daf", menu=get_subs_menu(subs)))
        else:
            USER_STATES[phone] = {"state": "AWAITING_UPDATE_DAF", "sub_id": subs[0]["id"] if subs else None}
            send_sms(phone, get_template("ask_update_daf"))

    elif message == '3':
        subs = get_user_subscriptions(user['id'])
        if len(subs) > 1:
            USER_STATES[phone] = {"state": "AWAITING_SUB_SELECTION", "action": "AWAITING_PAUSE_DAYS"}
            send_sms(phone, get_template("choose_subscription_pause", menu=get_subs_menu(subs)))
        else:
            USER_STATES[phone] = {"state": "AWAITING_PAUSE_DAYS", "sub_id": subs[0]["id"] if subs else None}
            send_sms(phone, get_template("ask_pause_days"))

    elif message == '4':
        subs = [s for s in get_user_subscriptions(user['id']) if s.get('pause_until')]
        if len(subs) > 1:
            USER_STATES[phone] = {"state": "AWAITING_SUB_SELECTION", "action": "AWAITING_RESUME"}
            send_sms(phone, get_template("choose_subscription_resume", menu=get_subs_menu(subs)))
        elif len(subs) == 1:
            conn = get_conn()
            conn.execute("UPDATE subscriptions SET pause_until=NULL WHERE id=?", (subs[0]["id"],))
            conn.commit()
            # Refresh to get current info
            updated = conn.execute("SELECT s.*, t.name as tractate_name FROM subscriptions s JOIN tractates t ON s.tractate_id = t.id WHERE s.id=?", (subs[0]["id"],)).fetchone()
            conn.close()
            
            if updated:
                from scheduler import format_sub_status
                status_line = format_sub_status(dict(updated))
                send_sms(phone, get_template("resume_success", sub_info=status_line))
            else:
                send_sms(phone, get_template("resume_success", sub_info=""))
        else:
            send_sms(phone, "אין לך מנויים מוקפאים.")

    elif message == '5':
        subs = get_user_subscriptions(user['id'])
        if len(subs) > 1:
            USER_STATES[phone] = {"state": "AWAITING_SUB_SELECTION", "action": "AWAITING_NEW_HOUR"}
            send_sms(phone, get_template("choose_subscription_hour", menu=get_subs_menu(subs)))
        else:
            USER_STATES[phone] = {"state": "AWAITING_NEW_HOUR", "sub_id": subs[0]["id"] if subs else None}
            send_sms(phone, get_template("ask_new_hour"))

    elif message == '6':
        subs = get_user_subscriptions(user['id'])
        if len(subs) >= 5:
            send_sms(phone, "הגעת למגבלת המנויים האפשרית (5).\nלא ניתן להוסיף מסכתות נוספות כעת.")
        else:
            USER_STATES[phone] = {"state": "AWAITING_REG_STEP_2"}
            send_sms(phone, get_template("registration_step_2_instructions", name=user["name"]))

    elif message == '7':
        subs = get_user_subscriptions(user['id'])
        if len(subs) > 1:
            USER_STATES[phone] = {"state": "AWAITING_SUB_SELECTION", "action": "AWAITING_UNSUBSCRIBE"}
            send_sms(phone, get_template("choose_subscription_unsubscribe", menu=get_subs_menu(subs)))
        else:
            conn = get_conn()
            conn.execute("UPDATE subscriptions SET is_active=0 WHERE user_id=?", (user["id"],))
            conn.commit()
            conn.close()
            send_sms(phone, get_template("unsubscribe_success"))
    elif message == '8':
        USER_STATES[phone] = {"state": "AWAITING_SUPPORT_CATEGORY"}
        send_sms(phone, get_template("support_category_menu"))
    else:
        send_sms(phone, get_template(template_name="main_menu", name=user["name"]))

def main():
    clear_screen()
    print("=== Gemara SMS Simulation (Updated) ===")
    phone = input("Enter phone number: ").strip()
    if not phone: return
    while True:
        try:
            print(f"\n--- Session: {phone} ---")
            message = input("SMS Message (or 'q' to quit): ").strip()
            if message.lower() == 'q': break
            if not message: continue
            
            # Check daily limit - OUTGOING messages only, calendar day
            conn = get_conn()
            is_postgres = bool(os.environ.get("DATABASE_URL"))
            if is_postgres:
                count_query = "SELECT COUNT(*) FROM sms_log WHERE phone=? AND direction='out' AND sent_at::date = CURRENT_DATE"
            else:
                count_query = "SELECT COUNT(*) FROM sms_log WHERE phone=? AND direction='out' AND date(sent_at) = date('now')"
            
            daily_count = conn.execute(count_query, (phone,)).fetchone()[0]
            if daily_count >= 30:
                print(f"Blocked incoming SMS from {phone}: Daily limit of 30 OUTGOING SMS reached.")
                conn.close()
                continue
                
            receive_sms(phone, message)
            user = conn.execute("SELECT * FROM users WHERE phone=?", (phone,)).fetchone()
            conn.close()
            if not user: handle_unregistered_user(phone, message)
            else: handle_registered_user(phone, user, message)
        except EOFError: break
        except Exception as e: print(f"Error: {e}")

if __name__ == "__main__":
    main()
