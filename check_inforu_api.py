import requests
import xml.etree.ElementTree as ET

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
    # Credentials from token.txt
    USER = "hazarasms"
    PASS = "3a45cda4-ff7e-4b99-91c8-d96e74cb872b"
    get_incoming_sms(USER, PASS)
