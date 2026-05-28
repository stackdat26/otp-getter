import os
import json
import asyncio
from flask import Flask, request
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

app = Flask(__name__)
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')

# ==================== TELEGRAM HANDLERS ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("start command received")
    await update.message.reply_text(
        "🔐 *OTP Testing Bot*\n\nSend /call to start.\n\n*For security testing only.*",
        parse_mode='Markdown'
    )

async def call_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("call command received")
    await update.message.reply_text("📞 Send phone number (e.g., +447123456789)")

# ==================== FLASK WEBHOOK ====================
@app.route("/webhook", methods=['POST'])
def webhook():
    try:
        json_data = request.get_json(force=True)
        print(f"Webhook received: {json.dumps(json_data)[:200]}...")
        
        # Create application and add handlers
        application = Application.builder().token(TELEGRAM_TOKEN).build()
        application.add_handler(CommandHandler('start', start))
        application.add_handler(CommandHandler('call', call_command))
        
        # Process the update
        update = Update.de_json(json_data, application.bot)
        asyncio.run(application.process_update(update))
        
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
    app.run(host='0.0.0.0', port=port)
