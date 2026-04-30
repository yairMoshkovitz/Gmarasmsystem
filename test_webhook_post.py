import os
import base64
from app import app

def test_webhook_post():
    os.environ['SITE_PASSWORD'] = 'admin123'
    client = app.test_client()

    print("--- Testing POST Webhook (Form Data) ---")
    # Simulate Inforu sending form data
    res = client.post('/WEBHOOK/INFORU', data={
        'Phone': '0501234567',
        'Text': 'בדיקה'
    })
    print(f"Status: {res.status_code}")
    print(f"Response: {res.data.decode()}")
    assert res.status_code == 200

    print("\n--- Testing POST Webhook (JSON) ---")
    # Simulate another potential format
    res = client.post('/webhook/inforu', json={
        'Phone': '0501234567',
        'Text': 'בדיקה'
    })
    print(f"Status: {res.status_code}")
    print(f"Response: {res.data.decode()}")
    assert res.status_code == 200

    print("\n--- Testing Webhook with missing data (Should be 400) ---")
    res = client.post('/WEBHOOK/INFORU', data={'Something': 'Else'})
    print(f"Status: {res.status_code}")
    assert res.status_code == 400

    print("\nAll local tests passed!")

if __name__ == '__main__':
    test_webhook_post()
