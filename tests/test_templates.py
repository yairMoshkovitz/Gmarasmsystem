from registration import get_template
from tests.helpers import create_user_with_subscription, simulate_inbound, get_last_sms

def test_template_rendering():
    name = "בדיקה"
    # Basic rendering
    welcome = get_template("welcome_new_user", name=name)
    assert f"שלום {name}!" in welcome
    assert "תודה שנרשמת" in welcome

def test_template_not_found():
    res = get_template("non_existent_template")
    assert "Template non_existent_template not found" in res

def test_footer_auto_append():
    # 'ask_update_daf' should have menu_footer appended
    res = get_template("ask_update_daf")
    assert "לאיזה דף הגעת" in res
    assert "לחזרה לתפריט שלח 0" in res

def test_template_missing_placeholders():
    # Should return an error message rather than crashing
    res = get_template("welcome_new_user") # missing 'name'
    assert "format error" in res
