from flask import Flask, render_template, request, jsonify
import os
import json
import threading
import time
from datetime import datetime
from database import get_conn
from sms_service import get_sms_history, receive_sms, set_live_mode, get_live_mode
from simulation_system import handle_unregistered_user, handle_registered_user
from scheduler import run_hour

app = Flask(__name__)

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
        print("🚀 Background Scheduler Started.")
        last_hour = -1
        while True:
            now = datetime.now()
            if now.hour != last_hour:
                print(f"🕒 Scheduler checking for hour {now.hour}...")
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
    
    # Base user query
    # Note: In Postgres, %% is needed to escape % when using %s placeholders
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
    
    # Filter by min_yes in Python for simplicity if needed, or in SQL
    filtered_users = [dict(u) for u in users if u['yes_count'] >= min_yes]
    
    # Get raw tables for the "DB Explorer" part
    # Limit for performance
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
    
    # 1. Users over time (last 30 days)
    if is_postgres:
        users_query = "SELECT date(registered_at) as date, count(*) as count FROM users GROUP BY date(registered_at) ORDER BY date DESC LIMIT 30"
    else:
        users_query = "SELECT date(registered_at) as date, count(*) as count FROM users GROUP BY date(registered_at) ORDER BY date DESC LIMIT 30"
    
    users_data = conn.execute(users_query).fetchall()
    
    # 2. Answers status (Yes/No/No Response)
    # Simple logic: if response_text exists and contains common "Yes" words in Hebrew
    yes_keywords = ['כן', 'נכון', 'אמת', 'יאפ', 'חיובי']
    # We'll fetch last 100 sent questions that have a response
    responses = conn.execute("SELECT response_text FROM sent_questions WHERE responded_at IS NOT NULL ORDER BY responded_at DESC LIMIT 500").fetchall()
    
    yes_count = 0
    no_count = 0
    for r in responses:
        txt = (r['response_text'] or "").strip().lower()
        if any(kw in txt for kw in yes_keywords):
            yes_count += 1
        else:
            no_count += 1
            
    # 3. Age distribution
    age_data = conn.execute("SELECT CASE \
        WHEN age < 13 THEN 'עד 12' \
        WHEN age BETWEEN 13 AND 18 THEN '13-18' \
        WHEN age BETWEEN 19 AND 24 THEN '19-24' \
        WHEN age BETWEEN 25 AND 30 THEN '25-30' \
        WHEN age BETWEEN 31 AND 40 THEN '31-40' \
        WHEN age > 40 THEN '41+' \
        ELSE 'לא צוין' END as age_group, count(*) as count \
        FROM users GROUP BY age_group").fetchall()
    
    # 4. City distribution
    city_data = conn.execute("SELECT COALESCE(city, 'לא צוין') as city, count(*) as count FROM users GROUP BY city ORDER BY count DESC LIMIT 10").fetchall()

    # 5. Subscriptions per Tractate (Total registrations)
    # Using LEFT JOIN and looking for the most recent tractates or using IDs if name is missing
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
    # Prevent caching for the edit templates page
    return response, 200, {
        'Cache-Control': 'no-cache, no-store, must-revalidate',
        'Pragma': 'no-cache',
        'Expires': '0'
    }

@app.route('/api/templates', methods=['GET', 'POST'])
def manage_templates():
    from registration import clear_template_cache
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
        clear_template_cache()
        return jsonify({"status": "success"})
    
    conn = get_conn()
    rows = conn.execute("SELECT key, content FROM sms_templates").fetchall()
    conn.close()
    
    templates = {r["key"]: r["content"] for r in rows}
    
    # If DB is empty, try to load from JSON
    if not templates:
        template_path = os.path.join(os.path.dirname(__file__), 'sms_templates.json')
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
        # Force reload from file to catch external changes
        with open(template_path, 'r', encoding='utf-8') as f:
            json_templates = json.load(f)
    except Exception as e:
        return jsonify({"error": f"Failed to parse JSON: {e}"}), 500
        
    conn = get_conn()
    rows = conn.execute("SELECT key, content FROM sms_templates").fetchall()
    conn.close()
    db_templates = {r["key"]: r["content"] for r in rows}
    
    diff = {
        "new_in_json": [],
        "different": [],
        "only_in_db": []
    }
    
    for key, json_content in json_templates.items():
        if key not in db_templates:
            diff["new_in_json"].append({"key": key, "json_content": json_content})
        else:
            # Simple direct comparison first, fallback to whitespace-insensitive if needed
            if db_templates[key] != json_content:
                diff["different"].append({
                    "key": key, 
                    "json_content": json_content, 
                    "db_content": db_templates[key]
                })
            
    for key in db_templates:
        if key not in json_templates:
            diff["only_in_db"].append(key)
            
    return jsonify(diff)

@app.route('/api/templates/sync', methods=['POST'])
def sync_templates():
    from registration import clear_template_cache
    data = request.json
    keys = data.get('keys', []) # List of keys to sync from JSON to DB
    
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

@app.route('/webhook/inforu', methods=['GET', 'POST'])
def inforu_webhook():
    phone = request.args.get('Phone') or request.form.get('Phone') or request.args.get('from')
    message = request.args.get('Text') or request.form.get('Text') or request.args.get('message')
    if phone and message:
        process_incoming_sms(phone, message)
        return "OK", 200
    return "No data", 400

def process_incoming_sms(phone, message):
    receive_sms(phone, message)
    conn = get_conn()
    user = conn.execute("SELECT * FROM users WHERE phone=?", (phone,)).fetchone()
    conn.close()
    if not user:
        handle_unregistered_user(phone, message)
    else:
        # We reuse the logic from simulation_system to keep it consistent
        from simulation_system import handle_registered_user
        handle_registered_user(phone, user, message)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    print(f"Starting Web Simulation at http://0.0.0.0:{port}")
    app.run(host='0.0.0.0', port=port)
