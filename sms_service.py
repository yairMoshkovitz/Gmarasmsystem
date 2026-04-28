"""
sms_service.py - SMS simulator (logs to DB + console instead of real SMS)
In production: replace send_sms() with Twilio/Vonage/etc. API call.
"""
from database import get_conn
from datetime import datetime
import os
import requests
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
    try:
        print(f"\n{'='*width}")
        # Using a prefix to make it clear it's the phone
        print(f"טלפון יעד: {phone}".rjust(width))
        print(f"{'-'*width}")
        for line in message.split('\n'):
            if not line.strip():
                continue
            print(line.rjust(width))
        print(f"{'='*width}")
    except UnicodeEncodeError:
        print(f"\n{'='*width}")
        print(f"Target Phone: {phone}")
        print(f"{'-'*width}")
        print(message)
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
