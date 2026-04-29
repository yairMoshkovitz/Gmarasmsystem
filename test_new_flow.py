
from simulation_system import handle_registered_user
from database import get_conn
from sms_service import send_sms

def test_flow():
    phone = "0501234561"
    conn = get_conn()
    user = conn.execute("SELECT * FROM users WHERE phone=?", (phone,)).fetchone()
    conn.close()
    
    print(f"--- Testing Flow for {user['name']} ({phone}) ---")
    
    # 1. Trigger daily questions (simulating menu option '1')
    print("\nStep 1: Requesting daily questions (sending '1')...")
    handle_registered_user(phone, user, "1")
    
    # 2. Answer the question (sending 'כן')
    print("\nStep 2: Answering 'כן' for the first question...")
    handle_registered_user(phone, user, "כן")
    
    print("\nStep 3: Answering 'כן' for the second question (from the other tractate)...")
    handle_registered_user(phone, user, "כן")
    
    print("\nStep 4: Answering 'כן' several times to finish all questions...")
    for i in range(10):
        print(f"--- Answer {i+1} ---")
        handle_registered_user(phone, user, "כן")

if __name__ == "__main__":
    test_flow()
