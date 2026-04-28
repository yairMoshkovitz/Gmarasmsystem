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
    parts = [p.strip() for p in message.split(',')]
    if len(parts) >= 9 and parts[0] == "הרשמה":
        try:
            name, last_name, city = parts[1], parts[2], parts[3]
            age = int(parts[4])
            tractate_name = parts[5]
            range_part = parts[6]
            if " עד " in range_part:
                start_str, end_str = range_part.split(" עד ")
                start_f, end_f = daf_to_float(start_str), daf_to_float(end_str)
            else:
                start_f = daf_to_float(range_part)
                end_f = start_f + 10.0
            rate, hour = float(parts[7]), int(parts[8])
            tractates = get_all_tractates()
            print(f"DEBUG: Searching for '{tractate_name}' in {[t['name'] for t in tractates]}")
            tractate_id = next((t['id'] for t in tractates if t['name'].strip() == tractate_name.strip()), None)
            if not tractate_id:
                print(f"DEBUG: Tractate '{tractate_name}' not found!")
                send_sms(phone, get_template("tractate_not_found", tractate=tractate_name))
                return
            user_id = register_user(phone, name, last_name, city, age)
            subscribe(user_id, tractate_id, start_f, end_f, rate, hour)
            return
        except Exception as e:
            import traceback
            print(f"DEBUG Error parsing: {e}")
            traceback.print_exc()
            send_sms(phone, get_template("error_parsing_registration"))
            return

    send_sms(phone, get_template("unregistered_instructions"))

def handle_registered_user(phone, user, message):
    state_info = USER_STATES.get(phone)
    if state_info:
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
                    send_daily_questions(s)
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
        send_sms(phone, get_template("unregistered_instructions"))
    elif message.lower() in ["כן", "לא", "ידעתי", "לא ידעתי"]:
        conn = get_conn()
        last_q = conn.execute("SELECT id FROM sent_questions WHERE user_id=? ORDER BY sent_at DESC LIMIT 1", (user["id"],)).fetchone()
        if last_q:
            conn.execute("UPDATE sent_questions SET responded_at=?, response_text=? WHERE id=?", (datetime.now().isoformat(), message, last_q["id"]))
            conn.commit()
            send_sms(phone, "קיבלתי, תודה!")
        else:
            send_sms(phone, "לא מצאתי שאלה פתוחה לשייך אליה את התשובה. וודא שקיבלת שאלה היום.")
        conn.close()
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
