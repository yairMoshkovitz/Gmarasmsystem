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

# Global state to track multi-step conversations
USER_STATES = {}

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
                        del USER_STATES[phone] # Clear answer state
                        from scheduler import send_next_question_or_finish
                        send_next_question_or_finish(dict(sub_row))
                        return
                
                # Fallback if DB didn't have the question for some reason
                conn.close()
                del USER_STATES[phone]
                send_sms(phone, "לא מצאתי שאלה פתוחה לשייך אליה את התשובה. חזרנו לתפריט הראשי.")
                return
            else:
                # User sent something else while we wait for an answer
                send_sms(phone, "כדי לענות על השאלה יש לשלוח 'כן' או 'לא'.\nלחזרה לתפריט הראשי ולביטול השאלה שלח 0.")
                return

        # 2. State: AWAITING_REG_STEP_2
        if state_info["state"] == "AWAITING_REG_STEP_2":
            # New flexible parsing logic: Masechta [Range] [Rate] [Hour]
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
                    rate = 1.0
                    hour = 18

                    # Advanced Parsing
                    if " עד " in norm_rem:
                        parts_range = norm_rem.split(" עד ")
                        start_str = parts_range[0].strip()
                        start_f = daf_to_float(start_str)
                        
                        end_part_full = parts_range[1].strip()
                        end_tokens = end_part_full.split()
                        
                        if len(end_tokens) >= 2 and end_tokens[1] in ('ע"א', 'ע"ב'):
                            end_str = f"{end_tokens[0]} {end_tokens[1]}"
                            end_f = daf_to_float(end_str)
                            remaining_params = end_tokens[2:]
                        else:
                            end_str = end_tokens[0]
                            # if end is just daf, include amud b
                            if 'ע"א' not in end_str and 'ע"ב' not in end_str:
                                 end_f = daf_to_float(end_str) + 0.5
                            else:
                                 end_f = daf_to_float(end_str)
                            remaining_params = end_tokens[1:]
                            
                        if len(remaining_params) >= 1:
                            try: rate = float(remaining_params[0])
                            except: pass
                        if len(remaining_params) >= 2:
                            try: hour = int(remaining_params[1])
                            except: pass
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
                            
                            if idx < len(params):
                                try: rate = float(params[idx]); idx += 1
                                except: pass
                            if idx < len(params):
                                try: hour = int(params[idx]); idx += 1
                                except: pass
                    
                    from database import load_questions
                    questions = load_questions(tractate_obj['id'])
                    found_q = False
                    for q in questions:
                        from questions_engine import get_daf_range_for_question
                        q_start, q_end = get_daf_range_for_question(q)
                        if q_start >= start_f and q_start <= end_f:
                            found_q = True
                            break
                    
                    if not found_q:
                        send_sms(phone, get_template("no_questions_in_range", 
                                                     tractate=tractate_obj['name'], 
                                                     start=float_to_daf_str(start_f), 
                                                     end=float_to_daf_str(end_f)))

                    subscribe(user["id"], tractate_obj["id"], start_f, end_f, rate, hour)
                    if phone in USER_STATES:
                        del USER_STATES[phone]
                    return
                except Exception as e:
                    print(f"DEBUG Step 2 Error: {e}")
                    send_sms(phone, "שגיאה בפרטי המסכת. אנא שלח בפורמט: מסכת, דף התחלה עד דף סיום, קצב, שעה\nלדוגמה: ברכות ב עד י 1 18")
                    return
            else:
                send_sms(phone, get_template("tractate_not_found", tractate=message.split()[0] if message.split() else message))
                return

        if state_info["state"] in ("AWAITING_UPDATE_DAF", "AWAITING_PAUSE_DAYS", "AWAITING_NEW_HOUR", "AWAITING_UNSUBSCRIBE", "AWAITING_RESUME"):
            subs = get_user_subscriptions(user['id'])
            if not subs:
                send_sms(phone, "אין לך מנויים פעילים.")
                del USER_STATES[phone]
                return

            # Combined input: "1 23b" or just "1" if only one sub exists
            parts = message.split(None, 1)
            sub_index = -1
            action_value = ""

            if len(subs) == 1:
                sub_index = 0
                action_value = message
            elif len(parts) >= 1 and parts[0].isdigit():
                sub_index = int(parts[0]) - 1
                if len(parts) > 1:
                    action_value = parts[1]
            
            if sub_index < 0 or sub_index >= len(subs):
                send_sms(phone, "בחירה לא תקינה. אנא שלח את מספר המנוי מהרשימה.")
                return

            sub = subs[sub_index]
            sub_range = f"({float_to_daf_str(sub['start_daf'])} - {float_to_daf_str(sub['end_daf'])})"
            
            if state_info["state"] == "AWAITING_UPDATE_DAF":
                if not action_value:
                    send_sms(phone, "אנא ציין את הדף החדש אחרי מספר המנוי (למשל: '1 כ ע\"א').")
                    return
                try:
                    new_daf_f = daf_to_float(action_value)
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
                if not action_value or not action_value.isdigit():
                    send_sms(phone, "אנא ציין את מספר הימים אחרי מספר המנוי (למשל: '1 5').")
                    return
                days = int(action_value)
                until_date = (datetime.now() + timedelta(days=days)).date()
                conn = get_conn()
                conn.execute("UPDATE subscriptions SET pause_until=? WHERE id=?", (until_date.isoformat(), sub["id"]))
                conn.commit()
                conn.close()
                send_sms(phone, f"מנוי {sub['tractate_name']} {sub_range} הוקפא ל-{days} ימים.")
                del USER_STATES[phone]
                return

            if state_info["state"] == "AWAITING_NEW_HOUR":
                if not action_value or not action_value.isdigit():
                    send_sms(phone, "אנא ציין את השעה החדשה אחרי מספר המנוי (למשל: '1 18').")
                    return
                hour = int(action_value)
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

            if state_info["state"] == "AWAITING_UNSUBSCRIBE":
                conn = get_conn()
                conn.execute("UPDATE subscriptions SET is_active=0 WHERE id=?", (sub["id"],))
                conn.commit()
                conn.close()
                send_sms(phone, f"המנוי ל{sub['tractate_name']} {sub_range} בוטל בהצלחה.")
                del USER_STATES[phone]
                return

            if state_info["state"] == "AWAITING_RESUME":
                conn = get_conn()
                conn.execute("UPDATE subscriptions SET pause_until=NULL WHERE id=?", (sub["id"],))
                conn.commit()
                conn.close()
                send_sms(phone, f"ההקפאה למנוי {sub['tractate_name']} {sub_range} בוטלה. נמשיך בלימוד!")
                del USER_STATES[phone]
                return

    if message == '1':
        subs = get_user_subscriptions(user['id'])
        if not subs:
            send_sms(phone, "אין לך מנויים פעילים.")
        else:
            for s in subs:
                if has_sent_today(user['id'], s['id']):
                    send_sms(phone, get_template("already_sent_today"))
                else:
                    from scheduler import send_next_question_or_finish
                    send_next_question_or_finish(s)
    elif message == '2':
        subs = get_user_subscriptions(user['id'])
        if len(subs) > 1:
            USER_STATES[phone] = {"state": "AWAITING_UPDATE_DAF"}
            send_sms(phone, get_template("choose_subscription_update_daf", menu=get_subs_menu(subs)))
        else:
            USER_STATES[phone] = {"state": "AWAITING_UPDATE_DAF"}
            send_sms(phone, get_template("ask_update_daf"))
    elif message == '3':
        subs = get_user_subscriptions(user['id'])
        if len(subs) > 1:
            USER_STATES[phone] = {"state": "AWAITING_PAUSE_DAYS"}
            send_sms(phone, get_template("choose_subscription_pause", menu=get_subs_menu(subs)))
        else:
            USER_STATES[phone] = {"state": "AWAITING_PAUSE_DAYS"}
            send_sms(phone, get_template("ask_pause_days"))
    elif message == '4':
        subs = get_user_subscriptions(user['id'])
        if len(subs) > 1:
            USER_STATES[phone] = {"state": "AWAITING_RESUME"}
            send_sms(phone, get_template("choose_subscription_resume", menu=get_subs_menu(subs)))
        else:
            conn = get_conn()
            conn.execute("UPDATE subscriptions SET pause_until=NULL WHERE user_id=? AND is_active=1", (user["id"],))
            conn.commit()
            conn.close()
            send_sms(phone, get_template("resume_success"))
    elif message == '5':
        subs = get_user_subscriptions(user['id'])
        if len(subs) > 1:
            USER_STATES[phone] = {"state": "AWAITING_NEW_HOUR"}
            send_sms(phone, get_template("choose_subscription_hour", menu=get_subs_menu(subs)))
        else:
            USER_STATES[phone] = {"state": "AWAITING_NEW_HOUR"}
            send_sms(phone, get_template("ask_new_hour"))
    elif message == '6':
        USER_STATES[phone] = {"state": "AWAITING_REG_STEP_2"}
        send_sms(phone, get_template("registration_step_2_instructions", name=user["name"]))
    elif message == '7':
        subs = get_user_subscriptions(user['id'])
        if len(subs) > 1:
            USER_STATES[phone] = {"state": "AWAITING_UNSUBSCRIBE"}
            send_sms(phone, get_template("choose_subscription_unsubscribe", menu=get_subs_menu(subs)))
        else:
            conn = get_conn()
            conn.execute("UPDATE subscriptions SET is_active=0 WHERE user_id=?", (user["id"],))
            conn.commit()
            conn.close()
            send_sms(phone, get_template("unsubscribe_success"))
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
            receive_sms(phone, message)
            conn = get_conn()
            user = conn.execute("SELECT * FROM users WHERE phone=?", (phone,)).fetchone()
            conn.close()
            if not user: handle_unregistered_user(phone, message)
            else: handle_registered_user(phone, user, message)
        except EOFError: break
        except Exception as e: print(f"Error: {e}")

if __name__ == "__main__":
    main()
