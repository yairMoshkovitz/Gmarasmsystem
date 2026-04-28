"""
scheduler.py - Daily job: send questions and check inactive users.
Run this every hour via cron: 0 * * * * python scheduler.py
Or call run_hour(hour) to simulate.
"""
from database import get_conn, float_to_daf_str
from questions_engine import (
    select_questions_for_range,
    get_already_sent_ids,
    format_question_sms,
)
from sms_service import send_sms
from datetime import datetime, timedelta


INACTIVE_DAYS = 7  # days without response before deactivating


def get_due_subscriptions(current_hour: int) -> list:
    """Return active subscriptions scheduled for this hour."""
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT s.*, u.phone, u.name, u.last_response_at, u.inactive_notified,
               t.name as tractate_name
        FROM subscriptions s
        JOIN users u ON s.user_id = u.id
        JOIN tractates t ON s.tractate_id = t.id
        WHERE s.is_active = 1
          AND u.is_active = 1
          AND s.send_hour = ?
          AND s.current_daf <= s.end_daf
        """,
        (current_hour,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def check_inactive_users():
    """
    Deactivate users who haven't responded in INACTIVE_DAYS days.
    Sends a warning SMS first.
    """
    conn = get_conn()
    cutoff = (datetime.now() - timedelta(days=INACTIVE_DAYS)).isoformat()

    # Find users inactive too long
    rows = conn.execute(
        """
        SELECT u.id, u.phone, u.name, u.last_response_at, u.inactive_notified
        FROM users u
        WHERE u.is_active = 1
          AND (u.last_response_at IS NULL OR u.last_response_at < ?)
        """,
        (cutoff,),
    ).fetchall()

    messages_to_send = []

    for user in rows:
        if not user["inactive_notified"]:
            # Send warning
            msg = (
                f"שלום {user['name']}!\n"
                "שבוע שלם לא קיבלנו תשובה ממך 😢\n"
                "כדי להמשיך לקבל שאלות, ענה על הודעה זו בכל מילה.\n"
                "אם לא נשמע ממך, נפסיק לשלוח שאלות."
            )
            messages_to_send.append((user["phone"], msg, user["id"]))
            conn.execute(
                "UPDATE users SET inactive_notified=1 WHERE id=?", (user["id"],)
            )
            print(f"⚠️  Warned inactive user: {user['name']} ({user['phone']})")
        else:
            # Already warned — deactivate
            conn.execute(
                "UPDATE users SET is_active=0 WHERE id=?", (user["id"],)
            )
            conn.execute(
                "UPDATE subscriptions SET is_active=0 WHERE user_id=?", (user["id"],)
            )
            msg = (
                f"שלום {user['name']}.\n"
                "לצערנו, הפסקנו לשלוח לך שאלות כי לא ענית שבוע.\n"
                "כדי להירשם מחדש, פנה אלינו. נשמח לקבלך! 📖"
            )
            messages_to_send.append((user["phone"], msg, user["id"]))
            print(f"🚫 Deactivated inactive user: {user['name']} ({user['phone']})")

    conn.commit()
    conn.close()

    for phone, msg, uid in messages_to_send:
        send_sms(phone, msg, uid)


def advance_subscription(sub_id: int, dafim_per_day: float):
    """Advance current_daf position after sending questions."""
    conn = get_conn()
    conn.execute(
        "UPDATE subscriptions SET current_daf = MIN(current_daf + ?, end_daf) WHERE id=?",
        (dafim_per_day, sub_id),
    )
    conn.commit()
    conn.close()


def send_daily_questions(sub: dict):
    """
    Pick and send questions for a subscription.
    Combined into a single SMS to save costs with clear instructions.
    Records sent questions in DB.
    """
    user_id = sub["user_id"]
    sub_id = sub["id"]
    tractate_id = sub["tractate_id"]
    current_daf = sub["current_daf"]
    dafim_per_day = sub["dafim_per_day"]
    tractate_name = sub["tractate_name"]

    already_sent = get_already_sent_ids(user_id, sub_id)

    questions = select_questions_for_range(
        tractate_id=tractate_id,
        current_daf=current_daf,
        dafim_per_day=dafim_per_day,
        count=2,
        already_sent=already_sent,
    )

    if not questions:
        print(f"  ℹ️  No questions available for sub {sub_id} at daf {current_daf}")
        return

    # Header
    combined_msg = f"📚 {tractate_name} - {float_to_daf_str(current_daf)}"
    
    conn = get_conn()

    for i, q in enumerate(questions, 1):
        daf_info = q.get("daf", {})
        daf_from = str(daf_info.get("from") or daf_info.get("daf", ""))
        daf_to = str(daf_info.get("to") or daf_info.get("daf", ""))

        msg_part = format_question_sms(q, i, tractate_name)
        combined_msg += f"\n\n{msg_part}"

        conn.execute(
            """
            INSERT INTO sent_questions
              (user_id, subscription_id, question_id, question_text, daf_from, daf_to)
            VALUES (?,?,?,?,?,?)
            """,
            (user_id, sub_id, q["id"], q["text"], daf_from, daf_to),
        )

    conn.commit()
    conn.close()

    # Adding explicit response instructions as requested
    instructions = (
        "\n\n------------------------\n"
        "📝 הוראות מענה:\n"
        "נא לענות על כל השאלות בהודעה אחת.\n"
        "הפרד בין התשובות בעזרת פסיק או רווח.\n"
        "למשל: תשובה1, תשובה2"
    )
    combined_msg += instructions

    # Send the single combined message
    send_sms(sub["phone"], combined_msg, user_id)

    # Advance position
    advance_subscription(sub_id, dafim_per_day)
    print(
        f"  ✉️  Sent combined questions with instructions to {sub['name']} "
        f"({sub['phone']}) | {tractate_name} daf {float_to_daf_str(current_daf)}"
    )


def run_hour(hour: int = None):
    """
    Main scheduler job. Run once per hour.
    If hour is None, uses current hour.
    """
    if hour is None:
        hour = datetime.now().hour

    print(f"\n🕐 Scheduler running for hour {hour:02d}:00 — {datetime.now():%Y-%m-%d %H:%M}")

    # 1. Check and handle inactive users
    check_inactive_users()

    # 2. Send questions for due subscriptions
    due = get_due_subscriptions(hour)
    print(f"📬 {len(due)} subscription(s) due at hour {hour:02d}:00")

    for sub in due:
        print(f"  → Processing: {sub['name']} | {sub['tractate_name']}")
        send_daily_questions(sub)

    print(f"✅ Scheduler done.\n")


if __name__ == "__main__":
    import sys
    hour = int(sys.argv[1]) if len(sys.argv) > 1 else None
    run_hour(hour)
