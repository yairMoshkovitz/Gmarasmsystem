from flask import Flask, render_template, request, jsonify, Response
import os
import json
import threading
import time
import base64
import xml.etree.ElementTree as ET
from datetime import datetime
from database import get_conn
from sms_service import get_sms_history, receive_sms, set_live_mode, get_live_mode
from simulation_system import handle_unregistered_user, handle_registered_user
from scheduler import run_hour

app = Flask(__name__)

def basic_auth_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        # Skip auth for webhooks
        path = request.path.lower()
        if path.startswith('/webhook/') or path == '/webhook' or path == '/send':
            return f(*args, **kwargs)

        auth = request.headers.get('Authorization')
        if not auth or not auth.startswith('Basic '):
            return Response(
                'Login required', 401,
                {'WWW-Authenticate': 'Basic realm="Protected Area"'}
            )

        try:
            encoded_creds = auth.split(' ')[1]
            decoded_creds = base64.b64decode(encoded_creds).decode('utf-8')
            user, password = decoded_creds.split(':', 1)
        except Exception:
            return Response(
                'Invalid credentials', 401,
                {'WWW-Authenticate': 'Basic realm="Protected Area"'}
            )

        if user != 'admin' or password != os.environ.get('SITE_PASSWORD'):
            return Response(
                'Wrong password', 403
            )
        return f(*args, **kwargs)
    return decorated

@app.before_request
def basic_auth_legacy():
    path = request.path.lower()
    if path.startswith('/webhook/') or path == '/webhook' or path == '/send':
        return

    auth = request.headers.get('Authorization')
    if not auth or not auth.startswith('Basic '):
        return Response(
            'Login required', 401,
            {'WWW-Authenticate': 'Basic realm="Protected Area"'}
        )

    try:
        encoded_creds = auth.split(' ')[1]
        decoded_creds = base64.b64decode(encoded_creds).decode('utf-8')
        user, password = decoded_creds.split(':', 1)
    except Exception:
        return Response(
            'Invalid credentials', 401,
            {'WWW-Authenticate': 'Basic realm="Protected Area"'}
        )

    if user != 'admin' or password != os.environ.get('SITE_PASSWORD'):
        return Response(
            'Wrong password', 403
        )

# Initialize DB on startup
from database import init_db, seed_tractates, seed_sms_templates
try:
    init_db()
    seed_tractates()
    seed_sms_templates()
except Exception as e:
    print(f"⚠️ Database initialization warning: {e}")

# Background scheduler thread
def start_background_scheduler():
    def scheduler_loop():
        try:
            print("Background Scheduler Started.")
        except:
            pass
            
        last_hour = -1
        while True:
            from scheduler import get_israel_time
            now = get_israel_time()
            if now.hour != last_hour:
                try:
                    print(f"🕒 Scheduler checking for hour {now.hour}...")
                except:
                    pass
                run_hour(now.hour)
                last_hour = now.hour
            time.sleep(60)
    
    thread = threading.Thread(target=scheduler_loop, daemon=True)
    thread.start()

# Start scheduler on startup
if os.environ.get('WERKZEUG_RUN_MAIN') == 'true' or not app.debug:
    start_background_scheduler()

@app.route('/toggle_mode', methods=['GET', 'POST'])
def toggle_mode():
    if request.method == 'POST':
        data = request.json
        enabled = data.get('enabled', False)
        set_live_mode(enabled)
        return jsonify({"status": "ok", "live_mode": enabled})
    else:
        return jsonify({"live_mode": get_live_mode()})

@app.route('/')
def dashboard():
    conn = get_conn()
    stats = {
        "users_count": conn.execute("SELECT COUNT(*) FROM users").fetchone()[0],
        "messages_count": conn.execute("SELECT COUNT(*) FROM sms_log").fetchone()[0],
        "active_tractates": conn.execute("SELECT COUNT(DISTINCT name) FROM tractates").fetchone()[0],
        "today_messages": conn.execute("SELECT COUNT(*) FROM sms_log WHERE date(sent_at) = CURRENT_DATE" if os.environ.get("DATABASE_URL") else "SELECT COUNT(*) FROM sms_log WHERE date(sent_at) = date('now')").fetchone()[0]
    }
    conn.close()
    return render_template('dashboard.html', stats=stats)

