from flask import Flask, request, jsonify
import json

app = Flask(__name__)

@app.route('/webhook/inforu', methods=['GET', 'POST'])
def inforu_webhook():
    print("\n" + "="*50)
    print("RECEIVED WEBHOOK REQUEST")
    print(f"Method: {request.method}")
    print(f"Headers: {dict(request.headers)}")
    
    # Check for query parameters (GET or POST)
    args = request.args.to_dict()
    if args:
        print(f"Query Args: {json.dumps(args, indent=2, ensure_ascii=False)}")
    
    # Check for form data (POST)
    form = request.form.to_dict()
    if form:
        print(f"Form Data: {json.dumps(form, indent=2, ensure_ascii=False)}")
    
    # Check for JSON data
    try:
        if request.is_json:
            print(f"JSON Body: {json.dumps(request.json, indent=2, ensure_ascii=False)}")
    except Exception:
        pass

    # Check for raw body (in case of XML or other)
    raw_data = request.data
    if raw_data:
        print(f"Raw Body: {raw_data.decode('utf-8', errors='ignore')[:500]}...")

    print("="*50 + "\n")

    # InforuMobile expects a simple success response, usually XML or just 200 OK.
    # Usually returning "OK" or a small XML like <Response>Success</Response> is enough.
    return "OK - Received", 200

if __name__ == '__main__':
    print("Starting InforuMobile Test Webhook at http://127.0.0.1:5001")
    print("Endpoint: http://127.0.0.1:5001/webhook/inforu")
    app.run(debug=True, port=5001)
