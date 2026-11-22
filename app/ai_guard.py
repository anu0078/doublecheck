"""AI guard: find and remove hidden "ignore previous instructions" style text
in emails / web pages before an AI assistant reads them.

Finds: HTML comments, text hidden with CSS (display:none, font-size:0 ...),
zero-width / invisible characters, invisible Unicode "tag" text, and the
shared prompt-injection rules.
"""
import re

from app.models import RedFlag
from app.rules import RULES, is_invisible

_HTML_COMMENT = re.compile(r"<!--(.*?)-->", re.DOTALL)
_ELEMENT = re.compile(r"<(?P<tag>[a-zA-Z][\w-]*)\b(?P<attrs>[^>]*)>(?P<body>.*?)</(?P=tag)\s*>",
                      re.DOTALL)
_HIDDEN_STYLE = re.compile(
    r"display\s*:\s*none|visibility\s*:\s*hidden|opacity\s*:\s*0(?:\.0+)?\s*(?:;|$|[\"'])"
    r"|font-size\s*:\s*0(?:\.0+)?(?:px|pt|em|rem|%)?\s*(?:;|$|[\"'])|(?:left|top)\s*:\s*-\d{3,}px",
    re.IGNORECASE,
)
_HIDDEN_ATTR = re.compile(r"(?:^|\s)(?:hidden|aria-hidden\s*=\s*[\"']true[\"'])(?=\s|$|=|/)", re.IGNORECASE)

_INJECTION_RULE = next(r for r in RULES if r.category == "prompt_injection")


def _is_hidden_element(attrs: str) -> bool:
    return bool(_HIDDEN_STYLE.search(attrs) or _HIDDEN_ATTR.search(attrs))


def _invisible_runs(text: str) -> list[tuple[int, int]]:
    runs, i = [], 0
    while i < len(text):
        if is_invisible(text[i]):
            j = i
            while j < len(text) and is_invisible(text[j]):
                j += 1
            # ZWJ / ZWNJ are normal inside Hindi words and emoji: only count them
            # when they sit next to plain ASCII letters
            run = text[i:j]
            if set(run) <= {"‌", "‍"}:
                prev = text[i - 1] if i > 0 else ""
                nxt = text[j] if j < len(text) else ""
                if not (prev.isascii() and prev.isalpha() or nxt.isascii() and nxt.isalpha()):
                    i = j
                    continue
            runs.append((i, j))
            i = j
        else:
            i += 1
    return runs


def _decode_tags(run: str) -> str:
    """Unicode tag characters secretly encode ASCII text."""
    return "".join(chr(ord(c) - 0xE0000) for c in run if 0xE0020 <= ord(c) <= 0xE007E)


def hidden_content_flags(text: str) -> list[RedFlag]:
    flags: list[RedFlag] = []

    for match in _HTML_COMMENT.finditer(text):
        inner = match.group(1).strip()
        if not inner or inner.startswith("[if") or inner.startswith("<![endif]"):
            continue   # Outlook "conditional comments" are normal in emails
        flags.append(RedFlag(
            quote=match.group(0)[:120],
            reason="Hidden HTML comment. People can't see it, but an AI reading the page can.",
            severity="LOW", category="hidden_content",
        ))

    for match in _ELEMENT.finditer(text):
        if _is_hidden_element(match.group("attrs")) and match.group("body").strip():
            flags.append(RedFlag(
                quote=match.group(0)[:120],
                reason="Text hidden with styling. Invisible on screen, but an AI still reads it.",
                severity="LOW", category="hidden_content",
            ))

    for start, end in _invisible_runs(text):
        run = text[start:end]
        decoded = _decode_tags(run)
        if decoded.strip():
            flags.append(RedFlag(
                quote=run,
                reason=f"Invisible 'tag' characters secretly spell out: \"{decoded[:80]}\"",
                severity="HIGH", category="invisible_chars",
            ))
        else:
            flags.append(RedFlag(
                quote=run,
                reason=f"{len(run)} invisible character(s) found. These can hide or split words to fool filters.",
                severity="MEDIUM", category="invisible_chars",
            ))
    return flags


def _remove_injection_sentences(text: str) -> str:
    """Delete each sentence (or line) that contains an injection phrase."""
    for _ in range(10):
        found = None
        for pattern in _INJECTION_RULE.patterns:
            found = pattern.search(text)
            if found:
                break
        if not found:
            return text
        start = max(text.rfind(ch, 0, found.start()) for ch in ".!?\n") + 1
        ends = [i for i in (text.find(ch, found.end()) for ch in ".!?\n") if i != -1]
        end = (min(ends) + 1) if ends else len(text)
        text = text[:start] + text[end:]
    return text


def clean_text(text: str) -> str:
    """Return the text with hidden instructions, HTML comments and invisible characters removed."""
    cleaned = "".join(ch for ch in text if not is_invisible(ch))
    cleaned = _HTML_COMMENT.sub("", cleaned)
    cleaned = _ELEMENT.sub(lambda m: "" if _is_hidden_element(m.group("attrs")) else m.group(0), cleaned)
    cleaned = _remove_injection_sentences(cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\n\s*\n\s*\n+", "\n\n", cleaned)
    return cleaned.strip()
