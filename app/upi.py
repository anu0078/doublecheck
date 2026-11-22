"""UPI-specific logic, all in plain code (the LLM decides none of this):

- HARD RULE: if anything asks for your UPI PIN (or to approve a request),
  money is LEAVING your account. You never need a PIN to receive money.
- Which way the money moves (SENDING / RECEIVING / UNKNOWN)
- The amount, formatted the Indian way (₹1,00,000)
- Sender name vs UPI ID mismatch ("SBI Refund" paying from rahul8823@ybl)
"""
import re

from app import messages as M
from app.models import RedFlag
from app.rules import strip_invisible

SENDING = "SENDING"
RECEIVING = "RECEIVING"
UNKNOWN = "UNKNOWN"

# A UPI ID is name@handle with no ".com" after it (that would be an email).
UPI_ID_RE = re.compile(r"\b[a-zA-Z0-9][a-zA-Z0-9._-]{1,254}@[a-zA-Z][a-zA-Z0-9]{1,63}\b(?!\.[a-zA-Z])")

AMOUNT_RE = re.compile(
    r"(?:₹|\brs\.?|\binr\b|\brupees?\b)\s*([\d,]+(?:\.\d{1,2})?)"
    r"|([\d,]+(?:\.\d{1,2})?)\s*(?:rupees?\b|rs\b|रुपये|रुपए|रु\.?)",
    re.IGNORECASE,
)
_SENT_RE = re.compile(r"\bdebited\b|\bsent\s+(?:₹|rs)|\bpaid\s+(?:₹|rs)|\bwithdrawn\b|डेबिट|कटे|भेजे\s*गए", re.IGNORECASE)
_RECEIVED_RE = re.compile(r"\bcredited\b|\breceived\s+(?:₹|rs\.?|inr)|\bdeposited\b|क्रेडिट|जमा\s*(?:हुए|किए)", re.IGNORECASE)
_CLAIMS_RECEIVE_RE = re.compile(
    r"\breceiv|\brefund|\bcashback|\bprize|\blottery|\bwon\b|\breward|\bmilenge|\bmilega|पाने|मिलेंगे|रिफंड|कैशबैक|इनाम",
    re.IGNORECASE,
)

_PIN_CATEGORIES = {"pin_entry", "upi_collect", "collect_request"}

# Words in a sender name that claim to be an organisation, not a person
ORG_BRANDS = ["sbi", "hdfc", "icici", "axis", "kotak", "pnb", "canara", "rbi", "npci", "paytm",
              "phonepe", "gpay", "google", "amazon", "flipkart", "airtel", "jio", "lic", "irctc"]
ORG_WORDS = ["bank", "refund", "cashback", "customer care", "support", "helpdesk", "govt",
             "government", "income tax", "electricity", "bijli", "police", "cbi", "customs",
             "lottery", "kbc", "official", "department"]


def format_inr(amount: float) -> str:
    """2000 -> ₹2,000 ; 150000 -> ₹1,50,000 ; 99.5 -> ₹99.50"""
    rupees = int(amount)
    paise = round((amount - rupees) * 100)
    digits = str(rupees)
    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        head = re.sub(r"(\d)(?=(\d{2})+$)", r"\1,", head)
        digits = f"{head},{tail}"
    return f"₹{digits}" + (f".{paise:02d}" if paise else "")


def extract_amount(text: str) -> float | None:
    for match in AMOUNT_RE.finditer(text):
        raw = (match.group(1) or match.group(2) or "").replace(",", "")
        try:
            value = float(raw)
        except ValueError:
            continue
        if value > 0:
            return value
    return None


def asks_for_pin(flags: list[RedFlag]) -> bool:
    """The hard rule's trigger: any PIN request or approve/collect request."""
    for f in flags:
        if f.category in _PIN_CATEGORIES:
            return True
        if f.category == "otp_pin_share" and re.search(r"pin|पिन", f.quote, re.IGNORECASE):
            return True
    return False


def detect_direction(text: str, flags: list[RedFlag]) -> tuple[str, str]:
    """Return (direction, reason) where reason is "pin" | "sent" | "received" | "unknown"."""
    if asks_for_pin(flags):
        return SENDING, "pin"                       # HARD RULE — PIN means money leaves
    clean, _ = strip_invisible(text)
    sent, received = bool(_SENT_RE.search(clean)), bool(_RECEIVED_RE.search(clean))
    if sent and not received:
        return SENDING, "sent"
    if received and not sent:
        return RECEIVING, "received"
    return UNKNOWN, "unknown"


def sender_mismatch_flags(text: str, sender: str | None, lang: str) -> list[RedFlag]:
    """Flag when the sender NAME claims to be an organisation but the UPI ID is personal."""
    if not sender or not sender.strip():
        return []
    # The sender field may hold a name, a UPI ID, or both ("SBI Refund (rahul@ybl)").
    # Only the NAME part can claim to be an organisation.
    name = UPI_ID_RE.sub(" ", sender).lower()
    brands = [b for b in ORG_BRANDS if re.search(rf"\b{b}\b", name)]
    if not brands and not any(w in name for w in ORG_WORDS):
        return []   # looks like a person's name; we can't judge that

    flags: list[RedFlag] = []
    seen: set[str] = set()
    for upi_id in UPI_ID_RE.findall(text) + UPI_ID_RE.findall(sender):
        if upi_id.lower() in seen:
            continue
        seen.add(upi_id.lower())
        local_part = upi_id.split("@")[0].lower()
        if brands and any(b in local_part for b in brands):
            continue   # e.g. "SBI Refund" with sbirefund@sbi — consistent
        shown = sender.strip()[:40]
        flags.append(RedFlag(
            quote=upi_id,
            reason=M.SENDER_MISMATCH_REASON[lang].format(sender=shown, upi=upi_id),
            severity="HIGH",
            category="sender_mismatch",
        ))
    return flags


def headline_key(direction: str, reason: str, text: str) -> str:
    if direction == SENDING and reason == "pin":
        return "send_not_receive" if _CLAIMS_RECEIVE_RE.search(text) else "send_pin"
    if direction == SENDING:
        return "sent"
    if direction == RECEIVING:
        return "receiving"
    return "unknown"
