"""
simulation_system.py - SMS bot simulation with numeric menu and states
"""
import os
import sys
from datetime import datetime, timedelta
from registration import register_user, subscribe, get_all_tractates, get_user_subscriptions, get_template
from scheduler import send_daily_questions, has_sent_today
from database import get_conn, float_to_daf_str, daf_to_float
from sms_service import get_sms_history, send_sms, receive_sms

# Global state to track multi-step conversations
USER_STATES = {}

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def handle_unregistered_user(phone, message):
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

def handle_registered_user(phone, user, message):
    state_info = USER_STATES.get(phone)
    
    if state_info:
        if state_info["state"] == "AWAITING_REG_STEP_2":
            parts = [p.strip() for p in message.split(',')]
            if len(parts) == 4:
                try:
                    tractate_name = parts[0]
                    range_part = parts[1]
                    if " עד " in range_part:
                        start_str, end_str = range_part.split(" עד ")
                        start_f, end_f = daf_to_float(start_str), daf_to_float(end_str)
                    else:
                        start_f = daf_to_float(range_part)
                        end_f = start_f + 10.0
                    rate, hour = float(parts[2]), int(parts[3])
                    
                    tractates = get_all_tractates()
                    tractate_id = next((t['id'] for t in tractates if t['name'].strip() == tractate_name.strip()), None)
                    if not tractate_id:
                        send_sms(phone, get_template("tractate_not_found", tractate=tractate_name))
                        return
                    
                    subscribe(user["id"], tractate_id, start_f, end_f, rate, hour)
                    if phone in USER_STATES:
                        del USER_STATES[phone]
                    return
                except Exception as e:
                    print(f"DEBUG Step 2 Error: {e}")
                    send_sms(phone, "שגיאה בפרטי המסכת. אנא שלח בפורמט: מסכת, דף התחלה עד דף סיום, קצב, שעה")
                    return
            else:
                send_sms(phone, get_template("registration_step_2_instructions", name=user["name"]))
                return

        if state_info["state"] == "AWAITING_UPDATE_DAF":
            try:
                new_daf_f = daf_to_float(message)
                conn = get_conn()
                conn.execute("UPDATE subscriptions SET current_daf=? WHERE user_id=? AND is_active=1", (new_daf_f, user["id"]))
                conn.commit()
                conn.close()
                send_sms(phone, get_template("update_daf_success", daf=float_to_daf_str(new_daf_f)))
                del USER_STATES[phone]
            except:
                send_sms(phone, "פורמט דף לא תקין. נסה שוב (למשל: כ ע\"ב) או שלח 'ביטול'.")
            return
        if state_info["state"] == "AWAITING_PAUSE_DAYS":
            if message.isdigit():
                days = int(message)
                until_date = (datetime.now() + timedelta(days=days)).date()
                conn = get_conn()
                conn.execute("UPDATE subscriptions SET pause_until=? WHERE user_id=? AND is_active=1", (until_date.isoformat(), user["id"]))
                conn.commit()
                conn.close()
                send_sms(phone, get_template("pause_success", days=days, date=until_date.strftime("%d/%m/%Y")))
                del USER_STATES[phone]
            else:
                send_sms(phone, "אנא שלח מספר ימים (ספרות בלבד).")
            return
        if state_info["state"] == "AWAITING_NEW_HOUR":
            if message.isdigit() and 0 <= int(message) <= 23:
                hour = int(message)
                conn = get_conn()
                conn.execute("UPDATE subscriptions SET send_hour=? WHERE user_id=? AND is_active=1", (hour, user["id"]))
                conn.commit()
                conn.close()
                send_sms(phone, get_template("update_hour_success", hour=hour))
                del USER_STATES[phone]
            else:
                send_sms(phone, "אנא שלח שעה תקינה (מספר בין 0 ל-23).")
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
        USER_STATES[phone] = {"state": "AWAITING_UPDATE_DAF"}
        send_sms(phone, get_template("ask_update_daf"))
    elif message == '3':
        USER_STATES[phone] = {"state": "AWAITING_PAUSE_DAYS"}
        send_sms(phone, get_template("ask_pause_days"))
    elif message == '4':
        conn = get_conn()
        conn.execute("UPDATE subscriptions SET pause_until=NULL WHERE user_id=? AND is_active=1", (user["id"],))
        conn.commit()
        conn.close()
        send_sms(phone, get_template("resume_success"))
    elif message == '5':
        USER_STATES[phone] = {"state": "AWAITING_NEW_HOUR"}
        send_sms(phone, get_template("ask_new_hour"))
    elif message == '6':
        USER_STATES[phone] = {"state": "AWAITING_REG_STEP_2"}
        send_sms(phone, get_template("registration_step_2_instructions", name=user["name"]))
    elif message.lower() in ["כן", "לא", "ידעתי", "לא ידעתי"]:
        conn = get_conn()
        # Find the OLDEST unanswered question for this user to keep order
        last_q = conn.execute(
            "SELECT id, subscription_id FROM sent_questions WHERE user_id=? AND responded_at IS NULL ORDER BY sent_at ASC LIMIT 1", 
            (user["id"],)
        ).fetchone()
        
        if last_q:
            conn.execute("UPDATE sent_questions SET responded_at=?, response_text=? WHERE id=?", (datetime.now().isoformat(), message, last_q["id"]))
            conn.commit()
            
            # Find the specific subscription for this question
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
                # Check for next question for THIS specific subscription
                from scheduler import send_next_question_or_finish
                send_next_question_or_finish(dict(sub_row))
        else:
            conn.close()
            send_sms(phone, "לא מצאתי שאלה פתוחה לשייך אליה את התשובה. וודא שקיבלת שאלה היום.")
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
