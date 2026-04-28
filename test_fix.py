from simulation_system import handle_unregistered_user, handle_registered_user
from database import get_conn
import os
import json

def test_full_flow():
    phone = "0541234567"
    
    # Check what tractates we have
    conn = get_conn()
    tractates = conn.execute("SELECT id, name FROM tractates").fetchall()
    
    t_names = [t['name'] for t in tractates]
    print(f"Available tractates: {t_names}")
    
    if not t_names:
        print("No tractates found!")
        conn.close()
        return
        
    # Let's find "שבת" or just use the first one
    t_name = t_names[0]
    for name in t_names:
        if "שבת" in name:
            t_name = name
            break
            
    # Registration message with the EXACT name from DB
    reg_message = f'הרשמה, משה, כהן, בני ברק, 25, {t_name}, כב ע"א עד ל ע"א, 1.5, 18'
    
    print(f"Testing registration: {reg_message}")
    
    # Clean up
    conn.execute("DELETE FROM sent_questions WHERE user_id IN (SELECT id FROM users WHERE phone=?)", (phone,))
    conn.execute("DELETE FROM subscriptions WHERE user_id IN (SELECT id FROM users WHERE phone=?)", (phone,))
    conn.execute("DELETE FROM users WHERE phone=?", (phone,))
    conn.commit()
    
    # 1. Register
    handle_unregistered_user(phone, reg_message)
    
    # Verify registration
    user = conn.execute("SELECT * FROM users WHERE phone=?", (phone,)).fetchone()
    if not user:
        print("User NOT registered!")
        conn.close()
        return
    
    print(f"User registered: {user['id']}")
    sub = conn.execute("SELECT * FROM subscriptions WHERE user_id=?", (user['id'],)).fetchone()
    if not sub:
        print("Subscription NOT created!")
        # Debug why subscribe() failed - let's check tractate id match
        parts = [p.strip() for p in reg_message.split(',')]
        tractate_name = parts[5]
        tractate_id = next((t['id'] for t in tractates if t['name'].strip() == tractate_name.strip()), None)
        print(f"DEBUG: Input tractate name: '{tractate_name}', Matched ID: {tractate_id}")
        conn.close()
        return
    
    print(f"Subscription created: {sub['id']}")
    
    # 2. Simulate sending questions (using menu option 1)
    print("\nTesting option 1 (Send Questions):")
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
