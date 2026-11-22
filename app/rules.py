"""Layer 1: deterministic keyword/regex rules (English, Hinglish, Hindi).

Rules run FIRST and their result is the floor: the LLM can never lower it.
Every match returns the exact text that matched, so the frontend can
highlight it.

Before matching we remove invisible characters (zero-width spaces etc.) so a
scammer can't hide "O​TP" from the rules. A position map lets us return
the quote exactly as it appears in the ORIGINAL message.
"""
import re
from dataclasses import dataclass

from app.links import link_flags
from app.models import RedFlag

# ---------------------------------------------------------------- invisible chars
INVISIBLE_CHARS = {
    "​", "‌", "‍", "⁠", "﻿", "­", "᠎",
    "‪", "‫", "‬", "‭", "‮",
    "⁦", "⁧", "⁨", "⁩",
}


def is_invisible(ch: str) -> bool:
    # U+E0000..U+E007F are "tag" characters: invisible ASCII look-alikes
    return ch in INVISIBLE_CHARS or 0xE0000 <= ord(ch) <= 0xE007F


def strip_invisible(text: str) -> tuple[str, list[int]]:
    """Return text without invisible chars + map from clean index -> original index."""
    kept, index_map = [], []
    for i, ch in enumerate(text):
        if not is_invisible(ch):
            kept.append(ch)
            index_map.append(i)
    return "".join(kept), index_map


def original_span(text: str, index_map: list[int], start: int, end: int) -> str:
    """Exact original substring for a match found in the cleaned text."""
    return text[index_map[start]: index_map[end - 1] + 1]


# ---------------------------------------------------------------- negation
# Real bank SMS say "Do not share this OTP" / "OTP kisi ko na batayein".
# Those must NOT be flagged as an OTP request.
_NEG_BEFORE = re.compile(
    r"(?:\bnever|\bdo\s+not|\bdon'?t|\bdont|\bnot)\s+(?:[\w']+\s+){0,3}$", re.IGNORECASE
)
_NEG_INSIDE = re.compile(
    r"\b(?:mat|na|nahi|nahin|never|not)\b|(?:^|\s)(?:न|मत|नहीं|ना)(?=\s|$)", re.IGNORECASE
)


def _is_negated(text: str, start: int, end: int) -> bool:
    before = text[max(0, start - 30): start]
    return bool(_NEG_BEFORE.search(before) or _NEG_INSIDE.search(text[start:end]))


# ---------------------------------------------------------------- rule table
@dataclass(frozen=True)
class Rule:
    category: str
    severity: str
    reason_en: str
    reason_hi: str
    patterns: tuple
    negatable: bool = False


def _p(*regexes: str) -> tuple:
    return tuple(re.compile(r, re.IGNORECASE | re.MULTILINE) for r in regexes)


