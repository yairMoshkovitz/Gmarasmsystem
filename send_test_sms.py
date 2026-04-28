import requests
import sys
import os
from dotenv import load_dotenv

load_dotenv()

def send_inforu_sms(phone, message):
    api_token = os.getenv("INFORU_TOKEN")
    api_user = os.getenv("INFORU_USER")
    
    url = "https://api.inforu.co.il/SendMessageXml.ashx"
    
    # Using the structure that aligns with their XML API requirements
    # Making sure to escape special characters if any, but f-strings are usually fine for simple text.
    # Note: Sometimes username is part of the token or separate.
    
    xml_payload = f"""<Inforu>
<User>
<Username>{api_user}</Username>
<ApiToken>{api_token}</ApiToken>
</User>
<Content Type="sms">
<Message>{message}</Message>
</Content>
<Recipients>
<PhoneNumber>{phone}</PhoneNumber>
</Recipients>
<Settings>
<SenderName>HazarSms</SenderName>
</Settings>
</Inforu>"""
    
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded'
    }

    try:
        # InforuMobile XML API often expects the XML in a 'InforuXML' parameter
        response = requests.post(url, data={'InforuXML': xml_payload}, headers=headers)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 2:
        phone_input = sys.argv[1]
        msg_input = sys.argv[2]
    else:
        phone_input = input("Enter phone number: ")
        msg_input = input("Enter message: ")
        
    if not phone_input or not msg_input:
        print("Usage: python send_test_sms.py [phone] [message]")
    else:
        send_inforu_sms(phone_input, msg_input)
