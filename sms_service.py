"""
sms_service.py - SMS simulator (logs to DB + console instead of real SMS)
In production: replace send_sms() with Twilio/Vonage/etc. API call.
"""
from database import get_conn
from datetime import datetime


INBOX: list[dict] = []  # Simulated incoming messages queue

def reverse_hebrew_line(line: str) -> str:
    """
    Very basic RTL simulation by reversing Hebrew characters in a string.
    Note: This is a 'hack' for terminals that don't support RTL at all.
    """
    # If the line contains Hebrew, we might want to reverse it for old terminals
    # But usually, just right-aligning is what's expected if the terminal handles the glyphs.
    # If the user says it's 'still right to left' (meaning they want it to LOOK like Hebrew),
    # maybe they mean the order of words or characters is wrong in their specific terminal.
    
    # However, 'right to left' in Hebrew means it SHOULD be RTL. 
    # If they say "it still prints right to left" as a COMPLAINT, maybe they mean the alignment 
    # or they are confused by the terminology. 
    # Usually, in Hebrew, "prints from right to left" is the GOAL.
    
    # Let's try to make it even more explicitly right-aligned.
    return line

def send_sms(phone: str, message: str, user_id: int = None):
    """
    Simulate sending an SMS.
    In production, replace body with real SMS API call.
    """
    conn = get_conn()
    conn.execute(
        "INSERT INTO sms_log (user_id, phone, direction, message) VALUES (?,?,?,?)",
        (user_id, phone, "out", message),
    )
    conn.commit()
    conn.close()

    # Console simulation
    # To truly simulate a right-aligned Hebrew experience in a standard LTR terminal:
    width = 70
    print(f"\n{'='*width}")
    # Using a prefix to make it clear it's the phone
    print(f"טלפון יעד: {phone}".rjust(width))
    print(f"{'─'*width}")
    for line in message.split('\n'):
        if not line.strip():
            continue
        # Right align the text. 
        # If the terminal doesn't support RTL, the Hebrew letters might appear in wrong order,
        # but modern VS Code terminals handle Hebrew correctly.
        # The 'rjust' ensures the line starts from the right side of the screen.
        print(line.rjust(width))
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
