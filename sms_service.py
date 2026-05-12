"""
sms_service.py - SMS simulator (logs to DB + console instead of real SMS)
In production: replace send_sms() with Twilio/Vonage/etc. API call.
"""
from database import get_conn
from datetime import datetime
import os
import requests
import sys
from dotenv import load_dotenv

load_dotenv()

INBOX: list[dict] = []  # Simulated incoming messages queue
LIVE_MODE = False

def set_live_mode(enabled: bool):
    global LIVE_MODE
    LIVE_MODE = enabled
    print(f"SMS Service: Live Mode set to {LIVE_MODE}")

def get_live_mode():
    return LIVE_MODE

def send_real_sms(phone: str, message: str):
    """
    Send a real SMS using Inforu API.
    """
    # Safety check: Prevent sending to test/fake phone numbers
    if phone.startswith("059") or phone.startswith("0580000"):
        print(f"⚠️  BLOCKED: Attempted to send real SMS to test number {phone}")
        print(f"   This appears to be a test/fake number. Real SMS sending prevented.")
        return False
    
    api_token = os.getenv("INFORU_TOKEN")
    api_user = os.getenv("INFORU_USER")
    sender_id = os.getenv("SENDER_ID", "HazarSms")
    
    if not api_token or not api_user:
        print("❌ Error: INFORU_TOKEN or INFORU_USER not set in .env")
        return False

    url = "https://api.inforu.co.il/SendMessageXml.ashx"
    
    xml_payload = f"""<Inforu>
<User>
<Username>{api_user}</Username>
<ApiToken>{api_token}</ApiToken>
</User>
<Content Type="sms">
<Message>{message}</Message>
</Content>
<Recipients>
<PhoneNumber>{phone}</PhoneNumber>
</Recipients>
<Settings>
<SenderName>{sender_id}</SenderName>
</Settings>
</Inforu>"""
    
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded'
    }

    try:
        response = requests.post(url, data={'InforuXML': xml_payload}, headers=headers)
        print(f"Inforu Response Status: {response.status_code}")
        if "Status=\"1\"" in response.text:
            print(f"✅ SMS sent successfully to {phone}")
            return True
        else:
            print(f"❌ SMS sending failed: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Error sending SMS via Inforu: {e}")
        return False

def reverse_hebrew_line(line: str) -> str:
    """
    Very basic RTL simulation by reversing Hebrew characters in a string.
    Note: This is a 'hack' for terminals that don't support RTL at all.
    """
    return line

def send_sms(phone: str, message: str, user_id: int = None):
    """
    Send an SMS (Simulated or Real based on LIVE_MODE).
    """
    conn = get_conn()
    is_postgres = bool(os.environ.get("DATABASE_URL"))
    
    # Check daily limit (30 messages per user per day) - Calendar day
    if is_postgres:
        count_query = "SELECT COUNT(*) FROM sms_log WHERE phone=? AND direction='out' AND sent_at::date = CURRENT_DATE"
    else:
        count_query = "SELECT COUNT(*) FROM sms_log WHERE phone=? AND direction='out' AND date(sent_at) = date('now')"
    
    daily_count = conn.execute(count_query, (phone,)).fetchone()[0]
    
    LIMIT = 30
    if daily_count >= LIMIT:
        # If this is exactly the 30th message, we allow one final warning message to go through
        if daily_count == LIMIT:
            warning_msg = "הגעת למגבלת ההודעות היומית (30). המערכת לא תוכל לשלוח או לקבל הודעות נוספות היום."
            conn.execute(
                "INSERT INTO sms_log (user_id, phone, direction, message) VALUES (?,?,?,?)",
                (user_id, phone, "out", warning_msg),
            )
            conn.commit()
            if LIVE_MODE:
                send_real_sms(phone, warning_msg)
            
            # Print the warning message to console too
            width = 70
            print(f"\n{'='*width}")
            print(f"טלפון יעד: {phone} | הודעה 30/30 להיום (אזהרה)".rjust(width))
            print(f"{'-'*width}")
            for line in warning_msg.split('\n'):
                if line.strip(): print(line.rjust(width))
            print(f"{'='*width}")
                
            print(f"\n[!] Daily limit reached for {phone}. Sent warning.")
        
        conn.close()
        print(f"\n[X] Blocked SMS to {phone}: Daily limit of {LIMIT} exceeded. Message not sent: {message}")
        return False

    conn.execute(
        "INSERT INTO sms_log (user_id, phone, direction, message) VALUES (?,?,?,?)",
        (user_id, phone, "out", message),
    )
    conn.commit()
    conn.close()

    if LIVE_MODE:
        send_real_sms(phone, message)

    # Console simulation
    width = 70
    
    # Calculate new daily count after insertion
    conn = get_conn()
    new_daily_count = conn.execute(count_query, (phone,)).fetchone()[0]
    conn.close()
    
    try:
        print(f"\n{'='*width}")
        # Using a prefix to make it clear it's the phone
        header = f"טלפון יעד: {phone} | הודעה {new_daily_count}/{LIMIT} להיום"
        print(header.rjust(width))
        print(f"{'-'*width}")
        for line in message.split('\n'):
            if not line.strip():
                continue
            print(line.rjust(width))
        print(f"{'='*width}")
    except UnicodeEncodeError:
        print(f"\n{'='*width}")
        print(f"Target Phone: {phone} | Msg {new_daily_count}/{LIMIT} today")
        print(f"{'-'*width}")
        # Try to print safely by replacing unencodable characters
        safe_msg = message.encode(sys.stdout.encoding, errors='replace').decode(sys.stdout.encoding)
        print(safe_msg)
        print(f"{'='*width}")


def receive_sms(phone: str, message: str):
    """
    Simulate receiving an SMS from a user.
    Logs it and puts it in the inbox queue.
    """
    conn = get_conn()

    user = conn.execute(
        "SELECT id FROM users WHERE phone=?", (phone,)
    ).fetchone()

    user_id = user["id"] if user else None

    conn.execute(
        "INSERT INTO sms_log (user_id, phone, direction, message) VALUES (?,?,?,?)",
        (user_id, phone, "in", message),
    )

    if user_id:
        # Update last_response_at
        conn.execute(
            "UPDATE users SET last_response_at=?, inactive_notified=0 WHERE id=?",
            (datetime.now().isoformat(), user_id),
        )

    conn.commit()
    conn.close()

    INBOX.append({"phone": phone, "message": message, "user_id": user_id})
    print(f"\n📨 התקבלה הודעה מ-{phone}: {message}")


def get_sms_history(phone: str = None, limit: int = 20) -> list:
    """Retrieve SMS log."""
    conn = get_conn()
    if phone:
        rows = conn.execute(
            "SELECT * FROM sms_log WHERE phone=? ORDER BY sent_at DESC LIMIT ?",
            (phone, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM sms_log ORDER BY sent_at DESC LIMIT ?", (limit,)
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
