"""Feature logic. FastAPI routes and the Telegram bot both call these functions,
so every channel uses the exact same engine and rules."""
from dataclasses import dataclass

from app import ai_guard, upi
from app import messages as M
from app.engine import Analysis, analyze
from app.llm import clean_llm_text
from app.models import DANGEROUS, LOW
from app.rules import injection_flags
from app.schemas import AIGuardResult, CallCopilotResult, PayGuardResult


def _is_risky(level: str) -> bool:
    return level != LOW


def common_fields(analysis: Analysis, lang: str) -> dict:
    """Fields every endpoint returns."""
    risky = _is_risky(analysis.level)
    return {
        "risk_level": analysis.level,
        "risk_score": analysis.score,
        "red_flags": [f.to_public() for f in analysis.flags],
        "helpline": M.HELPLINE[lang] if risky else None,
        "stored": False,
        "engine": analysis.engine,
        "disclaimer": M.DISCLAIMER["RISKY" if risky else "LOW"][lang],
    }


def _limit_words(text: str, max_words: int) -> str:
    return " ".join(text.split()[:max_words])


# ================================================================ call co-pilot
def _call_template(analysis: Analysis, lang: str) -> tuple[str, str, str | None]:
    category = M.primary_category(analysis.rule_categories)
    if category == "urgency" and analysis.level == DANGEROUS:
        category = None   # urgency words alone shouldn't drive a DANGEROUS reply
    key = category if category in M.CALL_TEMPLATES else f"_{analysis.level}"
    return M.CALL_TEMPLATES[key][lang]


async def run_call_copilot(text: str, lang: str = "en") -> CallCopilotResult:
    # If rules already say DANGEROUS we answer instantly, without waiting for Gemini.
    analysis = await analyze(text, "call_copilot", lang, skip_llm_if_dangerous=True)
    action, why, say_this = _call_template(analysis, lang)
    script = M.label(M.primary_category(analysis.rule_categories), lang)

    out = analysis.llm_output
    if out is not None:   # Gemini answered: use its wording where it passes our checks
        llm_action = clean_llm_text(out.action, max_chars=60)
        if llm_action:
            action = _limit_words(llm_action, 6)
        why = clean_llm_text(out.why, max_chars=140) or why
        say_this = clean_llm_text(out.say_this, max_chars=140) or say_this
        if script is None:
            script = clean_llm_text(out.script_detected, max_chars=60)

    if lang == "en":
        action = action.upper()
    if script is None and analysis.level == LOW:
        say_this = None

    return CallCopilotResult(
        **common_fields(analysis, lang),
        action=action,
        script_detected=script,
        why=why,
        say_this=say_this,
    )


# ================================================================ UPI guard
@dataclass
class PayGuardOutcome:
    response: PayGuardResult
    primary_category: str | None     # used by the bot for the family alert


def _merge_steps(fixed: list[str], extra: list[str], limit: int = 5) -> list[str]:
    steps = list(fixed)
    for step in extra:
        cleaned = clean_llm_text(step, max_chars=120)
        if cleaned and cleaned.lower() not in {s.lower() for s in steps}:
            steps.append(cleaned)
        if len(steps) >= limit:
            break
    return steps[:limit]


async def run_pay_guard(text: str, amount: float | None = None, sender: str | None = None,
                        lang: str = "en") -> PayGuardOutcome:
    # extra checks on top of the shared rules: sender/UPI mismatch, and the
    # injection rule on the sender field too (every input is checked)
    extra = upi.sender_mismatch_flags(text, sender, lang)
    if sender:
        extra += injection_flags(sender, lang)
    context = {"amount": amount, "sender": sender}
    analysis = await analyze(text, "pay_guard", lang, extra_flags=extra, context=context)

    # Direction and headline come from CODE (hard rule), never from the LLM.
    direction, reason = upi.detect_direction(text, analysis.flags)
    value = amount if amount is not None else upi.extract_amount(text)
    amt_upper = upi.format_inr(value) if value else M.AMOUNT_FALLBACK[lang]
    amt_lower = upi.format_inr(value) if value else M.AMOUNT_FALLBACK_LOWER[lang]
    headline = M.PAY_HEADLINES[upi.headline_key(direction, reason, text)][lang].format(amt=amt_upper)

    risky = _is_risky(analysis.level)
    category = M.primary_category(analysis.rule_categories)
    out = analysis.llm_output

    # What would really happen: fixed sentence when the PIN rule fired.
    would_make_you = M.WOULD_MAKE_YOU[reason][lang].format(amt=amt_lower)
    if out is not None and reason != "pin":
        would_make_you = clean_llm_text(out.would_make_you) or would_make_you

    if risky:
        fixed = M.PAY_NEXT_STEPS["risky_sending" if direction == upi.SENDING else "risky_other"][lang]
    else:
        fixed = M.PAY_NEXT_STEPS["low"][lang]
    next_steps = _merge_steps(fixed, out.next_steps if out else [])

    scam_label = M.label(category, lang) or M.label("pin_entry", lang)
    share = M.PAY_SHARE["risky" if risky else "low"][lang].format(label=scam_label)
    if out is not None and risky:
        share = clean_llm_text(out.share_message, max_chars=200) or share

    response = PayGuardResult(
        **common_fields(analysis, lang),
        direction=direction,
        headline=headline,
        would_make_you=would_make_you,
        next_steps=next_steps,
        share_message=share,
    )
    return PayGuardOutcome(response=response, primary_category=category)


# ================================================================ AI guard
async def run_ai_guard(text: str) -> AIGuardResult:
    analysis = await analyze(text, "ai_guard", "en", extra_flags=ai_guard.hidden_content_flags(text))
    risky = _is_risky(analysis.level)
    key = "risky" if risky else "low"
    out = analysis.llm_output

    would_make_ai = M.AI_WOULD_MAKE[key]
    share = M.AI_SHARE[key]
    if out is not None and risky:
        would_make_ai = clean_llm_text(out.would_make_ai) or would_make_ai
        share = clean_llm_text(out.share_message, max_chars=200) or share

    return AIGuardResult(
        **common_fields(analysis, "en"),
        would_make_ai=would_make_ai,
        cleaned_text=ai_guard.clean_text(text),
        next_steps=_merge_steps(M.AI_NEXT_STEPS[key], out.next_steps if out else []),
        share_message=share,
    )