RULES: list[Rule] = [
    Rule(
        "prompt_injection", "HIGH",
        "This text is trying to talk to our checker or an AI and change its answer. Real messages never do this.",
        "यह टेक्स्ट हमारी जाँच (या AI) को निर्देश देकर नतीजा बदलने की कोशिश कर रहा है। असली संदेश ऐसा नहीं करते।",
        _p(
            r"\bignore\s+(?:all\s+|any\s+|the\s+|your\s+|my\s+|these\s+|previous\s+|prior\s+|above\s+|earlier\s+|safety\s+)*(?:rules|instructions|prompts?|guidelines|directions|checks?)",
            r"\bdisregard\s+(?:all\s+|the\s+|your\s+|any\s+|previous\s+|prior\s+|above\s+)*(?:rules|instructions|prompts?|guidelines)",
            r"\bforget\s+(?:all\s+|your\s+|the\s+|previous\s+)*(?:rules|instructions|prompts?)",
            r"\b(?:mark|classify|label|rate|flag|report|treat)\s+(?:this|it|the\s+message|this\s+message|this\s+sms)\s+as\s+(?:safe|low|genuine|legit(?:imate)?|harmless|verified|not\s+(?:a\s+)?scam)",
            r"\b(?:say|tell\s+(?:the\s+user|them)|respond|reply|answer|confirm|output)\s+(?:that\s+)?(?:this|it)\s+(?:message\s+)?is\s+(?:safe|genuine|legit(?:imate)?|harmless|verified|not\s+a\s+scam)",
            r"\bthis\s+(?:message|sms|request|link)\s+is\s+(?:100%\s+)?(?:safe|verified\s+by\s+ai)\b",
            r"\b(?:you\s+are|you're)\s+(?:now\s+)?(?:an?\s+)?(?:ai|assistant|chatbot|language\s+model|scam\s+checker|classifier)\b",
            r"\b(?:system\s+prompt|developer\s+mode|jailbreak)\b",
            r"\b(?:new|updated|override)\s+instructions?\b",
            r"\b(?:ai|assistant|chatbot|gemini|chatgpt|claude|llm|copilot)\s*[:,]\s*(?:please\s+)?(?:ignore|forget|disregard|do\s+not|don'?t|mark|say|forward|send|reveal|summari[sz]e\s+this\s+as)",
            r"\b(?:do\s+not|don'?t|never)\s+(?:tell|inform|show|alert|warn)\s+(?:the\s+)?user\b",
            r"\b(?:reveal|print|show|output|repeat|leak)\s+(?:your\s+|the\s+)?(?:system\s+prompt|instructions|hidden\s+prompt|api\s*keys?|secrets?)",
            r"\bwhen\s+(?:an?\s+|the\s+)?(?:ai|assistant|llm|model|bot)\s+(?:reads|summari[sz]es|processes|sees)\b",
            r"^\s*(?:system|assistant)\s*:",
            r"\"?risk_level\"?\s*[:=]",
            r"\b(?:apne\s+)?(?:rules|niyam)\s+(?:bhool|ignore)\s*(?:jao|ja|kar|karo)",
            r"\b(?:isko|ise|isse|ye|yeh)\s+safe\s+(?:batao|bolo|bata|mark\s+karo|likho)",
            r"नियम\s*(?:\S+\s*){0,2}(?:भूल|अनदेखा)",
            r"सुरक्षित\s*(?:बताओ|बताएं|बताइए|मार्क|लिखो)",
        ),
    ),
    Rule(
        "digital_arrest", "HIGH",
        "Police, CBI, ED or customs never arrest anyone or 'keep you on a video call'. This is the digital arrest script.",
        "पुलिस, CBI, ED या कस्टम्स कभी वीडियो कॉल पर गिरफ्तार नहीं करते। यह 'डिजिटल अरेस्ट' धोखाधड़ी है।",
        _p(
            r"\bdigital\s*arrest",
            r"\bunder\s+(?:house\s+)?arrest\b",
            r"\barrest\s+warrant\b",
            r"\bwarrant\s+(?:against|in\s+your\s+name|has\s+been\s+issued|issued)\b",
            r"\bCBI\b",
            r"\b(?:ED|NCB)\s+(?:officer|office|department|se|from|team)\b",
            r"\benforcement\s+directorate\b",
            r"\bnarcotics\b",
            r"\bmoney\s+laundering\b",
            r"\b(?:stay|remain|be|keep)\s+(?:\w+\s+)?on\s+(?:the\s+)?video\s*call",
            r"\b(?:don'?t|do\s+not)\s+(?:disconnect|cut|end)\s+(?:the\s+|this\s+)?call\b",
            r"\b(?:don'?t|do\s+not)\s+tell\s+(?:anyone|anybody|your\s+family|family)\b",
            r"\b(?:drugs|illegal\s+items|fake\s+passports?)\b",
            r"\b(?:mumbai|delhi|cyber(?:\s*crime)?)\s+police\b",
            r"\bcase\s+(?:is\s+|has\s+been\s+)?(?:registered|filed)\s+against\s+you\b",
            r"\bTRAI\b[^.\n]{0,60}(?:block|disconnect|suspend|band)",
            r"\bgir(?:a|af)?ftar",
            r"गिरफ़?्तार",
            r"डिजिटल\s*अरेस्ट",
            r"वारंट",
            r"सीबीआई",
        ),
    ),
    Rule(
        "remote_access", "HIGH",
        "Screen-share / remote apps (AnyDesk, TeamViewer) let the caller see your OTP and control your bank app.",
        "AnyDesk / TeamViewer जैसे ऐप से ठग आपकी स्क्रीन देखकर OTP और बैंक ऐप चला लेते हैं।",
        _p(
            r"\b(?:any\s*desk|team\s*viewer|rust\s*desk|quick\s*support|ammyy|air\s*droid|ultra\s*viewer)\b",
            r"\bscreen\s*shar(?:e|ing)\b",
            r"\bshare\s+(?:your\s+|the\s+)?screen\b",
            r"\b(?:download|install)\s+(?:this|the|an?|our|my)?\s*(?:app|apk|application)\b",
            r"\.apk\b",
            r"\bapp\s+(?:download|install)\s+(?:karo|karein|kijiye|kar\s+lo|kariye)",
            r"स्क्रीन\s*शेयर",
            r"ऐप\s*(?:डाउनलोड|इंस्टॉल)",
        ),
    ),
    Rule(
        "otp_pin_share", "HIGH",
        "Asking you to tell or share your OTP / PIN. No bank, officer or company ever asks for this.",
        "आपसे OTP / PIN बताने को कहा जा रहा है। कोई बैंक या अफ़सर कभी यह नहीं माँगता।",
        _p(
            r"\b(?:share|tell|give|read\s*out|forward|provide|bata(?:o|iye|yein|ye)?)\s+(?:me\s+|us\s+)?(?:the\s+|your\s+|this\s+|that\s+|received\s+)?(?:\d-digit\s+)?(?:otp|o\.t\.p|cvv|(?:upi\s+|atm\s+)?pin|password)\b",
            r"\bsend\s+(?:me|us)\s+(?:the\s+|your\s+)?(?:otp|pin|cvv)\b",
            r"\bwhat\s+is\s+(?:the|your)\s+(?:otp|pin|cvv)\b",
            r"\b(?:otp|pin|cvv)\s+(?:\S+\s+){0,5}?(?:bata|bolo|bhej|share\s+kar|de\s*do|dijiye)",
            r"(?:ओटीपी|पिन|OTP|PIN)\s*(?:\S+\s*){0,4}?(?:बताएं|बताइए|बताओ|बता\s*दो|बताएँ|भेजें|भेजो|दीजिए)",
        ),
        negatable=True,
    ),
    Rule(
        "upi_collect", "HIGH",
        "Says you'll RECEIVE money if you approve / enter PIN. Approving or entering a PIN always SENDS money.",
        "कहा जा रहा है कि PIN डालने / मंज़ूरी देने से पैसे मिलेंगे। PIN डालने से पैसा हमेशा जाता है, आता नहीं।",
        _p(
            r"\b(?:approve|accept|authori[sz]e|confirm)\s+(?:the\s+|this\s+)?(?:request\s+|payment\s+)?(?:to|and)\s+(?:receive|get|claim)\b",
            r"\b(?:enter|type|put|use)\s+(?:your\s+)?(?:upi\s+)?pin\s+(?:to|and)\s+(?:receive|get|claim|accept)\b",
            r"\bpin\s+(?:\S+\s+){0,4}?to\s+receive\b",
            r"\bscan\s+(?:this\s+|the\s+)?qr(?:\s+code)?\s+(?:to|and)\s+(?:receive|get|claim)\b",
            r"\bpin\s+(?:\S+\s+){0,4}?(?:paise|paisa|money|refund|cashback)\s+(?:\S+\s+){0,2}?(?:milenge|milega|aa\s+jayenge|aayenge)",
            r"\b(?:paise|refund|cashback)\s+(?:\S+\s+){0,3}?(?:pane|lene|receive\s+karne)\s+(?:ke\s+liye|keliye)\s+(?:\S+\s+){0,2}?pin",
            r"पैसे\s*(?:\S+\s*){0,3}?(?:पाने|लेने)\s*के\s*लिए\s*(?:\S+\s*){0,3}?पिन",
            r"पिन\s*(?:\S+\s*){0,4}?पैसे\s*(?:\S+\s*){0,2}?(?:मिलेंगे|आ\s*जाएंगे)",
        ),
        negatable=True,
    ),
    Rule(
        "pin_entry", "MEDIUM",
        "Asks for your UPI PIN. Entering a PIN means money is LEAVING your account.",
        "आपका UPI PIN माँगा जा रहा है। PIN डालने का मतलब है पैसा आपके खाते से जाएगा।",
        _p(
            r"\b(?:enter|type|put|dalo|daalo)\s+(?:your\s+|the\s+)?(?:upi\s+|atm\s+|mpin\s+)?(?:pin|mpin)\b",
            r"\bpin\s+(?:daal|dal|daalo|dalo|daaliye|dalein|enter\s+kar)",
            r"पिन\s*(?:डालें|डालिए|डालो|दर्ज)",
        ),
        negatable=True,
    ),
    Rule(
        "collect_request", "MEDIUM",
        "This is a 'collect request': approving it takes money OUT of your account.",
        "यह 'कलेक्ट रिक्वेस्ट' है: मंज़ूरी देने पर पैसा आपके खाते से कटता है।",
        _p(
            r"\bcollect\s+request\b",
            r"\b(?:has\s+)?request(?:ed|ing)\s+(?:a\s+payment\s+of\s+|money\s+|you\s+(?:to\s+pay\s+)?)?(?:₹|rs\.?\s?|inr\s?)\s*[\d,]+",
            r"\bpayment\s+request\b",
        ),
    ),
    Rule(
        "kyc_expiry", "MEDIUM",
        "'KYC expired / account will be blocked' is a common trick to make you click a link or share details.",
        "'KYC खत्म / खाता बंद होगा' — लिंक खुलवाने या जानकारी लेने की आम चाल है।",
        _p(
            r"\bkyc\b[^.\n]{0,40}?(?:expire[sd]?|expiring|pending|update|suspend|block|incomplete|verify)",
            r"\b(?:account|a/c|card|wallet|sim|number)\s+(?:\S+\s+){0,3}?(?:will\s+be\s+|has\s+been\s+|is\s+|gets\s+)?(?:blocked|suspended|deactivated|frozen|closed|disabled)\b",
            r"\bpan\s*(?:card)?\s+(?:is\s+)?(?:not\s+)?(?:linked|link|update)",
            r"\bkyc\s+(?:update\s+)?kar(?:o|ein|en|iye|lo)",
            r"\b(?:account|khata)\s+band\s+ho\s+(?:jayega|jaega|jaayega)",
            r"केवाईसी",
            r"खाता\s*(?:\S+\s*){0,2}?(?:बंद|ब्लॉक)",
        ),
    ),
    Rule(
        "customs_parcel", "MEDIUM",
        "Fake parcel / customs story. Couriers and customs don't threaten you or ask for money on calls.",
        "नकली पार्सल / कस्टम्स कहानी। कूरियर या कस्टम्स फ़ोन पर धमकी देकर पैसे नहीं माँगते।",
        _p(
            r"\bcustoms?\b",
            r"\bparcel\s+(?:\S+\s+){0,4}?(?:held|seized|stuck|returned|blocked|detained|on\s+hold)\b",
            r"\b(?:fedex|dhl|courier|blue\s*dart)\b\s+(?:\S+\s+){0,6}?(?:seized|held|illegal|customs|drugs)",
            r"\baddress\s+(?:\S+\s+){0,3}?(?:incomplete|invalid)\b",
            r"\bparcel\s+(?:me|mein)\s+(?:drugs|illegal)",
            r"पार्सल",
        ),
    ),
    Rule(
        "electricity_bill", "MEDIUM",
        "Fake electricity disconnection threat. Power companies don't cut supply because of a phone call or SMS.",
        "बिजली काटने की नकली धमकी। बिजली कंपनी फ़ोन या SMS पर ऐसे बिजली नहीं काटती।",
        _p(
            r"\b(?:electricity|power|light|bijli|bijlee)\s+(?:\S+\s+){0,4}?(?:disconnect(?:ed|ion)?|cut|kat|kaat|band)\b",
            r"\b(?:previous|last)\s+month(?:'s)?\s+bill\s+(?:was\s+|is\s+)?not\s+(?:updated|paid)",
            r"\belectricity\s+officer\b",
            r"बिजली\s*(?:\S+\s*){0,3}?(?:कट|काट|बंद)",
        ),
    ),
    Rule(
        "urgency", "LOW",
        "Pressure to act fast. Scammers rush you so you don't stop and check.",
        "जल्दी करने का दबाव। ठग जल्दबाज़ी करवाते हैं ताकि आप जाँच न कर सकें।",
        _p(
            r"\burgent(?:ly)?\b",
            r"\bimmediately\b",
            r"\bwithin\s+\d+\s*(?:minutes?|mins?|hours?|hrs?)\b",
            r"\btonight\b",
            r"\btoday\s+(?:itself|only|before)\b",
            r"\blast\s+(?:chance|warning|reminder)\b",
            r"\bturant\b",
            r"\bjaldi\b",
            r"\babhi\s+ke\s+abhi\b",
            r"\b\d+\s*(?:minute|minutes|mins|ghante)\s+(?:mein|me|ke\s+andar)\b",
            r"तुरंत",
            r"जल्दी",
        ),
    ),
]

