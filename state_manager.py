"""
state_manager.py - Centralized state management using database
Replaces the in-memory USER_STATES dictionary with DB-backed storage
"""
import json
from database import get_conn
from datetime import datetime


def get_user_state(phone: str) -> dict:
    """
    Get the current state for a user by phone number.
    Returns a dict with 'state' and any additional data, or None if no state exists.
    """
    conn = get_conn()
    row = conn.execute(
        "SELECT state, data FROM user_states WHERE phone = ?", (phone,)
    ).fetchone()
    conn.close()
    
    if not row:
        return None
    
    result = {"state": row["state"]}
    if row["data"]:
        try:
            additional_data = json.loads(row["data"])
            result.update(additional_data)
        except:
            pass
    
    return result


def set_user_state(phone: str, state: str, **kwargs):
    """
    Set the state for a user. Additional keyword arguments are stored as JSON.
    Example: set_user_state(phone, "AWAITING_ANSWER", sub_id=123, queue=[1,2,3])
    """
    conn = get_conn()
    is_postgres = bool(conn.__class__.__name__ == 'PostgresConnWrapper')
    
    data_json = json.dumps(kwargs) if kwargs else None
    
    if is_postgres:
        conn.execute("""
            INSERT INTO user_states (phone, state, data, updated_at) 
            VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (phone) DO UPDATE 
            SET state = EXCLUDED.state, data = EXCLUDED.data, updated_at = EXCLUDED.updated_at
        """, (phone, state, data_json))
    else:
        conn.execute("""
            INSERT OR REPLACE INTO user_states (phone, state, data, updated_at) 
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        """, (phone, state, data_json))
    
    conn.commit()
    conn.close()


def clear_user_state(phone: str):
    """
    Remove the state for a user (e.g., when they complete a flow or reset).
    """
    conn = get_conn()
    conn.execute("DELETE FROM user_states WHERE phone = ?", (phone,))
    conn.commit()
    conn.close()


def update_user_state_data(phone: str, **kwargs):
    """
    Update only the data portion of a user's state without changing the state itself.
    Useful for modifying queue or other metadata.
    """
    current = get_user_state(phone)
    if not current:
        return
    
    # Merge new data with existing
    current_state = current.pop("state")
    current.update(kwargs)
    
    set_user_state(phone, current_state, **current)
