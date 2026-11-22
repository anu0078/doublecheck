"""Telegram bot: consent-first linking, child never sees the message, reply format."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import bot
from app.bot_text import format_bot_reply
from app.family_store import FamilyStore, PendingCodes
from app.services import run_pay_guard
from tests.conftest import run

PARENT, CHILD, STRANGER = 111, 222, 333
SCAM = "Enter your UPI PIN to receive Rs 2000 refund. Account 99887766 details attached."


# ---------------------------------------------------------------- store + codes
def test_store_keeps_only_ids_links_and_language(tmp_path):
    store = FamilyStore(str(tmp_path / "f.db"))
    store.set_lang(PARENT, "hi")
    store.add_link(PARENT, CHILD)
    assert store.get_lang(PARENT) == "hi"
    assert store.get_lang(CHILD) == "en"
    assert store.get_children(PARENT) == [CHILD]
    cols = {r[1] for r in store._run("PRAGMA table_info(users)")} | \
           {r[1] for r in store._run("PRAGMA table_info(family_links)")}
    assert cols == {"chat_id", "lang", "parent_chat_id", "child_chat_id"}


def test_stopfamily_from_either_side(tmp_path):
    store = FamilyStore(str(tmp_path / "f.db"))
    store.add_link(PARENT, CHILD)
    assert store.remove_links_for(CHILD) == [PARENT]
    assert store.get_children(PARENT) == []
    store.add_link(PARENT, CHILD)
    assert store.remove_links_for(PARENT) == [CHILD]


def test_codes_single_use_expiry_and_self():
    now = [0.0]
    codes = PendingCodes(ttl_seconds=900, clock=lambda: now[0])
    code = codes.create(PARENT)
    assert len(code) == 6
    assert codes.redeem(code, PARENT) == ("self", None)
    assert codes.redeem(code.lower(), CHILD) == ("ok", PARENT)
    assert codes.redeem(code, CHILD) == ("invalid", None)          # single use

    code = codes.create(PARENT)
    now[0] = 901
    assert codes.redeem(code, CHILD) == ("invalid", None)          # expired after 15 min


def test_new_code_replaces_old():
    codes = PendingCodes()
    old = codes.create(PARENT)
    new = codes.create(PARENT)
    assert codes.redeem(old, CHILD) == ("invalid", None)
    assert codes.redeem(new, CHILD) == ("ok", PARENT)


# ---------------------------------------------------------------- reply format
@pytest.mark.parametrize("lang", ["en", "hi"])
def test_reply_is_4_to_6_short_lines(lang):
    for text in [SCAM, "Rs 500 credited to your account from ramesh@oksbi"]:
        result = run(run_pay_guard(text, None, None, lang)).response
        reply = format_bot_reply(result, lang)
        lines = reply.split("\n")
        assert 4 <= len(lines) <= 6, reply
        assert all(len(line) <= 100 for line in lines)
        assert "SAFE" not in reply.upper().split()


def test_danger_reply_has_helpline():
    result = run(run_pay_guard(SCAM, None, None, "en")).response
    reply = format_bot_reply(result, "en")
    assert reply.startswith("🔴 DANGER")
    assert "1930" in reply and "cybercrime.gov.in" in reply
    assert "YOU ARE SENDING ₹2,000 — NOT RECEIVING." in reply


# ---------------------------------------------------------------- handlers (fake Telegram)
class FakeBot:
    def __init__(self):
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, chat_id, text, **kwargs):
        self.sent.append((chat_id, text))

    async def get_chat(self, chat_id):
        return SimpleNamespace(first_name="Sunita")


def make_update(chat_id, first_name="User", text=None):
    message = SimpleNamespace(text=text, caption=None, reply_text=AsyncMock())
    return SimpleNamespace(
        effective_chat=SimpleNamespace(id=chat_id),
        effective_user=SimpleNamespace(first_name=first_name),
        message=message,
    )


@pytest.fixture
def fresh_bot(tmp_path, monkeypatch):
    from app.ratelimit import SlidingWindowRateLimiter
    monkeypatch.setattr(bot, "store", FamilyStore(str(tmp_path / "bot.db")))
    monkeypatch.setattr(bot, "codes", PendingCodes())
    monkeypatch.setattr(bot, "link_limiter", SlidingWindowRateLimiter(5, 900))
    monkeypatch.setattr(bot, "message_limiter", SlidingWindowRateLimiter(30, 60))
    return SimpleNamespace(bot=FakeBot(), args=[])


def test_no_alert_without_consent(fresh_bot):
    update = make_update(PARENT, "Sunita", SCAM)
    run(bot.check_message(update, fresh_bot))
    update.message.reply_text.assert_awaited()
    assert fresh_bot.bot.sent == []          # nobody else was told anything


def test_full_consent_flow_and_child_sees_only_alert(fresh_bot):
    # parent: /family -> sees consent text with buttons
    update = make_update(PARENT, "Sunita")
    run(bot.family(update, fresh_bot))
    consent_text = update.message.reply_text.await_args.args[0]
    assert "NEVER see your message" in consent_text
    assert "reply_markup" in update.message.reply_text.await_args.kwargs

    # parent taps "Yes, I agree" -> code is created only now
    query = SimpleNamespace(data="family:yes", answer=AsyncMock(), edit_message_text=AsyncMock(),
                            message=SimpleNamespace(chat=SimpleNamespace(id=PARENT)))
    run(bot.family_answer(SimpleNamespace(callback_query=query), fresh_bot))
    code_text = query.edit_message_text.await_args.args[0]
    code = code_text.split("/link ")[1].strip()

    # child: /link CODE
    fresh_bot.args = [code]
    child_update = make_update(CHILD, "Ravi")
    run(bot.link(child_update, fresh_bot))
    assert bot.store.get_children(PARENT) == [CHILD]

    # parent forwards a scam -> child gets ONLY the one-line alert
    fresh_bot.bot.sent.clear()
    run(bot.check_message(make_update(PARENT, "Sunita", SCAM), fresh_bot))
    assert len(fresh_bot.bot.sent) == 1
    to, alert = fresh_bot.bot.sent[0]
    assert to == CHILD
    assert alert == "⚠️ Sunita received a likely scam (Fake 'receive money' UPI request). Maybe give them a call."
    assert "99887766" not in alert and "Rs 2000" not in alert

    # /stopfamily from the child removes it
    run(bot.stopfamily(make_update(CHILD, "Ravi"), fresh_bot))
    assert bot.store.get_children(PARENT) == []


def test_declining_creates_no_code(fresh_bot):
    query = SimpleNamespace(data="family:no", answer=AsyncMock(), edit_message_text=AsyncMock(),
                            message=SimpleNamespace(chat=SimpleNamespace(id=PARENT)))
    run(bot.family_answer(SimpleNamespace(callback_query=query), fresh_bot))
    assert bot.codes._codes == {}


def test_wrong_code_and_guessing_limit(fresh_bot):
    fresh_bot.args = ["ZZZZZZ"]
    for _ in range(5):
        update = make_update(STRANGER)
        run(bot.link(update, fresh_bot))
        assert "wrong or expired" in update.message.reply_text.await_args.args[0]
    update = make_update(STRANGER)
    run(bot.link(update, fresh_bot))
    assert "Too many tries" in update.message.reply_text.await_args.args[0]


def test_language_switch(fresh_bot):
    run(bot.hindi(make_update(PARENT), fresh_bot))
    update = make_update(PARENT, "Sunita", SCAM)
    run(bot.check_message(update, fresh_bot))
    assert update.message.reply_text.await_args.args[0].startswith("🔴 खतरा")


def test_screenshot_asks_for_text(fresh_bot):
    update = make_update(PARENT)
    run(bot.photo(update, fresh_bot))
    assert "paste" in update.message.reply_text.await_args.args[0]


def test_application_builds():
    application = bot.build_application("123456:TEST-TOKEN-NOT-REAL")
    assert len(application.handlers[0]) == 9
