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
from database import init_db, seed_tractates
try:
    init_db()
    seed_tractates()
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
def index():
    return render_template('index.html')

@app.route('/edit-templates')
def edit_templates():
    return render_template('edit_templates.html')

@app.route('/api/templates', methods=['GET', 'POST'])
def manage_templates():
    template_path = os.path.join(os.path.dirname(__file__), 'sms_templates.json')
    if request.method == 'POST':
        data = request.json
        with open(template_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        return jsonify({"status": "success"})
    
    if os.path.exists(template_path):
        with open(template_path, 'r', encoding='utf-8') as f:
            templates = json.load(f)
    else:
        templates = {}
    return jsonify(templates)

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
        handle_registered_user(phone, user, message)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    print(f"Starting Web Simulation at http://0.0.0.0:{port}")
    app.run(host='0.0.0.0', port=port)
