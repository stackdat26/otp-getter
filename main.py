import os
import sys
from flask import Flask, request

app = Flask(__name__)

# Simple test endpoint
@app.route("/", methods=['GET'])
def index():
    return "OTP Bot is running. Webhook is ready."

# Minimal webhook - just echoes what it received
@app.route("/webhook", methods=['POST'])
def webhook():
    print("=" * 50)
    print("Webhook received a POST request!")
    print(f"Headers: {dict(request.headers)}")
    print(f"Body: {request.get_data(as_text=True)}")
    print("=" * 50)
    return "OK", 200

if __name__ == "__main__":
    print("Starting minimal OTP bot...")
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