@app.route('/demo')
def demo_dashboard():
    return render_template('demo_dashboard.html')

@app.route('/analytics')
def analytics_page():
    conn = get_conn()
    cities = conn.execute("SELECT DISTINCT city FROM users WHERE city IS NOT NULL ORDER BY city").fetchall()
    tractates = conn.execute("SELECT id, name FROM tractates ORDER BY name").fetchall()
    conn.close()
    return render_template('analytics.html', cities=[c['city'] for c in cities], tractates=tractates)

@app.route('/api/analytics/data')
def analytics_data():
    city = request.args.get('city')
    tractate_id = request.args.get('tractate_id')
    min_yes = request.args.get('min_yes', type=int, default=0)
    
    conn = get_conn()
    is_postgres = bool(os.environ.get("DATABASE_URL"))
    placeholder = "%s" if is_postgres else "?"
    
    p_esc = "%" if not is_postgres else "%%"
    user_query = f"""
        SELECT u.*, 
        (SELECT count(*) FROM sent_questions sq 
         WHERE sq.user_id = u.id 
         AND (sq.response_text LIKE '{p_esc}כן{p_esc}' OR sq.response_text LIKE '{p_esc}נכון{p_esc}' OR sq.response_text LIKE '{p_esc}אמת{p_esc}')) as yes_count,
        (SELECT count(*) FROM sent_questions sq WHERE sq.user_id = u.id) as total_questions
        FROM users u
        WHERE 1=1
    """
    params = []
    if city:
        user_query += f" AND u.city = {placeholder}"
        params.append(city)
    
    if tractate_id:
        user_query += f" AND EXISTS (SELECT 1 FROM subscriptions s WHERE s.user_id = u.id AND s.tractate_id = {placeholder})"
        params.append(tractate_id)
        
    users = conn.execute(user_query, params).fetchall()
    filtered_users = [dict(u) for u in users if u['yes_count'] >= min_yes]
    
    raw_users = conn.execute("SELECT * FROM users LIMIT 1000").fetchall()
    raw_subs = conn.execute("""
        SELECT s.*, u.phone, u.name as user_name, t.name as tractate_name 
        FROM subscriptions s
        JOIN users u ON s.user_id = u.id
        JOIN tractates t ON s.tractate_id = t.id
        LIMIT 1000
    """).fetchall()
    raw_questions = conn.execute("""
        SELECT sq.*, u.phone, u.name as user_name 
        FROM sent_questions sq
        JOIN users u ON sq.user_id = u.id
        ORDER BY sent_at DESC
        LIMIT 1000
    """).fetchall()
    raw_logs = conn.execute("SELECT * FROM sms_log ORDER BY sent_at DESC LIMIT 1000").fetchall()
    
    conn.close()
    
    return jsonify({
        "filtered_users": filtered_users,
        "raw_data": {
            "users": [dict(r) for r in raw_users],
            "subscriptions": [dict(r) for r in raw_subs],
            "sent_questions": [dict(r) for r in raw_questions],
            "sms_log": [dict(r) for r in raw_logs]
        }
    })

