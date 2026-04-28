from simulation_system import handle_unregistered_user, handle_registered_user
from database import get_conn
import os

def test_full_flow():
    phone = "0541234567"
    # Registration message
    reg_message = 'הרשמה, משה, כהן, בני ברק, 25, שבת, כב ע"א עד ל ע"א, 1.5, 18'
    
    print(f"Testing registration: {reg_message}")
    
    # Clean up
    conn = get_conn()
    conn.execute("DELETE FROM sent_questions WHERE user_id IN (SELECT id FROM users WHERE phone=?)", (phone,))
    conn.execute("DELETE FROM subscriptions WHERE user_id IN (SELECT id FROM users WHERE phone=?)", (phone,))
    conn.execute("DELETE FROM users WHERE phone=?", (phone,))
    conn.commit()
    conn.close()
    
    # 1. Register
    handle_unregistered_user(phone, reg_message)
    
    # Verify registration
    conn = get_conn()
    user = conn.execute("SELECT * FROM users WHERE phone=?", (phone,)).fetchone()
    if not user:
        print("User NOT registered!")
        return
    
    print(f"User registered: {user['id']}")
    sub = conn.execute("SELECT * FROM subscriptions WHERE user_id=?", (user['id'],)).fetchone()
    if not sub:
        print("Subscription NOT created!")
        tractates = conn.execute("SELECT name FROM tractates").fetchall()
        print(f"Available tractates: {[t['name'] for t in tractates]}")
        return
    
    print(f"Subscription created: {sub['id']}")
    
    # 2. Simulate sending questions (using menu option 1)
    print("\nTesting option 1 (Send Questions):")
    # Set live mode to true for simulation within scheduler
    from sms_service import set_live_mode
    set_live_mode(True)
    
    handle_registered_user(phone, user, '1')
    
    # Verify question sent
    sent = conn.execute("SELECT * FROM sent_questions WHERE user_id=? ORDER BY sent_at DESC LIMIT 1", (user['id'],)).fetchone()
    if sent:
        print(f"Question sent and logged: {sent['id']}")
    else:
        print("No question found in sent_questions!")
        conn.close()
        return

    # 3. Simulate response
    print("\nTesting response 'כן':")
    handle_registered_user(phone, user, 'כן')
    
    # Verify response updated
    updated = conn.execute("SELECT * FROM sent_questions WHERE id=?", (sent['id'],)).fetchone()
    if updated and updated['response_text'] == 'כן':
        print(f"Response updated: {updated['response_text']}")
    else:
        print(f"Response NOT updated!")
    
    conn.close()

if __name__ == "__main__":
    test_full_flow()
