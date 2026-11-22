"""DoubleCheck Telegram bot for families.

Run:  python bot.py      (needs TELEGRAM_BOT_TOKEN in .env)

- Uses the SAME engine as the API (app.services.run_pay_guard).
- Works only in private chats, so alerts never leak into groups.
- Family alerts are opt-in by the PARENT:
    parent /family -> reads exactly what the child will see -> taps "Yes, I agree"
    -> gets a 6-character code (15 minutes, one use) -> child sends /link CODE
- The child only ever gets a one-line alert, never the message itself.
- /stopfamily from either side removes the link.
"""
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters,
)

from app import llm, services
from app import messages as M
from app.bot_text import BOT_TEXT, child_alert_text, format_bot_reply
from app.config import MAX_TEXT_CHARS, settings
from app.family_store import CODE_TTL_SECONDS, FamilyStore, PendingCodes
from app.ratelimit import SlidingWindowRateLimiter

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
# httpx logs full request URLs at INFO, and Telegram URLs contain the bot token.
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("doublecheck.bot")

store = FamilyStore(settings.family_db_path)
codes = PendingCodes()
message_limiter = SlidingWindowRateLimiter(limit=30, window_seconds=60)        # per chat
link_limiter = SlidingWindowRateLimiter(limit=5, window_seconds=CODE_TTL_SECONDS)  # stops code guessing

PRIVATE = filters.ChatType.PRIVATE
GENERIC_SCAM_LABEL = {"en": "suspicious message", "hi": "संदिग्ध संदेश"}


def t(chat_id: int, key: str) -> str:
    return BOT_TEXT[store.get_lang(chat_id)][key]


# ---------------------------------------------------------------- basic commands
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(t(update.effective_chat.id, "start"))


async def hindi(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    store.set_lang(update.effective_chat.id, "hi")
    await update.message.reply_text(BOT_TEXT["hi"]["lang_set"])


async def english(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    store.set_lang(update.effective_chat.id, "en")
    await update.message.reply_text(BOT_TEXT["en"]["lang_set"])


# ---------------------------------------------------------------- family consent flow
async def family(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    lang = store.get_lang(chat_id)
    name = update.effective_user.first_name or BOT_TEXT[lang]["someone"]
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton(BOT_TEXT[lang]["yes_button"], callback_data="family:yes")],
        [InlineKeyboardButton(BOT_TEXT[lang]["no_button"], callback_data="family:no")],
    ])
    await update.message.reply_text(BOT_TEXT[lang]["family_consent"].format(name=name),
                                    reply_markup=buttons)


async def family_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat.id
    lang = store.get_lang(chat_id)
    if query.data == "family:yes":
        code = codes.create(chat_id)        # code exists only AFTER the parent agreed
        await query.edit_message_text(BOT_TEXT[lang]["family_code"].format(code=code))
    else:
        codes.cancel_for(chat_id)
        await query.edit_message_text(BOT_TEXT[lang]["family_declined"])


async def link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    child_id = update.effective_chat.id
    lang = store.get_lang(child_id)
    if not context.args:
        await update.message.reply_text(BOT_TEXT[lang]["link_usage"])
        return
    if not link_limiter.allow(str(child_id)):
        await update.message.reply_text(BOT_TEXT[lang]["link_too_many"])
        return

    status, parent_id = codes.redeem(context.args[0], child_id)
    if status == "self":
        await update.message.reply_text(BOT_TEXT[lang]["link_self"])
        return
    if status != "ok":
        await update.message.reply_text(BOT_TEXT[lang]["link_invalid"])
        return

    store.add_link(parent_id, child_id)
    parent_lang = store.get_lang(parent_id)
    parent_name = BOT_TEXT[lang]["someone"]
    try:
        parent_chat = await context.bot.get_chat(parent_id)
        parent_name = parent_chat.first_name or parent_name
        child_name = update.effective_user.first_name or BOT_TEXT[parent_lang]["someone"]
        await context.bot.send_message(
            parent_id, BOT_TEXT[parent_lang]["link_ok_parent"].format(name=child_name))
    except Exception as exc:
        logger.warning("notify_parent_failed reason=%s", type(exc).__name__)
    await update.message.reply_text(BOT_TEXT[lang]["link_ok_child"].format(name=parent_name))


async def stopfamily(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    codes.cancel_for(chat_id)
    others = store.remove_links_for(chat_id)
    if not others:
        await update.message.reply_text(t(chat_id, "nothing_to_stop"))
        return
    for other in others:
        try:
            await context.bot.send_message(other, t(other, "stopped_other"))
        except Exception as exc:
            logger.warning("notify_unlink_failed reason=%s", type(exc).__name__)
    await update.message.reply_text(t(chat_id, "stopped"))


# ---------------------------------------------------------------- checking messages
async def check_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    lang = store.get_lang(chat_id)
    if not message_limiter.allow(str(chat_id)):
        await update.message.reply_text(BOT_TEXT[lang]["too_many"])
        return

    text = (update.message.text or update.message.caption or "")[:MAX_TEXT_CHARS]
    if not text.strip():
        await update.message.reply_text(BOT_TEXT[lang]["paste_text"])
        return

    outcome = await services.run_pay_guard(text, None, None, lang)
    result = outcome.response
    await update.message.reply_text(format_bot_reply(result, lang))
    logger.info("bot_check risk=%s engine=%s", result.risk_level, result.engine)  # no text logged

    if result.risk_level == "DANGEROUS":
        await alert_family(context, chat_id, update.effective_user.first_name, outcome.primary_category)


async def alert_family(context: ContextTypes.DEFAULT_TYPE, parent_id: int,
                       parent_name: str | None, category: str | None) -> None:
    """Quietly tell linked family members. Never includes the message itself."""
    for child_id in store.get_children(parent_id):
        child_lang = store.get_lang(child_id)
        script = M.label(category, child_lang) or GENERIC_SCAM_LABEL[child_lang]
        try:
            await context.bot.send_message(child_id, child_alert_text(parent_name, script, child_lang))
        except Exception as exc:   # e.g. the child blocked the bot
            logger.warning("family_alert_failed reason=%s", type(exc).__name__)


async def photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(t(update.effective_chat.id, "paste_text"))


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("bot_error reason=%s", type(context.error).__name__)


# ---------------------------------------------------------------- wiring
def build_application(token: str) -> Application:
    application = Application.builder().token(token).build()
    application.add_handler(CommandHandler("start", start, filters=PRIVATE))
    application.add_handler(CommandHandler("hindi", hindi, filters=PRIVATE))
    application.add_handler(CommandHandler("english", english, filters=PRIVATE))
    application.add_handler(CommandHandler("family", family, filters=PRIVATE))
    application.add_handler(CommandHandler("link", link, filters=PRIVATE))
    application.add_handler(CommandHandler("stopfamily", stopfamily, filters=PRIVATE))
    application.add_handler(CallbackQueryHandler(family_answer, pattern=r"^family:(yes|no)$"))
    application.add_handler(MessageHandler(PRIVATE & (filters.PHOTO | filters.Document.IMAGE) & ~filters.CAPTION, photo))
    application.add_handler(MessageHandler(PRIVATE & (filters.TEXT | filters.CAPTION) & ~filters.COMMAND, check_message))
    application.add_error_handler(on_error)
    return application


def main() -> None:
    if not settings.telegram_bot_token:
        raise SystemExit("TELEGRAM_BOT_TOKEN is missing. Add it to your .env file (see README).")
    logger.info("DoubleCheck bot starting (llm_available=%s)", llm.is_available())
    build_application(settings.telegram_bot_token).run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
