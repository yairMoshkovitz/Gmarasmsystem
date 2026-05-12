import requests
import json

def test_scheduled_api():
    base_url = "http://localhost:5000"
    auth = ("admin", "1234") # Replace with actual password from .env if needed, or run locally without auth if possible
    
    # Since we might not have the password here, let's assume we are testing the logic
    # locally or the user will verify.
    # But I can create a script that helps the user verify.
    
    print("Testing /api/scheduled-messages/subscriptions...")
    # This will likely fail without auth in a real request, but let's see
    try:
        r = requests.get(f"{base_url}/api/scheduled-messages/subscriptions?type=after&hour=20", auth=auth)
        if r.status_code == 200:
            subs = r.json()
            print(f"Success! Found {len(subs)} subscriptions after 20:00")
            for s in subs:
                print(f" - {s['user_name']} ({s['phone']}): {s['send_hour']}:00")
        else:
            print(f"Failed with status {r.status_code}: {r.text}")
    except Exception as e:
        print(f"Error connecting to server: {e}")

if __name__ == "__main__":
    test_scheduled_api()
