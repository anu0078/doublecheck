"""The shared detection engine used by all three features (and the bot).

    rules  ->  (optional) Gemini  ->  merge

Merge rules:
- final risk = the HIGHER of rules and LLM (LLM can raise, never lower)
- LLM red flags are kept only if their quote really appears in the message
- if Gemini is missing/slow/broken -> rules-only result, never a crash
"""
import re
from dataclasses import dataclass, field

from app import llm
from app.models import DANGEROUS, RedFlag, combine, score_flags, sort_flags
from app.rules import run_rules


@dataclass
class Analysis:
    level: str
    score: int
    flags: list[RedFlag]
    engine: str                      # "rules+llm" or "rules_only"
    llm_output: "llm.LLMOutput | None" = None
    rule_categories: list[str] = field(default_factory=list)


def find_in_text(text: str, quote: str) -> str | None:
    """Return the exact substring of `text` matching `quote`, or None if it's made up.
    Tolerates differences in letter case and whitespace only."""
    quote = (quote or "").strip()
    if len(quote) < 2:
        return None
    if quote in text:
        return quote
    pattern = r"\s+".join(re.escape(part) for part in quote.split())
    match = re.search(pattern, text, re.IGNORECASE)
    return match.group(0) if match else None


def verify_llm_flags(text: str, llm_flags, existing: list[RedFlag]) -> list[RedFlag]:
    """Drop LLM red flags whose quote isn't actually in the message."""
    known = {f.quote.casefold() for f in existing}
    verified: list[RedFlag] = []
    for item in llm_flags:
        quote = find_in_text(text, item.quote)
        reason = llm.clean_llm_text(item.reason, max_chars=160)
        if quote is None or reason is None or quote.casefold() in known:
            continue
        known.add(quote.casefold())
        verified.append(RedFlag(quote=quote, reason=reason, severity=item.severity, category="llm"))
    return verified


def ordered_categories(flags: list[RedFlag]) -> list[str]:
    seen: list[str] = []
    for f in sort_flags(flags):
        if f.category != "llm" and f.category not in seen:
            seen.append(f.category)
    return seen


async def analyze(
    text: str,
    feature: str,
    lang: str = "en",
    extra_flags: list[RedFlag] | None = None,
    context: dict | None = None,
    skip_llm_if_dangerous: bool = False,
) -> Analysis:
    # 1) rules first
    flags = run_rules(text, lang) + list(extra_flags or [])
    rule_level, rule_score = score_flags(flags)
    categories = ordered_categories(flags)

    # 2) instant path: rules already say DANGEROUS -> don't wait for Gemini
    if skip_llm_if_dangerous and rule_level == DANGEROUS:
        return Analysis(rule_level, rule_score, sort_flags(flags), "rules_only", None, categories)

    # 3) Gemini (returns None on any failure)
    result = await llm.check(feature, text, lang, categories, context)
    if result is None:
        return Analysis(rule_level, rule_score, sort_flags(flags), "rules_only", None, categories)

    # 4) merge: keep only real quotes, take the higher risk
    flags = flags + verify_llm_flags(text, result.red_flags, flags)
    level, score = combine(rule_level, rule_score, result.risk_level, result.risk_score)
    return Analysis(level, score, sort_flags(flags), "rules+llm", result, categories)
