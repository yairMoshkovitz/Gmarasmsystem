import requests
import xml.etree.ElementTree as ET
import os
from dotenv import load_dotenv

load_dotenv()

def get_incoming_sms(username, password):
    url = "https://api.inforu.co.il/SendMessageXml.ashx"
    
    # Updated XML format for pulling incoming SMS
    xml_data = f"""
    <Inforu>
        <User>
            <Username>{username}</Username>
            <Password>{password}</Password>
        </User>
        <Content Type="GetIncomingSms">
            <Query></Query>
        </Content>
    </Inforu>
    """
    
    try:
        response = requests.post(url, data={'InforuXML': xml_data})
        print(f"Status Code: {response.status_code}")
        print("Response Content:")
        print(response.text)
        return response.text
    except Exception as e:
        print(f"Error: {e}")
        return None

if __name__ == "__main__":
    USER = os.getenv("INFORU_USER")
    PASS = os.getenv("INFORU_TOKEN")
    get_incoming_sms(USER, PASS)