@app.route('/api/stats/charts')
def chart_stats():
    conn = get_conn()
    is_postgres = bool(os.environ.get("DATABASE_URL"))
    
    if is_postgres:
        users_query = "SELECT date(registered_at) as date, count(*) as count FROM users GROUP BY date(registered_at) ORDER BY date DESC LIMIT 30"
    else:
        users_query = "SELECT date(registered_at) as date, count(*) as count FROM users GROUP BY date(registered_at) ORDER BY date DESC LIMIT 30"
    
    users_data = conn.execute(users_query).fetchall()
    yes_keywords = ['כן', 'נכון', 'אמת', 'יאפ', 'חיובי']
    responses = conn.execute("SELECT response_text FROM sent_questions WHERE responded_at IS NOT NULL ORDER BY responded_at DESC LIMIT 500").fetchall()
    
    yes_count = 0
    no_count = 0
    for r in responses:
        txt = (r['response_text'] or "").strip().lower()
        if any(kw in txt for kw in yes_keywords):
            yes_count += 1
        else:
            no_count += 1
            
    age_data = conn.execute("SELECT CASE \
        WHEN age < 13 THEN 'עד 12' \
        WHEN age BETWEEN 13 AND 18 THEN '13-18' \
        WHEN age BETWEEN 19 AND 24 THEN '19-24' \
        WHEN age BETWEEN 25 AND 30 THEN '25-30' \
        WHEN age BETWEEN 31 AND 40 THEN '31-40' \
        WHEN age > 40 THEN '41+' \
        ELSE 'לא צוין' END as age_group, count(*) as count \
        FROM users GROUP BY age_group").fetchall()
    
    city_data = conn.execute("SELECT COALESCE(city, 'לא צוין') as city, count(*) as count FROM users GROUP BY city ORDER BY count DESC LIMIT 10").fetchall()
    tractate_stats = conn.execute("""
        SELECT COALESCE(t.name, 'מסכת #' || s.tractate_id) as name, count(s.id) as count 
        FROM subscriptions s
        LEFT JOIN tractates t ON s.tractate_id = t.id 
        WHERE s.is_active = 1
        GROUP BY s.tractate_id, t.name
        ORDER BY count DESC
    """).fetchall()
    
    conn.close()
    
    return jsonify({
        "users_growth": [{"date": r['date'], "count": r['count']} for r in reversed(users_data)],
        "answers": {"yes": yes_count, "no": no_count},
        "ages": [{"group": r['age_group'], "count": r['count']} for r in age_data],
        "cities": [{"city": r['city'], "count": r['count']} for r in city_data],
        "tractates": [{"name": r['name'], "count": r['count']} for r in tractate_stats]
    })

@app.route('/simulator')
def index():
    return render_template('index.html')

@app.route('/edit-templates')
def edit_templates():
    response = render_template('edit_templates.html')
    return response, 200, {
        'Cache-Control': 'no-cache, no-store, must-revalidate',
        'Pragma': 'no-cache',
        'Expires': '0'
    }

@app.route('/support')
@basic_auth_required
def support_page():
    return render_template('support.html')

@app.route('/scheduled-messages')
@basic_auth_required
def scheduled_messages_page():
    return render_template('scheduled_messages.html')

@app.route('/api/scheduled-messages/subscriptions')
@basic_auth_required
def get_scheduled_subscriptions():
    filter_type = request.args.get('type', 'exact')
    hour = request.args.get('hour', type=int)
    
    if hour is None:
        return jsonify([])
        
    query = """
        SELECT s.*, u.phone, u.name as user_name, t.name as tractate_name 
        FROM subscriptions s
        JOIN users u ON s.user_id = u.id
        JOIN tractates t ON s.tractate_id = t.id
        WHERE s.is_active = 1
    """
    params = []
    if filter_type == 'exact':
        query += " AND s.send_hour = ?"
        params.append(hour)
    elif filter_type == 'after':
        query += " AND s.send_hour > ?"
        params.append(hour)
    elif filter_type == 'before':
        query += " AND s.send_hour < ?"
        params.append(hour)
        
    conn = get_conn()
    rows = conn.execute(query, params).fetchall()
    conn.close()
    
    return jsonify([dict(r) for r in rows])

@app.route('/api/scheduled-messages/send', methods=['POST'])
@basic_auth_required
def send_scheduled_broadcast():
    data = request.json
    sub_ids = data.get('subscription_ids', [])
    message = data.get('message')
    mode = data.get('mode', 'now')
    
    if not message or not sub_ids:
        return jsonify({"error": "Missing message or subscriptions"}), 400
        
    from sms_service import send_sms
    conn = get_conn()
    placeholders = ",".join(["?"] * len(sub_ids))
    rows = conn.execute(f"""
        SELECT s.user_id, u.phone 
        FROM subscriptions s 
        JOIN users u ON s.user_id = u.id 
        WHERE s.id IN ({placeholders})
    """, sub_ids).fetchall()
    
    sent_count = 0
    processed_users = set()
    
    if mode == 'now':
        for row in rows:
            uid = row['user_id']
            if uid not in processed_users:
                send_sms(row['phone'], message, uid)
                processed_users.add(uid)
                sent_count += 1
    else:
        for row in rows:
            uid = row['user_id']
            if uid not in processed_users:
                conn.execute(
                    "INSERT INTO pending_admin_messages (user_id, message) VALUES (?, ?)",
                    (uid, message)
                )
                processed_users.add(uid)
                sent_count += 1
        conn.commit()
            
    conn.close()
    return jsonify({"status": "success", "sent_count": sent_count})

