import json
from registration import register_user
from tests.helpers import get_last_sms, create_user_with_subscription


def _create_request(db_conn, user_id, category="באג/תקלה", message="יש לי תקלה", status="new"):
    db_conn.execute(
        "INSERT INTO support_requests (user_id, category, message, status) VALUES (?,?,?,?)",
        (user_id, category, message, status),
    )
    db_conn.commit()
    row = db_conn.execute("SELECT last_insert_rowid() as id").fetchone()
    return row["id"]


def test_support_users_lists_grouped_counts_and_sort_order(client, db_conn, auth_headers):
    user_a = register_user("0501110001", "UserA")
    user_b = register_user("0501110002", "UserB")

    _create_request(db_conn, user_a, status="completed")
    _create_request(db_conn, user_b, status="new")

    res = client.get("/api/support/users", headers=auth_headers)
    assert res.status_code == 200
    data = res.get_json()
    assert len(data) == 2

    # user_b has an open request, so it should sort first.
    assert data[0]["user_id"] == user_b
    assert data[0]["open_count"] == 1
    assert data[0]["new_count"] == 1
    assert data[1]["user_id"] == user_a
    assert data[1]["open_count"] == 0
    assert data[1]["completed_count"] == 1


def test_support_requests_filtered_by_user_id(client, db_conn, auth_headers):
    user_a = register_user("0501110003", "UserA")
    user_b = register_user("0501110004", "UserB")
    _create_request(db_conn, user_a)
    _create_request(db_conn, user_b)

    res = client.get(f"/api/support/requests?user_id={user_a}", headers=auth_headers)
    assert res.status_code == 200
    data = res.get_json()
    assert len(data) == 1
    assert data[0]["user_id"] == user_a


def test_support_thread_returns_sms_history(client, db_conn, auth_headers):
    phone = "0501110005"
    user_id = register_user(phone, "UserC")
    db_conn.execute(
        "INSERT INTO sms_log (user_id, phone, direction, message) VALUES (?,?,?,?)",
        (user_id, phone, "in", "שלום"),
    )
    db_conn.execute(
        "INSERT INTO sms_log (user_id, phone, direction, message) VALUES (?,?,?,?)",
        (user_id, phone, "out", "היי, איך אפשר לעזור?"),
    )
    db_conn.commit()

    res = client.get(f"/api/support/thread?phone={phone}", headers=auth_headers)
    assert res.status_code == 200
    data = res.get_json()
    assert len(data) == 2
    messages = {m["message"] for m in data}
    assert "שלום" in messages
    assert "היי, איך אפשר לעזור?" in messages


def test_support_reply_sends_sms_without_closing(client, db_conn, auth_headers):
    phone = "0501110006"
    user_id = register_user(phone, "UserD")
    req_id = _create_request(db_conn, user_id, status="new")

    res = client.post(
        "/api/support/reply",
        headers=auth_headers,
        json={"user_id": user_id, "message": "תשובה לפנייה", "request_id": req_id},
    )
    assert res.status_code == 200
    assert res.get_json()["status"] == "success"
    assert get_last_sms(phone) == "תשובה לפנייה"

    row = db_conn.execute("SELECT status, last_response_at FROM support_requests WHERE id=?", (req_id,)).fetchone()
    assert row["status"] == "new"
    assert row["last_response_at"] is not None


def test_support_reply_without_request_id_only_sends_sms(client, db_conn, auth_headers):
    phone = "0501110007"
    user_id = register_user(phone, "UserE")
    req_id = _create_request(db_conn, user_id, status="new")

    res = client.post(
        "/api/support/reply",
        headers=auth_headers,
        json={"user_id": user_id, "message": "הודעה כללית"},
    )
    assert res.status_code == 200
    assert get_last_sms(phone) == "הודעה כללית"

    row = db_conn.execute("SELECT status, last_response_at FROM support_requests WHERE id=?", (req_id,)).fetchone()
    assert row["status"] == "new"
    assert row["last_response_at"] is None


def test_support_reply_rate_limited(client, db_conn, auth_headers):
    phone = "0501110008"
    user_id = register_user(phone, "UserF")

    for _ in range(30):
        db_conn.execute(
            "INSERT INTO sms_log (user_id, phone, direction, message) VALUES (?,?,?,?)",
            (user_id, phone, "out", "הודעה"),
        )
    db_conn.commit()

    res = client.post(
        "/api/support/reply",
        headers=auth_headers,
        json={"user_id": user_id, "message": "עוד הודעה"},
    )
    assert res.status_code == 429


