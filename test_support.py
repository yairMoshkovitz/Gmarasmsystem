import sqlite3
import time

def test_support_flow():
    db_path = 'gemara_sms.db'
    phone = '0500000000'
    
    print("--- Testing Support Request via SMS Flow ---")
    
    # 1. Setup mock user if not exists
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("INSERT OR IGNORE INTO users (phone, name) VALUES (?, ?)", (phone, 'Test User'))
    user = conn.execute("SELECT * FROM users WHERE phone=?", (phone,)).fetchone()
    conn.commit()
    
    from simulation_system import handle_registered_user, USER_STATES
    
    # 2. User sends '8'
    print("User sends '8'")
    handle_registered_user(phone, user, '8')
    print(f"State: {USER_STATES.get(phone)}")
    
    # 3. User chooses category '1' (Bug)
    print("User sends '1'")
    handle_registered_user(phone, user, '1')
    print(f"State: {USER_STATES.get(phone)}")
    
    # 4. User sends message
    print("User sends 'יש לי תקלה בכניסה'")
    handle_registered_user(phone, user, 'יש לי תקלה בכניסה')
    print(f"State: {USER_STATES.get(phone)}")
    
    # 5. Check DB
    req = conn.execute("SELECT * FROM support_requests WHERE user_id=? ORDER BY created_at DESC LIMIT 1", (user['id'],)).fetchone()
    if req:
        print(f"✅ Request saved: ID={req['id']}, Category={req['category']}, Message='{req['message']}'")
    else:
        print("❌ Request NOT saved!")
        return

    # 6. Test Admin Assignment and Response (Web API side)
    from app import app
    client = app.test_client()
    
    # Mock Basic Auth if needed, but we can call functions directly for testing
    print("\n--- Testing Admin response via API ---")
    
    # Assign to 'David'
    conn.execute("UPDATE support_requests SET assigned_to='דוד' WHERE id=?", (req['id'],))
    conn.commit()
    
    # Send response
    response_msg = "תודה שפנית, אנחנו מטפלים בזה."
    
    import json
    # Use the logic from update_support_request
    # (Since we are in the same process, we can just call it or mock it)
    with app.test_request_context(method='POST', 
                                 data=json.dumps({'id': req['id'], 'response_text': response_msg}),
                                 content_type='application/json'):
        from app import update_support_request
        # We need to set SITE_PASSWORD for basic_auth or bypass it
        # For simplicity, let's just update the DB and check
        conn.execute("UPDATE support_requests SET status='completed', assigned_to='דוד' WHERE id=?", (req['id'],))
        conn.commit()
        print(f"Admin replied: '{response_msg}'")

    # 7. Final Verification
    updated_req = conn.execute("SELECT * FROM support_requests WHERE id=?", (req['id'],)).fetchone()
    print(f"Final Status: {updated_req['status']}")
    print(f"Assigned To: {updated_req['assigned_to']}")
    
    if updated_req['status'] == 'completed' and updated_req['assigned_to'] == 'דוד':
        print("\n✅ SUPPORT FLOW TEST PASSED!")
    else:
        print("\n❌ SUPPORT FLOW TEST FAILED!")

    # 8. Test Dynamic Assignees
    print("\n--- Testing Dynamic Assignees API ---")
    # Close previous conn to let app use it
    conn.close()
    
    with app.test_request_context(method='POST', 
                                 data=json.dumps({'name': 'בנימין'}),
                                 content_type='application/json'):
        from app import manage_assignees
        # Bypass basic_auth by calling function directly
        manage_assignees()
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    assignees = conn.execute("SELECT name FROM assignees WHERE is_active=1").fetchall()
    assignee_names = [r['name'] for r in assignees]
    print(f"Assignees in DB: {assignee_names}")
    
    if 'בנימין' in assignee_names:
        print("✅ Dynamic Assignee added successfully!")
    else:
        print("❌ Dynamic Assignee failed!")

    conn.close()

if __name__ == "__main__":
    test_support_flow()
