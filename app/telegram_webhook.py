"""Run the Telegram bot INSIDE the web server, using a webhook.

Why: free hosting (Render) runs one web server and may sleep when idle.
A webhook means Telegram sends each message to our server as an HTTPS POST,
which also wakes the server up. Same handlers as bot.py, nothing duplicated.

Security: Telegram signs every webhook call with a secret header that only
we and Telegram know. Calls without the right secret get a 404.
"""
import hashlib
import hmac
import logging

from telegram import Update

from app.config import settings

logger = logging.getLogger("doublecheck")

WEBHOOK_PATH = "/telegram/webhook"
_application = None


def webhook_enabled() -> bool:
    return bool(settings.telegram_bot_token and settings.public_url)


def webhook_secret() -> str:
    """Derived from the bot token, so there's no extra secret to manage.
    Hex output fits Telegram's allowed characters (A-Z, a-z, 0-9, _ and -)."""
    return hashlib.sha256(f"doublecheck-webhook:{settings.telegram_bot_token}".encode()).hexdigest()


async def start() -> None:
    """Start the bot and tell Telegram where to send messages. Never crashes the site."""
    global _application
    try:
        import bot  # reuse exactly the same handlers as `python bot.py`

        application = bot.build_application(settings.telegram_bot_token)
        await application.initialize()
        await application.start()
        await application.bot.set_webhook(
            url=settings.public_url + WEBHOOK_PATH,
            secret_token=webhook_secret(),
            allowed_updates=["message", "callback_query"],
        )
        _application = application
        logger.info("telegram_webhook=on")
    except Exception as exc:
        logger.error("telegram_webhook=failed reason=%s", type(exc).__name__)
        _application = None


async def stop() -> None:
    global _application
    if _application is not None:
        await _application.stop()
        await _application.shutdown()
        _application = None


async def handle(request) -> bool:
    """Queue one update from Telegram. Returns False if the call isn't genuine."""
    if _application is None:
        return False
    received = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not hmac.compare_digest(received, webhook_secret()):
        return False
    try:
        data = await request.json()
    except ValueError:
        return False
    await _application.update_queue.put(Update.de_json(data, _application.bot))
    return True