def test_get_user_returns_profile(client, auth_headers):
    user_id = register_user("0501110009", "UserG", "כהן", "חיפה", 40)

    res = client.get(f"/api/users/{user_id}", headers=auth_headers)
    assert res.status_code == 200
    data = res.get_json()
    assert data["phone"] == "0501110009"
    assert data["name"] == "UserG"
    assert data["last_name"] == "כהן"
    assert data["city"] == "חיפה"
    assert data["age"] == 40


def test_put_user_updates_fields_phone_readonly(client, db_conn, auth_headers):
    user_id = register_user("0501110010", "UserH")

    res = client.put(
        f"/api/users/{user_id}",
        headers=auth_headers,
        json={"name": "שם חדש", "last_name": "משפחה", "city": "תל אביב", "age": 33, "phone": "0509999999"},
    )
    assert res.status_code == 200

    row = db_conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    assert row["name"] == "שם חדש"
    assert row["last_name"] == "משפחה"
    assert row["city"] == "תל אביב"
    assert row["age"] == 33
    assert row["phone"] == "0501110010"  # unchanged despite being sent


def test_put_user_clears_optional_fields_with_blank_string(client, db_conn, auth_headers):
    user_id = register_user("0501110011", "UserI", "כהן", "חיפה", 40)

    res = client.put(
        f"/api/users/{user_id}",
        headers=auth_headers,
        json={"name": "UserI", "last_name": "", "city": None, "age": ""},
    )
    assert res.status_code == 200

    row = db_conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    assert row["last_name"] is None
    assert row["city"] is None
    assert row["age"] is None


def test_put_user_rejects_missing_name(client, auth_headers):
    user_id = register_user("0501110012", "UserJ")
    res = client.put(f"/api/users/{user_id}", headers=auth_headers, json={"name": "  "})
    assert res.status_code == 400


def test_put_user_rejects_invalid_age(client, auth_headers):
    user_id = register_user("0501110013", "UserK")
    res = client.put(f"/api/users/{user_id}", headers=auth_headers, json={"name": "UserK", "age": "abc"})
    assert res.status_code == 400

    res2 = client.put(f"/api/users/{user_id}", headers=auth_headers, json={"name": "UserK", "age": 200})
    assert res2.status_code == 400


def test_get_user_subscriptions_returns_list(client, auth_headers):
    user_id, sub_id = create_user_with_subscription("0501110015", "UserM")

    res = client.get(f"/api/users/{user_id}/subscriptions", headers=auth_headers)
    assert res.status_code == 200
    data = res.get_json()
    assert len(data) == 1
    assert data[0]["id"] == sub_id
    assert data[0]["tractate_name"] == "ברכות"


def test_put_subscription_updates_fields(client, db_conn, auth_headers):
    user_id, sub_id = create_user_with_subscription("0501110016", "UserN")

    res = client.put(
        f"/api/subscriptions/{sub_id}",
        headers=auth_headers,
        json={"current_daf": 5.5, "end_daf": 20, "dafim_per_day": 2, "send_hour": 9, "question_type": "rashi_only"},
    )
    assert res.status_code == 200

    row = db_conn.execute("SELECT * FROM subscriptions WHERE id=?", (sub_id,)).fetchone()
    assert row["current_daf"] == 5.5
    assert row["end_daf"] == 20
    assert row["dafim_per_day"] == 2
    assert row["send_hour"] == 9
    assert row["question_type"] == "rashi_only"


def test_put_subscription_rejects_invalid_data(client, auth_headers):
    user_id, sub_id = create_user_with_subscription("0501110017", "UserO")

    # end_daf before current_daf
    res = client.put(
        f"/api/subscriptions/{sub_id}",
        headers=auth_headers,
        json={"current_daf": 10, "end_daf": 5, "dafim_per_day": 1, "send_hour": 8, "question_type": "all"},
    )
    assert res.status_code == 400

    # invalid question_type
    res2 = client.put(
        f"/api/subscriptions/{sub_id}",
        headers=auth_headers,
        json={"current_daf": 2, "end_daf": 10, "dafim_per_day": 1, "send_hour": 8, "question_type": "bogus"},
    )
    assert res2.status_code == 400

    # invalid send_hour
    res3 = client.put(
        f"/api/subscriptions/{sub_id}",
        headers=auth_headers,
        json={"current_daf": 2, "end_daf": 10, "dafim_per_day": 1, "send_hour": 25, "question_type": "all"},
    )
    assert res3.status_code == 400


def test_support_routes_require_auth(client):
    user_id = register_user("0501110014", "UserL")

    assert client.get("/api/support/users").status_code == 401
    assert client.get("/api/support/thread?phone=0501110014").status_code == 401
    assert client.post("/api/support/reply", json={"user_id": user_id, "message": "hi"}).status_code == 401
    assert client.get(f"/api/users/{user_id}").status_code == 401
