import os
import base64
from app import app

def test_inforu_json_complex():
    os.environ['SITE_PASSWORD'] = 'admin123'
    client = app.test_client()

    # The exact format seen in the logs
    json_data = {
        "CustomerId": 34240,
        "ProjectId": 1066218,
        "Data": [
            {
                "Channel": "SMS_MO",
                "Type": "PhoneNumber",
                "Value": "0584555723",
                "Keyword": "בדיקה",
                "Message": "בדיקה",
                "Network": "053",
                "ShortCode": "0537038610"
            }
        ]
    }

    print("--- Testing Inforu Complex JSON Format ---")
    res = client.post('/WEBHOOK/INFORU', json=json_data)
    
    print(f"Status: {res.status_code}")
    assert res.status_code == 200
    
    print("\nComplex JSON Test passed!")

if __name__ == '__main__':
    test_inforu_json_complex()
