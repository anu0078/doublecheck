"""Dodgy-link checks: shorteners, punycode look-alikes, fake bank domains,
raw IP addresses, APK downloads and unusual domain endings."""
import ipaddress
import re
from urllib.parse import urlsplit

from app.models import RedFlag

_COMMON_TLDS = (
    "com|in|net|org|co|io|info|xyz|top|click|online|site|live|buzz|icu|shop|store|link|app|me|cc|"
    "tk|ml|ga|cf|gq|vip|win|loan|work|support|today|ly|gl|gd|gy|to|sbi|bank|pw|rest|cfd|sbs"
)
URL_RE = re.compile(
    r"(?:https?://|www\.)[^\s<>\"'()]+"
    r"|\b(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+(?:" + _COMMON_TLDS + r"|xn--[a-z0-9-]+)\b(?:/[^\s<>\"'()]*)?",
    re.IGNORECASE,
)

SHORTENERS = {
    "bit.ly", "tinyurl.com", "goo.gl", "cutt.ly", "is.gd", "rb.gy", "tiny.cc", "ow.ly",
    "shorturl.at", "rebrand.ly", "s.id", "v.gd", "t.ly", "shorturl.gg", "bitly.com",
}
RISKY_TLDS = {
    "xyz", "top", "click", "online", "site", "live", "buzz", "icu", "shop", "link", "vip",
    "win", "loan", "work", "support", "tk", "ml", "ga", "cf", "gq", "pw", "rest", "cfd", "sbs",
}
BRANDS = [
    "sbi", "hdfc", "icici", "axis", "kotak", "pnb", "canara", "unionbank", "yesbank", "idfc",
    "bankofbaroda", "paytm", "phonepe", "gpay", "googlepay", "npci", "rbi", "uidai", "aadhaar",
    "incometax", "epfo", "bses", "tatapower", "indiapost", "irctc",
]
# Official domains (and their subdomains). ".bank.in" is RBI's restricted domain for banks.
OFFICIAL_SUFFIXES = (
    "bank.in", "gov.in", "nic.in", "sbi.co.in", "onlinesbi.sbi", "sbi", "hdfcbank.com",
    "icicibank.com", "axisbank.com", "kotak.com", "pnbindia.in", "canarabank.com",
    "unionbankofindia.co.in", "yesbank.in", "idfcfirstbank.com", "bankofbaroda.in", "paytm.com",
    "phonepe.com", "google.com", "npci.org.in", "rbi.org.in", "bsesdelhi.com",
    "tatapower-ddl.com", "tatapower.com", "irctc.co.in",
)

_REASONS = {
    "apk": ("Link downloads an Android app (APK). Such apps can take over your phone and read your OTPs.",
            "यह लिंक एक ऐप (APK) डाउनलोड करता है जो आपका फ़ोन और OTP चुरा सकता है।"),
    "punycode": ("Web address uses look-alike letters (punycode) to imitate a real site.",
                 "वेब पता असली साइट जैसे दिखने वाले नकली अक्षरों का इस्तेमाल करता है।"),
    "fake_brand": ("Pretends to be '{brand}' but this is not its official website.",
                   "यह '{brand}' होने का दिखावा करता है, लेकिन यह उसकी आधिकारिक वेबसाइट नहीं है।"),
    "shortener": ("Shortened link hides the real website it opens.",
                  "छोटा (शॉर्ट) लिंक असली वेबसाइट छिपा देता है।"),
    "ip": ("Link goes to a bare number address, not a real company website.",
           "लिंक किसी असली कंपनी की वेबसाइट पर नहीं, सीधे नंबर वाले पते पर जाता है।"),
    "risky_tld": ("Unusual web address ending (.{tld}) often used in scams.",
                  "असामान्य वेब पता (.{tld}) — धोखाधड़ी में अक्सर इस्तेमाल होता है।"),
}
_SEVERITY = {"apk": "HIGH", "punycode": "HIGH", "fake_brand": "HIGH",
             "shortener": "MEDIUM", "ip": "MEDIUM", "risky_tld": "MEDIUM"}


def _is_official(host: str) -> bool:
    return any(host == s or host.endswith("." + s) for s in OFFICIAL_SUFFIXES)


def _check_url(raw: str) -> tuple[str, dict] | None:
    """Return (issue_key, format_args) for the worst problem with this URL, or None."""
    candidate = raw if re.match(r"https?://", raw, re.IGNORECASE) else "http://" + raw
    try:
        parts = urlsplit(candidate)
        host = (parts.hostname or "").lower().rstrip(".")
    except ValueError:
        return None
    if not host:
        return None
    path = (parts.path or "").lower()
    if path.endswith(".apk"):
        return "apk", {}
    if "xn--" in host:
        return "punycode", {}
    if not _is_official(host):
        tokens = re.split(r"[.\-_]", host)
        for brand in BRANDS:
            # short brands must START a word ("sbi-kyc" yes, "carbide" no)
            if any(t == brand or t.startswith(brand) or (len(brand) >= 5 and brand in t) for t in tokens):
                return "fake_brand", {"brand": brand.upper()}
    if host in SHORTENERS:
        return "shortener", {}
    try:
        ipaddress.ip_address(host)
        return "ip", {}
    except ValueError:
        pass
    tld = host.rsplit(".", 1)[-1]
    if tld in RISKY_TLDS:
        return "risky_tld", {"tld": tld}
    return None


def link_flags(text: str, lang: str = "en") -> list[RedFlag]:
    # local import avoids a circular import (rules.py imports this module)
    from app.rules import original_span, strip_invisible

    clean, index_map = strip_invisible(text)
    flags: list[RedFlag] = []
    seen: set[str] = set()
    for match in URL_RE.finditer(clean):
        start, end = match.start(), match.end()
        while end > start and clean[end - 1] in ".,;:!?)]}'\"":
            end -= 1
        raw = clean[start:end]
        if not raw or raw.lower() in seen:
            continue
        seen.add(raw.lower())
        result = _check_url(raw)
        if result is None:
            continue
        key, args = result
        en, hi = _REASONS[key]
        flags.append(RedFlag(
            quote=original_span(text, index_map, start, end),
            reason=(hi if lang == "hi" else en).format(**args),
            severity=_SEVERITY[key],
            category="suspicious_link",
        ))
    return flags
