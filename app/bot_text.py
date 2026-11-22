"""Text and reply formatting for the Telegram bot (kept separate so it's testable)."""
from app.schemas import PayGuardResult

BOT_TEXT = {
    "en": {
        "start": (
            "👋 I'm DoubleCheck.\n"
            "Forward me any suspicious SMS, WhatsApp message or UPI request.\n"
            "I'll tell you in simple words if it looks like a scam.\n\n"
            "🔒 I don't save your messages.\n\n"
            "/hindi — हिंदी में जवाब\n"
            "/family — let a family member get an alert if you get a scam\n"
            "/stopfamily — turn family alerts off"
        ),
        "lang_set": "✅ I'll reply in English now.",
        "paste_text": "📷 I can't read pictures yet. Please copy the message text and paste it here.",
        "too_many": "⏳ Too many messages. Please wait a minute.",
        "danger": "🔴 DANGER — this looks like a scam",
        "suspicious": "🟠 CAREFUL — this looks suspicious",
        "low": "🟢 No known scam pattern found.",
        "low_tip": "Still, never share your OTP or PIN.",
        "helpline": "📞 Help: call 1930 or visit cybercrime.gov.in",
        "not_saved": "🔒 Not saved.",
        "family_consent": (
            "👨‍👩‍👧 Family alerts\n\n"
            "If you agree, a family member (for example your son or daughter) will get a short alert "
            "when a message you send me looks DANGEROUS.\n\n"
            "They will ONLY see:\n"
            "\"⚠️ {name} received a likely scam (type of scam). Maybe give them a call.\"\n\n"
            "They will NEVER see your message. Nothing is saved.\n"
            "You can stop anytime with /stopfamily.\n\n"
            "Do you agree?"
        ),
        "yes_button": "✅ Yes, I agree",
        "no_button": "❌ No",
        "family_declined": "Okay, nothing was set up. No one will get alerts.",
        "family_code": (
            "✅ Thank you. Your code is: {code}\n"
            "It works for 15 minutes, one time only.\n\n"
            "Ask your family member to open this bot and send:\n"
            "/link {code}"
        ),
        "link_usage": "Please send the code like this: /link ABC123",
        "link_invalid": "❌ That code is wrong or expired. Ask for a new one (/family).",
        "link_self": "❌ You can't link to yourself. Send this code to a family member.",
        "link_too_many": "⏳ Too many tries. Please wait 15 minutes.",
        "link_ok_child": (
            "✅ Linked with {name}.\n"
            "You'll get a short alert only if they receive a likely scam. "
            "You will never see their messages.\n"
            "Stop anytime: /stopfamily"
        ),
        "link_ok_parent": "✅ {name} is now linked for family alerts. Stop anytime: /stopfamily",
        "stopped": "✅ Family alerts are off.",
        "stopped_other": "ℹ️ A family alert link with you was removed.",
        "nothing_to_stop": "You don't have any family alerts set up.",
        "child_alert": "⚠️ {name} received a likely scam ({script}). Maybe give them a call.",
        "someone": "Your family member",
    },
    "hi": {
        "start": (
            "👋 मैं DoubleCheck हूँ।\n"
            "कोई भी शक वाला SMS, WhatsApp संदेश या UPI रिक्वेस्ट मुझे भेजें।\n"
            "मैं आसान शब्दों में बताऊँगा कि यह धोखाधड़ी लगती है या नहीं।\n\n"
            "🔒 मैं आपके संदेश सेव नहीं करता।\n\n"
            "/english — reply in English\n"
            "/family — धोखाधड़ी आने पर परिवार के सदस्य को अलर्ट\n"
            "/stopfamily — फ़ैमिली अलर्ट बंद करें"
        ),
        "lang_set": "✅ अब मैं हिंदी में जवाब दूँगा।",
        "paste_text": "📷 मैं अभी फ़ोटो नहीं पढ़ सकता। कृपया संदेश का टेक्स्ट कॉपी करके यहाँ भेजें।",
        "too_many": "⏳ बहुत ज़्यादा संदेश। कृपया एक मिनट रुकें।",
        "danger": "🔴 खतरा — यह धोखाधड़ी लगती है",
        "suspicious": "🟠 सावधान — यह संदिग्ध लगता है",
        "low": "🟢 कोई जाना-पहचाना धोखाधड़ी पैटर्न नहीं मिला।",
        "low_tip": "फिर भी, OTP या PIN कभी किसी को न बताएं।",
        "helpline": "📞 मदद: 1930 पर कॉल करें या cybercrime.gov.in पर जाएँ",
        "not_saved": "🔒 सेव नहीं किया गया।",
        "family_consent": (
            "👨‍👩‍👧 फ़ैमिली अलर्ट\n\n"
            "अगर आप सहमत हैं, तो आपके परिवार के एक सदस्य (जैसे बेटा या बेटी) को छोटा अलर्ट मिलेगा "
            "जब आपका भेजा कोई संदेश खतरनाक लगे।\n\n"
            "उन्हें सिर्फ़ यह दिखेगा:\n"
            "\"⚠️ {name} को एक संभावित धोखाधड़ी संदेश मिला (धोखाधड़ी का प्रकार)। एक बार उन्हें फ़ोन कर लें।\"\n\n"
            "उन्हें आपका संदेश कभी नहीं दिखेगा। कुछ भी सेव नहीं होता।\n"
            "आप कभी भी /stopfamily से बंद कर सकते हैं।\n\n"
            "क्या आप सहमत हैं?"
        ),
        "yes_button": "✅ हाँ, मैं सहमत हूँ",
        "no_button": "❌ नहीं",
        "family_declined": "ठीक है, कुछ भी चालू नहीं किया गया। किसी को अलर्ट नहीं जाएगा।",
        "family_code": (
            "✅ धन्यवाद। आपका कोड है: {code}\n"
            "यह 15 मिनट तक, सिर्फ़ एक बार काम करेगा।\n\n"
            "अपने परिवार के सदस्य से कहें कि यह बॉट खोलकर भेजें:\n"
            "/link {code}"
        ),
        "link_usage": "कृपया कोड ऐसे भेजें: /link ABC123",
        "link_invalid": "❌ यह कोड गलत है या खत्म हो गया। नया कोड माँगें (/family)।",
        "link_self": "❌ आप खुद से लिंक नहीं कर सकते। यह कोड परिवार के सदस्य को भेजें।",
        "link_too_many": "⏳ बहुत ज़्यादा कोशिशें। कृपया 15 मिनट रुकें।",
        "link_ok_child": (
            "✅ {name} से लिंक हो गया।\n"
            "उन्हें संभावित धोखाधड़ी संदेश मिलने पर ही आपको छोटा अलर्ट मिलेगा। "
            "आपको उनके संदेश कभी नहीं दिखेंगे।\n"
            "बंद करने के लिए: /stopfamily"
        ),
        "link_ok_parent": "✅ {name} फ़ैमिली अलर्ट के लिए लिंक हो गए। बंद करने के लिए: /stopfamily",
        "stopped": "✅ फ़ैमिली अलर्ट बंद हो गए।",
        "stopped_other": "ℹ️ आपके साथ एक फ़ैमिली अलर्ट लिंक हटा दिया गया।",
        "nothing_to_stop": "आपके लिए कोई फ़ैमिली अलर्ट चालू नहीं है।",
        "child_alert": "⚠️ {name} को एक संभावित धोखाधड़ी संदेश मिला ({script})। एक बार उन्हें फ़ोन कर लें।",
        "someone": "आपके परिवार के सदस्य",
    },
}


def _short(text: str, limit: int = 90) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + "…"


def format_bot_reply(result: PayGuardResult, lang: str) -> str:
    """4-6 short lines an older person can read easily."""
    t = BOT_TEXT[lang]
    lines: list[str] = []
    if result.risk_level == "LOW":
        lines += [t["low"], _short(result.headline), t["low_tip"]]
    else:
        lines.append(t["danger"] if result.risk_level == "DANGEROUS" else t["suspicious"])
        lines.append(_short(result.headline))
        if result.red_flags:
            lines.append("• " + _short(result.red_flags[0].reason))
        if result.next_steps:
            lines.append("• " + _short(result.next_steps[0]))
        lines.append(t["helpline"])
    lines.append(t["not_saved"])
    return "\n".join(lines[:6])


def child_alert_text(parent_name: str | None, script_label: str, lang: str) -> str:
    t = BOT_TEXT[lang]
    return t["child_alert"].format(name=parent_name or t["someone"], script=script_label)
