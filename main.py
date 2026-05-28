import os
import json
from flask import Flask, request

app = Flask(__name__)

@app.route('/', methods=['GET'])
def index():
    return 'OTP Bot is running. Webhook is ready.'

@app.route('/webhook', methods=['POST'])
def webhook():
    # Log the raw request data
    print("=" * 50)
    print("Webhook received a POST request!")
    print(f"Headers: {dict(request.headers)}")
    print(f"Raw body: {request.get_data(as_text=True)}")
    
    # Try to parse JSON
    try:
        data = request.get_json()
        print(f"Parsed JSON: {json.dumps(data, indent=2)[:500]}")
    except Exception as e:
        print(f"JSON parse error: {e}")
    
    print("=" * 50)
    return 'OK', 200

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