@app.route('/api/scheduled-messages/trigger-daily', methods=['POST'])
@basic_auth_required
def trigger_daily_questions_manually():
    data = request.json
    sub_ids = data.get('subscription_ids', [])
    
    if not sub_ids:
        return jsonify({"error": "No subscriptions selected"}), 400
        
    from scheduler import send_daily_questions
    from database import get_conn
    
    conn = get_conn()
    placeholders = ",".join(["?"] * len(sub_ids))
    rows = conn.execute(f"""
        SELECT s.*, t.name as tractate_name, u.phone, u.name as user_name
        FROM subscriptions s
        JOIN tractates t ON s.tractate_id = t.id
        JOIN users u ON s.user_id = u.id
        WHERE s.id IN ({placeholders})
    """, sub_ids).fetchall()
    conn.close()
    
    triggered_count = 0
    for r in rows:
        try:
            send_daily_questions(dict(r))
            triggered_count += 1
        except Exception as e:
            print(f"Error triggering daily for sub {r['id']}: {e}")
            
    return jsonify({"status": "success", "triggered_count": triggered_count})

@app.route('/api/support/assignees', methods=['GET', 'POST', 'DELETE'])
@basic_auth_required
def manage_assignees():
    conn = get_conn()
    if request.method == 'POST':
        data = request.json
        name = data.get('name')
        if name:
            conn.execute("INSERT OR IGNORE INTO assignees (name) VALUES (?)", (name,))
            conn.commit()
        conn.close()
        return jsonify({"status": "success"})
    
    elif request.method == 'DELETE':
        name = request.args.get('name')
        if name:
            conn.execute("UPDATE assignees SET is_active = 0 WHERE name = ?", (name,))
            conn.commit()
        conn.close()
        return jsonify({"status": "success"})
        
    rows = conn.execute("SELECT name FROM assignees WHERE is_active = 1").fetchall()
    conn.close()
    return jsonify([r['name'] for r in rows])

@app.route('/api/support/requests')
@basic_auth_required
def get_support_requests():
    category = request.args.get('category')
    status = request.args.get('status')
    assigned_to = request.args.get('assigned_to')
    
    query = """
        SELECT r.*, u.name || ' ' || COALESCE(u.last_name, '') as user_full_name, u.phone 
        FROM support_requests r
        JOIN users u ON r.user_id = u.id
        WHERE 1=1
    """
    params = []
    if category:
        query += " AND r.category = ?"
        params.append(category)
    if status:
        query += " AND r.status = ?"
        params.append(status)
    if assigned_to:
        query += " AND r.assigned_to = ?"
        params.append(assigned_to)
        
    query += " ORDER BY r.created_at DESC"
    
    conn = get_conn()
    rows = conn.execute(query, params).fetchall()
    conn.close()
    
    return jsonify([dict(r) for r in rows])

@app.route('/api/support/update', methods=['POST'])
@basic_auth_required
def update_support_request():
    data = request.json
    req_id = data.get('id')
    status = data.get('status')
    assigned_to = data.get('assigned_to')
    response_text = data.get('response_text')
    
    if not req_id:
        return jsonify({"error": "Missing ID"}), 400
        
    conn = get_conn()
    if status:
        conn.execute("UPDATE support_requests SET status = ? WHERE id = ?", (status, req_id))
    if assigned_to is not None:
        conn.execute("UPDATE support_requests SET assigned_to = ? WHERE id = ?", (assigned_to, req_id))
        
    if response_text:
        req = conn.execute("""
            SELECT r.*, u.phone 
            FROM support_requests r 
            JOIN users u ON r.user_id = u.id 
            WHERE r.id = ?
        """, (req_id,)).fetchone()
        
        if req:
            from sms_service import send_sms
            send_sms(req['phone'], response_text)
            conn.execute("""
                UPDATE support_requests 
                SET last_response_at = CURRENT_TIMESTAMP, 
                    status = 'completed',
                    resolved_at = CASE WHEN status != 'completed' THEN CURRENT_TIMESTAMP ELSE resolved_at END
                WHERE id = ?
            """, (req_id,))
            
    conn.commit()
    conn.close()
    return jsonify({"status": "success"})

