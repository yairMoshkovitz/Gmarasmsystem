"""
simulation_system.py - סימולציה של המערכת בתור בוט SMS
"""
import os
import sys
from registration import register_user, subscribe, get_all_tractates, get_user_subscriptions
from scheduler import send_daily_questions
from database import get_conn, float_to_daf_str
from sms_service import get_sms_history, send_sms, receive_sms

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def handle_unregistered_user(phone, message):
    # הפורמט יכול להיות:
    # 7 איברים: הרשמה, שם, מסכת, דף התחלה, דף סיום, קצב, שעה
    # 9 איברים: הרשמה, שם, מסכת, דף התחלה, עמוד התחלה, דף סיום, עמוד סיום, קצב, שעה
    parts = [p.strip() for p in message.split(',')]
    
    if len(parts) > 0 and parts[0] == "הרשמה" and (len(parts) == 7 or len(parts) == 9):
        try:
            name = parts[1]
            tractate_name = parts[2]
            
            if len(parts) == 7:
                start_daf = int(parts[3])
                start_amud = 'א'
                end_daf = int(parts[4])
                end_amud = 'ב'
                rate = float(parts[5])
                hour = int(parts[6])
            else:
                start_daf = int(parts[3])
                start_amud = parts[4]
                end_daf = int(parts[5])
                end_amud = parts[6]
                rate = float(parts[7])
                hour = int(parts[8])
                
            # למצוא מזהה מסכת
            tractates = get_all_tractates()
            tractate_id = None
            for t in tractates:
                if t['name'] == tractate_name:
                    tractate_id = t['id']
                    break
                    
            if not tractate_id:
                send_sms(phone, f"המסכת '{tractate_name}' לא נמצאה במערכת.")
                return
                
            user_id = register_user(phone, name)
            sub_id = subscribe(user_id, tractate_id, start_daf, start_amud, end_daf, end_amud, rate, hour)
            # הודעת ההצלחה כבר נשלחת מתוך register_user ו-subscribe
            return
            
        except ValueError:
            send_sms(phone, "שגיאה בפענוח הנתונים. אנא ודא שהכנסת מספרים היכן שנדרש.")
            return

    # אם לא תקין או שההודעה אחרת, נשלח הוראות
    instructions = (
        "שלום! אינך רשום במערכת.\n"
        "כדי להירשם שלח הודעה בפורמט הבא (עם פסיקים):\n"
        "הרשמה, שם, מסכת, דף התחלה, דף סיום, קצב דפים ביום, שעה מועדפת\n"
        "לדוגמה: הרשמה, משה, ברכות, 2, 10, 1, 18\n"
        "*(למתקדמים: ניתן להוסיף עמוד א/ב אחרי כל דף)*"
    )
    send_sms(phone, instructions)

def handle_registered_user(phone, user, message):
    if message == '1':
        subs = get_user_subscriptions(user['id'])
        if not subs:
            send_sms(phone, "אין לך מנויים פעילים לקבלת שאלות.")
        else:
            for s in subs:
                print(f"\nמפעיל שליחה עבור מסכת {s['tractate_name']}...")
                send_daily_questions(s)
    elif message == '2':
        send_sms(phone, "התנתקת בהצלחה (סימולציה של יציאה מהבוט).")
        return "exit"
    elif message == '3':
        instructions = (
            "להרשמה למסכת נוספת, שלח הודעה בפורמט:\n"
            "הרשמה, שם, מסכת, דף התחלה, דף סיום, קצב, שעה\n"
            "לדוגמה: הרשמה, משה, שבת, 2, 10, 1, 18"
        )
        send_sms(phone, instructions)
    elif message.startswith("הרשמה"):
        # ננסה לרשום אותו לעוד מסכת (כמו אצל משתמש חדש)
        # מכיוון ש-handle_unregistered_user מטפל גם בחיפוש שם, אפשר לקרוא לו או לממש מחדש,
        # אבל register_user כבר תומך במשתמש קיים (הוא פשוט מחזיר את ה-ID הקיים ולא מוסיף חדש).
        handle_unregistered_user(phone, message)
    else:
        # הודעה כללית (תפריט)
        menu = (
            f"שלום {user['name']}, בחר אפשרות:\n"
            "1. קבלת שאלה יומית עכשיו\n"
            "2. יציאה מהמערכת (החלפת מספר)\n"
            "3. הרשמה למסכת נוספת\n"
            "(או שלח הודעת הרשמה מלאה)"
        )
        send_sms(phone, menu)
    return None

def main():
    clear_screen()
    print("=== מערכת סימולציה Gemara SMS ===")
    
    phone = input("הכנס מספר טלפון זמני לסשן (למשל 0501234567): ").strip()
    if not phone:
        print("לא הוזן מספר. יציאה.")
        return

    while True:
        try:
            print(f"\n--- סשן פעיל: {phone} ---")
            message = input("הכנס הודעת SMS נכנסת (או q ליציאה): ").strip()
            if message.lower() == 'q':
                break
            if not message:
                continue
                
            # Log the incoming message
            receive_sms(phone, message)
            
            # Check if user exists
            conn = get_conn()
            user = conn.execute("SELECT * FROM users WHERE phone=?", (phone,)).fetchone()
            conn.close()
            
            if not user:
                handle_unregistered_user(phone, message)
            else:
                res = handle_registered_user(phone, user, message)
                if res == "exit":
                    phone = input("\nהכנס מספר טלפון זמני חדש (או q ליציאה): ").strip()
                    if phone.lower() == 'q' or not phone:
                        break

        except EOFError:
            break

if __name__ == "__main__":
    main()
