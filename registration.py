"""
registration.py - User registration and subscription management
"""
from database import get_conn, daf_to_float
from sms_service import send_sms
from datetime import datetime


def register_user(phone: str, name: str) -> int:
    """Register a new user. Returns user_id."""
    conn = get_conn()

    existing = conn.execute(
        "SELECT id FROM users WHERE phone=?", (phone,)
    ).fetchone()

    if existing:
        conn.close()
        print(f"⚠️  User {phone} already exists.")
        return existing["id"]

    conn.execute(
        "INSERT INTO users (phone, name, last_response_at) VALUES (?,?,?)",
        (phone, name, datetime.now().isoformat()),
    )
    conn.commit()
    user_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()

    welcome = (
        f"שלום {name}! 👋\n"
        "ברוך הבא למערכת שאלות הגמרא ב-SMS.\n"
        "תודה שנרשמת. נשלח לך שאלות יומיות לפי הלימוד שהגדרת.\n"
        "כשתקבל שאלה, ענה עליה בהודעה חוזרת.\n"
        "שיהיה לך לימוד מועיל! 📖"
    )
    send_sms(phone, welcome, user_id)
    print(f"✅ Registered user: {name} ({phone}) → ID {user_id}")
    return user_id


def get_all_tractates() -> list:
    """Return all registered tractates."""
    conn = get_conn()
    rows = conn.execute("SELECT * FROM tractates ORDER BY name").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def subscribe(
    user_id: int,
    tractate_id: int,
    start_daf: int,
    start_amud: str,       # "א" or "ב"
    end_daf: int,
    end_amud: str,
    dafim_per_day: float,  # 0.5, 1, 1.5, 2 ...
    send_hour: int,        # 0-23
) -> int:
    """Subscribe a user to a tractate learning schedule."""
    conn = get_conn()

    # Validate tractate
    tractate = conn.execute(
        "SELECT * FROM tractates WHERE id=?", (tractate_id,)
    ).fetchone()
    if not tractate:
        conn.close()
        raise ValueError(f"Tractate ID {tractate_id} not found.")

    current_daf = daf_to_float(start_daf, start_amud)
    end_daf_f = daf_to_float(end_daf, end_amud)

    # Deactivate existing subscription for same tractate
    conn.execute(
        "UPDATE subscriptions SET is_active=0 WHERE user_id=? AND tractate_id=?",
        (user_id, tractate_id),
    )

    conn.execute(
        """
        INSERT INTO subscriptions
          (user_id, tractate_id, start_daf, end_daf, current_daf, dafim_per_day, send_hour)
        VALUES (?,?,?,?,?,?,?)
        """,
        (user_id, tractate_id, start_daf, end_daf_f, current_daf, dafim_per_day, send_hour),
    )
    conn.commit()
    sub_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()

    # Fetch user info
    conn2 = get_conn()
    user = conn2.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    conn2.close()

    amud_map = {"א": "עמוד א", "ב": "עמוד ב", None: ""}
    day_label = {0.5: "חצי דף", 1.0: "דף אחד", 2.0: "שני דפים"}.get(
        dafim_per_day, f"{dafim_per_day} דפים"
    )

    confirm = (
        f"✅ נרשמת ללימוד מסכת {tractate['name']}!\n"
        f"מדף {start_daf} {amud_map.get(start_amud,'')} עד דף {end_daf} {amud_map.get(end_amud,'')}.\n"
        f"קצב: {day_label} ליום.\n"
        f"שאלות יישלחו בשעה {send_hour:02d}:00.\n"
        f"בהצלחה! 🎓"
    )
    send_sms(user["phone"], confirm, user_id)

    print(
        f"✅ Subscription #{sub_id}: User {user_id} → {tractate['name']} "
        f"daf {current_daf}–{end_daf_f}, {dafim_per_day}/day, hour {send_hour}"
    )
    return sub_id


def unsubscribe(user_id: int, tractate_id: int):
    """Deactivate a subscription."""
    conn = get_conn()
    conn.execute(
        "UPDATE subscriptions SET is_active=0 WHERE user_id=? AND tractate_id=?",
        (user_id, tractate_id),
    )
    conn.commit()
    conn.close()
    print(f"❌ Unsubscribed user {user_id} from tractate {tractate_id}.")


def get_user_subscriptions(user_id: int) -> list:
    """Return active subscriptions for a user."""
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT s.*, t.name as tractate_name, u.phone, u.name
        FROM subscriptions s
        JOIN tractates t ON s.tractate_id = t.id
        JOIN users u ON s.user_id = u.id
        WHERE s.user_id=? AND s.is_active=1
        """,
        (user_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