@app.route('/api/templates', methods=['GET', 'POST'])
def manage_templates():
    from registration import clear_template_cache
    template_path = os.path.join(os.path.dirname(__file__), 'sms_templates.json')
    
    if request.method == 'POST':
        data = request.json
        conn = get_conn()
        is_postgres = bool(os.environ.get("DATABASE_URL"))
        for key, content in data.items():
            if is_postgres:
                conn.execute("""
                    INSERT INTO sms_templates (key, content, updated_at) VALUES (%s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (key) DO UPDATE SET content = EXCLUDED.content, updated_at = EXCLUDED.updated_at
                """, (key, content))
            else:
                conn.execute("INSERT OR REPLACE INTO sms_templates (key, content, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)", (key, content))
        conn.commit()
        conn.close()
        
        try:
            current_json = {}
            if os.path.exists(template_path):
                with open(template_path, 'r', encoding='utf-8') as f:
                    current_json = json.load(f)
            current_json.update(data)
            with open(template_path, 'w', encoding='utf-8') as f:
                json.dump(current_json, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"Error updating JSON file: {e}")

        clear_template_cache()
        return jsonify({"status": "success"})
    
    conn = get_conn()
    rows = conn.execute("SELECT key, content FROM sms_templates").fetchall()
    conn.close()
    templates = {r["key"]: r["content"] for r in rows}
    
    if not templates:
        if os.path.exists(template_path):
            with open(template_path, 'r', encoding='utf-8') as f:
                templates = json.load(f)
    return jsonify(templates)

@app.route('/api/templates/diff')
def templates_diff():
    template_path = os.path.join(os.path.dirname(__file__), 'sms_templates.json')
    if not os.path.exists(template_path):
        return jsonify({"error": "JSON file not found"}), 404
    try:
        with open(template_path, 'r', encoding='utf-8') as f:
            json_templates = json.load(f)
    except Exception as e:
        return jsonify({"error": f"Failed to parse JSON: {e}"}), 500
        
    conn = get_conn()
    rows = conn.execute("SELECT key, content FROM sms_templates").fetchall()
    conn.close()
    db_templates = {r["key"]: r["content"] for r in rows}
    
    diff = {"new_in_json": [], "different": [], "only_in_db": []}
    for key, json_content in json_templates.items():
        if key not in db_templates:
            diff["new_in_json"].append({"key": key, "json_content": json_content})
        elif db_templates[key] != json_content:
            diff["different"].append({"key": key, "json_content": json_content, "db_content": db_templates[key]})
            
    for key in db_templates:
        if key not in json_templates:
            diff["only_in_db"].append(key)
    return jsonify(diff)

@app.route('/api/templates/sync', methods=['POST'])
def sync_templates():
    from registration import clear_template_cache
    data = request.json
    keys = data.get('keys', [])
    template_path = os.path.join(os.path.dirname(__file__), 'sms_templates.json')
    with open(template_path, 'r', encoding='utf-8') as f:
        json_templates = json.load(f)
        
    conn = get_conn()
    is_postgres = bool(os.environ.get("DATABASE_URL"))
    for key in keys:
        if key in json_templates:
            content = json_templates[key]
            if is_postgres:
                conn.execute("""
                    INSERT INTO sms_templates (key, content, updated_at) VALUES (%s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (key) DO UPDATE SET content = EXCLUDED.content, updated_at = EXCLUDED.updated_at
                """, (key, content))
            else:
                conn.execute("INSERT OR REPLACE INTO sms_templates (key, content, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)", (key, content))
    conn.commit()
    conn.close()
    clear_template_cache()
    return jsonify({"status": "success"})

@app.route('/api/templates/sync-to-json', methods=['POST'])
def sync_templates_to_json():
    data = request.json
    keys = data.get('keys', [])
    conn = get_conn()
    rows = conn.execute("SELECT key, content FROM sms_templates").fetchall()
    conn.close()
    db_templates = {r["key"]: r["content"] for r in rows}
    
    template_path = os.path.join(os.path.dirname(__file__), 'sms_templates.json')
    try:
        current_json = {}
        if os.path.exists(template_path):
            with open(template_path, 'r', encoding='utf-8') as f:
                current_json = json.load(f)
        for key in keys:
            if key in db_templates:
                current_json[key] = db_templates[key]
        with open(template_path, 'w', encoding='utf-8') as f:
            json.dump(current_json, f, ensure_ascii=False, indent=4)
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/history')
def history():
    phone = request.args.get('phone')
    if not phone:
        return jsonify([])
    return jsonify(get_sms_history(phone))