_MAX_FLAGS_PER_CATEGORY = 5


def run_rules(text: str, lang: str = "en", only: set[str] | None = None) -> list[RedFlag]:
    """Run every rule (or only some categories) and return red flags with exact quotes."""
    clean, index_map = strip_invisible(text)
    flags: list[RedFlag] = []
    for rule in RULES:
        if only is not None and rule.category not in only:
            continue
        spans: list[tuple[int, int]] = []
        for pattern in rule.patterns:
            for match in pattern.finditer(clean):
                start, end = match.start(), match.end()
                # trim surrounding whitespace so quotes are tidy
                while start < end and clean[start].isspace():
                    start += 1
                while end > start and clean[end - 1].isspace():
                    end -= 1
                if end <= start:
                    continue
                if any(start < e and s < end for s, e in spans):
                    continue  # overlaps a quote we already have for this rule
                if rule.negatable and _is_negated(clean, start, end):
                    continue
                if len(spans) >= _MAX_FLAGS_PER_CATEGORY:
                    break
                spans.append((start, end))
                flags.append(RedFlag(
                    quote=original_span(text, index_map, start, end),
                    reason=rule.reason_hi if lang == "hi" else rule.reason_en,
                    severity=rule.severity,
                    category=rule.category,
                ))
    if only is None or "suspicious_link" in only:
        flags.extend(link_flags(text, lang))
    return flags


def injection_flags(text: str, lang: str = "en") -> list[RedFlag]:
    """Only the prompt-injection rule (used on extra inputs like the sender name)."""
    return run_rules(text, lang, only={"prompt_injection"})
