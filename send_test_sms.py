import requests
import sys

def send_inforu_sms(phone, message):
    # The token found in token.txt line 1
    api_token = "3a45cda4-ff7e-4b99-91c8-d96e74cb872b"
    
    url = "https://api.inforu.co.il/SendMessageXml.ashx"
    
    # Using the structure that aligns with their XML API requirements
    # Making sure to escape special characters if any, but f-strings are usually fine for simple text.
    # Note: Sometimes username is part of the token or separate.
    
    xml_payload = f"""<Inforu>
<User>
<Username>hazarasms</Username>
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
