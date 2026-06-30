from tests.helpers import create_user_with_subscription, simulate_inbound, get_last_sms, get_all_outgoing_sms
from database import get_conn
from simulation_system import USER_STATES

def test_question_selection_and_answer():
    phone = "0503330001"
    create_user_with_subscription(phone, "Quest1")
    
    # Trigger first question
    simulate_inbound(phone, "1")
    all_msgs = get_all_outgoing_sms(phone)
    assert any("מסכת ברכות, דף ב ע\"א" in m for m in all_msgs)
    
    # Answer question
    simulate_inbound(phone, "כן")
    
    # Check if answered in DB
    conn = get_conn()
    q = conn.execute("SELECT responded_at, response_text FROM sent_questions ORDER BY sent_at DESC LIMIT 1").fetchone()
    assert q['responded_at'] is not None
    assert q['response_text'] == "כן"
    conn.close()
    
    # Should get second question (daily limit is 2)
    # The last outgoing message should now be the new question
    assert "יודע את התשובה?" in get_last_sms(phone)

def test_daily_limit_questions():
    phone = "0503330002"
    create_user_with_subscription(phone, "Quest2")
    
    simulate_inbound(phone, "1")
    simulate_inbound(phone, "כן") # Answer 1
    
    # After 1st answer, should get 2nd question
    assert "יודע את התשובה?" in get_last_sms(phone)
    
    simulate_inbound(phone, "כן") # Answer 2
    
    # After 2nd answer, should get study closure
    last_msg = get_last_sms(phone)
    assert "תמשיך בהתמדה" in last_msg
    assert "הלימוד מחר" in last_msg

def test_invalid_answer_response():
    phone = "0503330003"
    create_user_with_subscription(phone, "Quest3")
    
    simulate_inbound(phone, "1")
    simulate_inbound(phone, "אולי") # Invalid answer
    
    assert "כדי לענות על השאלה יש לשלוח 'כן' או 'לא'" in get_last_sms(phone)
    assert USER_STATES[phone]['state'] == "AWAITING_ANSWER"

def test_already_sent_filtering():
    phone = "0503330004"
    user_id, sub_id = create_user_with_subscription(phone, "Quest4")
    
    # Manually insert a sent question for Daf 2
    conn = get_conn()
    conn.execute(
        "INSERT INTO sent_questions (user_id, subscription_id, question_id, question_text) VALUES (?, ?, ?, ?)",
        (user_id, sub_id, "א", "שאלה שכבר נשלחה")
    )
    conn.commit()
    conn.close()
    
    simulate_inbound(phone, "1")
    # Should get a DIFFERENT question, not "שאלה שכבר נשלחה"
    last_msg = get_last_sms(phone)
    assert "שאלה שכבר נשלחה" not in last_msg
