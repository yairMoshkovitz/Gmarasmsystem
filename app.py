from flask import Flask, render_template, request, jsonify
import os
from database import get_conn
from sms_service import get_sms_history, receive_sms
from simulation_system import handle_unregistered_user, handle_registered_user

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

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
    
    # 1. Log the incoming message (System receiving it)
    receive_sms(phone, message)
    
    # 2. Process logic (identical to simulation_system.py)
    conn = get_conn()
    user = conn.execute("SELECT * FROM users WHERE phone=?", (phone,)).fetchone()
    conn.close()
    
    if not user:
        handle_unregistered_user(phone, message)
    else:
        handle_registered_user(phone, user, message)
        
    return jsonify({"status": "ok"})

if __name__ == '__main__':
    # Initialize DB and other things if needed (already handled by other scripts usually)
    print("Starting Web Simulation at http://127.0.0.1:5000")
    app.run(debug=True, port=5000)