@app.route('/send', methods=['POST'])
def send():
    data = request.json
    phone = data.get('phone')
    message = data.get('message')
    if not phone or not message:
        return jsonify({"error": "Missing phone or message"}), 400
    process_incoming_sms(phone, message)
    return jsonify({"status": "ok"})

@app.route('/webhook/inforu', methods=['GET', 'POST'], strict_slashes=False)
@app.route('/WEBHOOK/INFORU', methods=['GET', 'POST'], strict_slashes=False)
def inforu_webhook():
    print(f"--- Incoming Webhook {request.method} ---")
    phone = None
    message = None
    
    incoming_xml = request.form.get('IncomingXML')
    if incoming_xml:
        try:
            root = ET.fromstring(incoming_xml)
            phone = root.findtext('PhoneNumber')
            message = root.findtext('Message')
        except Exception as e:
            print(f"Error parsing IncomingXML: {e}")

    if not phone:
        phone = (request.args.get('Phone') or request.form.get('Phone') or request.args.get('from') or request.form.get('from'))
    if not message:
        message = (request.args.get('Text') or request.form.get('Text') or request.args.get('message') or request.form.get('message'))

    if not phone or not message:
        try:
            json_data = request.get_json(silent=True)
            if json_data:
                if 'Data' in json_data and isinstance(json_data['Data'], list) and len(json_data['Data']) > 0:
                    item = json_data['Data'][0]
                    phone = phone or item.get('Value')
                    message = message or item.get('Message')
                phone = phone or json_data.get('Phone') or json_data.get('from') or json_data.get('PhoneNumber')
                message = message or json_data.get('Text') or json_data.get('message') or json_data.get('Message')
        except Exception as e:
            print(f"Error checking JSON: {e}")
               
    if phone and message:
        process_incoming_sms(phone, message)
        return "OK", 200
    return "No data found in request", 400

def process_incoming_sms(phone, message):
    admin_phone = "0584555723"
    if phone == admin_phone:
        msg_clean = message.strip().upper()
        if msg_clean in ["LIVE ON", "לייב פועל", "מצב חיבור"]:
            set_live_mode(True)
            from sms_service import send_sms
            send_sms(phone, "מצב LIVE הופעל בהצלחה. המערכת תשלח כעת הודעות אמיתיות.")
            return
        elif msg_clean in ["LIVE OFF", "לייב כבוי", "מצב סימולציה"]:
            set_live_mode(False)
            from sms_service import send_sms
            send_sms(phone, "מצב LIVE כובה. המערכת חזרה למצב סימולציה.")
            return

    conn = get_conn()
    is_postgres = bool(os.environ.get("DATABASE_URL"))
    try:
        if is_postgres:
            count_query = "SELECT COUNT(*) FROM sms_log WHERE phone=? AND direction='out' AND sent_at::date = CURRENT_DATE"
        else:
            count_query = "SELECT COUNT(*) FROM sms_log WHERE phone=? AND direction='out' AND date(sent_at) = date('now')"
        
        daily_count = conn.execute(count_query, (phone,)).fetchone()[0]
        if daily_count >= 30:
            from sms_service import send_sms
            send_sms(phone, "הגעת למגבלת ההודעות היומית (30). המערכת לא תוכל לשלוח או לקבל הודעות נוספות היום.")
            conn.close()
            return
    except Exception as e:
        print(f"Error checking daily limit: {e}")

    try:
        receive_sms(phone, message)
    except Exception as e:
        print(f"Error in receive_sms: {e}")
    
    user = conn.execute("SELECT * FROM users WHERE phone=?", (phone,)).fetchone()
    conn.close()
    if not user:
        handle_unregistered_user(phone, message)
    else:
        from simulation_system import handle_registered_user
        handle_registered_user(phone, user, message)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
