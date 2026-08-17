import pytest
import sqlite3
from database import get_conn
from simulation_system import handle_unregistered_user, handle_registered_user, USER_STATES
from questions_engine import select_questions_for_range

@pytest.fixture
def clean_db():
    conn = get_conn()
    conn.execute("DELETE FROM users WHERE phone='972540000001'")
    conn.execute("DELETE FROM subscriptions WHERE user_id IN (SELECT id FROM users WHERE phone='972540000001')")
    conn.commit()
    yield conn
    conn.execute("DELETE FROM users WHERE phone='972540000001'")
    conn.commit()
    conn.close()

def test_registration_with_rashi_only(clean_db):
    phone = "972540000001"
    
    # 1. Personal Details
    handle_unregistered_user(phone, "ישראל, ישראלי, ירושלים, 30")
    user = clean_db.execute("SELECT * FROM users WHERE phone=?", (phone,)).fetchone()
    assert user is not None
    
    # 2. Masechta
    handle_registered_user(phone, user, "ברכות ב עד ד")
    
    # 3. Rate then Hour (sent as two separate messages)
    handle_registered_user(phone, user, "1")

    # Check state is now Step 3B (awaiting hour)
    state = USER_STATES.get(phone)
    assert state['state'] == 'AWAITING_REG_STEP_3B'

    handle_registered_user(phone, user, "10")

    # Check state is now Step 4
    state = USER_STATES.get(phone)
    assert state['state'] == 'AWAITING_REG_STEP_4'
    
    # 4. Choose Rashi Only
    handle_registered_user(phone, user, "1")
    
    # Verify subscription
    sub = clean_db.execute("SELECT * FROM subscriptions WHERE user_id=?", (user['id'],)).fetchone()
    assert sub is not None
    assert sub['question_type'] == 'rashi_only'

def test_registration_with_all_questions(clean_db):
    phone = "972540000001"
    handle_unregistered_user(phone, "ישראל, ישראלי, ירושלים, 30")
    user = clean_db.execute("SELECT * FROM users WHERE phone=?", (phone,)).fetchone()
    handle_registered_user(phone, user, "ברכות ב עד ד")
    handle_registered_user(phone, user, "1")
    handle_registered_user(phone, user, "10")

    # Choose All (Rashi + Tosafot)
    handle_registered_user(phone, user, "2")
    
    sub = clean_db.execute("SELECT * FROM subscriptions WHERE user_id=?", (user['id'],)).fetchone()
    assert sub['question_type'] == 'all'

def test_question_filtering(clean_db):
    # Setup dummy questions
    tractate = clean_db.execute("SELECT id FROM tractates LIMIT 1").fetchone()
    if not tractate:
        clean_db.execute("INSERT INTO tractates (name, json_path) VALUES ('מבחן', 'data/ברכות.json')")
        tractate = clean_db.execute("SELECT id FROM tractates WHERE name='מבחן'").fetchone()
    
    t_id = tractate['id']
    clean_db.execute("DELETE FROM questions WHERE tractate_id=?", (t_id,))
    clean_db.execute("INSERT INTO questions (tractate_id, external_id, question_text, question_type, start_daf, end_daf) VALUES (?,?,?,?,?,?)",
                 (t_id, 'q1', 'שאלה מרש"י', 'רש"י', 2.0, 2.0))
    clean_db.execute("INSERT INTO questions (tractate_id, external_id, question_text, question_type, start_daf, end_daf) VALUES (?,?,?,?,?,?)",
                 (t_id, 'q2', 'שאלה מתוספות', "תוס'", 2.0, 2.0))
    clean_db.commit()
    
    # Case 1: Rashi only
    questions = select_questions_for_range(t_id, 2.0, 2.5, [], max_questions=10, question_type_pref='rashi_only')
    assert len(questions) == 1
    assert questions[0]['text'] == 'שאלה מרש"י'
    
    # Case 2: All
    questions_all = select_questions_for_range(t_id, 2.0, 2.5, [], max_questions=10, question_type_pref='all')
    assert len(questions_all) == 2
