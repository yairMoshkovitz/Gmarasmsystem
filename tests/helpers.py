from simulation_system import handle_unregistered_user, handle_registered_user
from database import get_conn
from sms_service import get_sms_history

def simulate_inbound(phone, message):
    """Simulates a user sending an SMS and handles it through the system logic."""
    conn = get_conn()
    user = conn.execute("SELECT * FROM users WHERE phone=?", (phone,)).fetchone()
    conn.close()
    
    if not user:
        handle_unregistered_user(phone, message)
    else:
        handle_registered_user(phone, user, message)

def get_last_sms(phone):
    """Gets the last outgoing SMS for a specific phone number."""
    from database import get_conn
    conn = get_conn()
    row = conn.execute("SELECT message FROM sms_log WHERE phone=? AND direction='out' ORDER BY id DESC LIMIT 1", (phone,)).fetchone()
    conn.close()
    if row:
        return row['message']
    return None

def get_all_outgoing_sms(phone):
    """Gets all outgoing SMS messages for a phone number, ordered by ID ASC."""
    from database import get_conn
    conn = get_conn()
    rows = conn.execute("SELECT message FROM sms_log WHERE phone=? AND direction='out' ORDER BY id ASC", (phone,)).fetchall()
    conn.close()
    return [r['message'] for r in rows]

def create_user_with_subscription(phone, name, tractate_name="ברכות"):
    """Helper to quickly set up a user with a subscription for testing."""
    from registration import register_user, subscribe
    conn = get_conn()
    user_id = register_user(phone, name, "לוי", "צפת", 28)
    t = conn.execute("SELECT id FROM tractates WHERE name=?", (tractate_name,)).fetchone()
    sub_id = subscribe(user_id, t['id'], 2.0, 10.0, 1.0, 18)
    conn.close()
    return user_id, sub_id
