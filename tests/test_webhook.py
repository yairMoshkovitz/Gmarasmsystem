from tests.helpers import get_last_sms
from database import get_conn

def test_webhook_xml_format(client):
    phone = "0507770001"
    xml_data = f"""<Inforu>
        <PhoneNumber>{phone}</PhoneNumber>
        <Message>שלום</Message>
    </Inforu>"""
    
    response = client.post('/webhook/inforu', data={'IncomingXML': xml_data})
    assert response.status_code == 200
    
    # User should get registration instructions since not registered
    assert "ברוך הבא" in get_last_sms(phone)

def test_webhook_json_format(client):
    phone = "0507770002"
    json_data = {
        "Data": [
            {
                "Value": phone,
                "Message": "עזרה"
            }
        ]
    }
    
    response = client.post('/webhook/inforu', json=json_data)
    assert response.status_code == 200
    assert "ברוך הבא" in get_last_sms(phone)

def test_webhook_form_params(client):
    phone = "0507770003"
    response = client.post('/webhook/inforu', data={'Phone': phone, 'Text': 'בדיקה'})
    assert response.status_code == 200
    assert "ברוך הבא" in get_last_sms(phone)

def test_webhook_invalid_data(client):
    response = client.post('/webhook/inforu', data={'Wrong': 'Data'})
    assert response.status_code == 400
