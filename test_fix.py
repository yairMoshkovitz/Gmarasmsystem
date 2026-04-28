from simulation_system import handle_unregistered_user
from database import get_conn
import os

def test_full_flow():
    phone = "0541234567"
    message = 'הרשמה, משה, כהן, בני ברק, 25, ברכות, כב ע"א עד ל ע"א, 1.5, 18'
    
    print(f"Testing message: {message}")
    
    # Check if user exists first
    conn = get_conn()
    conn.execute("DELETE FROM subscriptions WHERE user_id IN (SELECT id FROM users WHERE phone=?)", (phone,))
    conn.execute("DELETE FROM users WHERE phone=?", (phone,))
    conn.commit()
    conn.close()
    
    # Force re-seed to apply strip() fix
    from database import seed_tractates
    seed_tractates()

    handle_unregistered_user(phone, message)
    
    # Verify results
    conn = get_conn()
    user = conn.execute("SELECT * FROM users WHERE phone=?", (phone,)).fetchone()
    if user:
        print(f"User registered: {dict(user)}")
        sub = conn.execute("SELECT * FROM subscriptions WHERE user_id=?", (user['id'],)).fetchone()
        if sub:
            print(f"Subscription created: {dict(sub)}")
        else:
            print("Subscription NOT created!")
    else:
        print("User NOT registered!")
    conn.close()

if __name__ == "__main__":
    test_full_flow()
