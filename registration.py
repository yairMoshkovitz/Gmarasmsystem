"""
registration.py - User registration and subscription management
"""
from database import get_conn, daf_to_float, float_to_daf_str
from sms_service import send_sms
from datetime import datetime
import json
import os

_template_cache = {}

def get_template(template_name_pos=None, **kwargs):
    # Use a unique name for the first argument to avoid collisions with kwargs like 'name'
    template_name = kwargs.pop('template_name', template_name_pos)
    
    global _template_cache
    
    # 1. Check cache first
    template_content = _template_cache.get(template_name)
    
    if not template_content:
        try:
            # 2. Try DB
            conn = get_conn()
            row = conn.execute("SELECT content FROM sms_templates WHERE key = ?", (template_name,)).fetchone()
            conn.close()
            
            if row:
                template_content = row["content"]
                _template_cache[template_name] = template_content
            else:
                # 3. Fallback to JSON
                template_path = os.path.join(os.path.dirname(__file__), "sms_templates.json")
                if os.path.exists(template_path):
                    with open(template_path, "r", encoding="utf-8") as f:
                        templates = json.load(f)
                    template_content = templates.get(template_name, "")
                    if template_content:
                        _template_cache[template_name] = template_content
        except Exception as e:
            print(f"Error loading template {template_name}: {e}")
            
    if not template_content:
        return f"Template {template_name} not found"
        
    try:
        return template_content.format(**kwargs)
    except Exception as e:
        return f"Template {template_name} format error: {e}"

def clear_template_cache():
    global _template_cache
    _template_cache = {}

def register_user(phone: str, name: str, last_name: str = None, city: str = None, age: int = None) -> int:
    """Register a new user. Returns user_id."""
    conn = get_conn()

    existing = conn.execute(
        "SELECT id FROM users WHERE phone=?", (phone,)
    ).fetchone()

    if existing:
        # Update details if provided
        if last_name or city or age:
            conn.execute(
                "UPDATE users SET name=?, last_name=?, city=?, age=? WHERE phone=?",
                (name, last_name, city, age, phone)
            )
            conn.commit()
        conn.close()
        return existing["id"]

    conn.execute(
        "INSERT INTO users (phone, name, last_name, city, age, last_response_at) VALUES (?,?,?,?,?,?)",
        (phone, name, last_name, city, age, datetime.now().isoformat()),
    )
    conn.commit()
    user_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()

    try:
        print(f"Registered user: {name} ({phone}) -> ID {user_id}")
    except UnicodeEncodeError:
        print(f"Registered user ID {user_id}")
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
    start_daf: float,      # Float value (e.g. 2.0, 2.5)
    end_daf: float,        # Float value
    rate: float,           # 0.5, 1, 2 etc
    hour: int,             # 0-23
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
        (user_id, tractate_id, int(start_daf), end_daf, start_daf, rate, hour),
    )
    conn.commit()
    sub_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()

    # Fetch user info
    conn2 = get_conn()
    user = conn2.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    conn2.close()

    confirm = get_template(
        "registration_success",
        tractate=tractate['name'],
        start_daf=float_to_daf_str(start_daf),
        end_daf=float_to_daf_str(end_daf),
        rate=rate,
        hour=hour
    )
    send_sms(user["phone"], confirm, user_id)

    try:
        print(f"Subscription #{sub_id}: User {user_id} -> {tractate['name']} daf {start_daf}-{end_daf}")
    except:
        print(f"Subscription #{sub_id} created")
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
    print(f"Unsubscribed user {user_id} from tractate {tractate_id}.")


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
