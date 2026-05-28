import os
import json
import requests
from flask import Flask, request

app = Flask(__name__)
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
BASE_URL = "https://otp-getter.onrender.com"

# Helper function to send Telegram messages
def send_telegram_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    try:
        response = requests.post(url, json=payload)
        print(f"Sent message to {chat_id}: {response.status_code}")
    except Exception as e:
        print(f"Error sending message: {e}")

# ==================== FLASK WEBHOOK ====================
@app.route("/webhook", methods=['POST'])
def webhook():
    try:
        # Get the update from Telegram
        update = request.get_json(force=True)
        print(f"Webhook received: {json.dumps(update)[:200]}...")
        
        # Extract message details
        message = update.get('message', {})
        chat = message.get('chat', {})
        chat_id = chat.get('id')
        text = message.get('text', '')
        
        if not chat_id:
            print("No chat_id found in update")
            return "ok", 200
        
        # Handle commands
        if text == '/start':
            print(f"Handling /start for chat {chat_id}")
            send_telegram_message(chat_id, "🔐 *OTP Testing Bot*\n\nSend /call to start.\n\n*For security testing only.*")
        elif text == '/call':
            print(f"Handling /call for chat {chat_id}")
            send_telegram_message(chat_id, "📞 Send phone number (e.g., +447123456789)")
        else:
            print(f"Unknown command: {text}")
        
        return "ok", 200
        
    except Exception as e:
        print(f"Error in webhook: {e}")
        return "error", 500

@app.route("/", methods=['GET'])
def index():
    return "OTP Bot is running."

@app.route("/health", methods=['GET'])
def health():
    return "OK", 200

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    print(f"Starting bot on port {port}")
    print(f"Bot token configured: {bool(TELEGRAM_TOKEN)}")
    app.run(host='0.0.0.0', port=port)
