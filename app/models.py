"""Shared building blocks: risk levels, red flags and scoring.

There is deliberately NO "SAFE" level. We can only say we found no known
scam pattern, never that something is safe.
"""
from dataclasses import dataclass

LOW = "LOW"
SUSPICIOUS = "SUSPICIOUS"
DANGEROUS = "DANGEROUS"
LEVEL_ORDER = [LOW, SUSPICIOUS, DANGEROUS]

# Score range (0-100) that belongs to each level.
LEVEL_BANDS = {LOW: (0, 24), SUSPICIOUS: (25, 59), DANGEROUS: (60, 100)}

# Points per red-flag severity. One HIGH flag alone = DANGEROUS.
# MEDIUM alone = SUSPICIOUS. MEDIUM + urgency, or two MEDIUMs = DANGEROUS.
SEVERITY_POINTS = {"LOW": 20, "MEDIUM": 40, "HIGH": 70}
SEVERITY_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}


@dataclass(frozen=True)
class RedFlag:
    quote: str      # exact text from the message (frontend highlights it)
    reason: str     # short explanation for the user
    severity: str   # "LOW" | "MEDIUM" | "HIGH"
    category: str   # internal only (e.g. "digital_arrest"), not sent to the client

    def to_public(self) -> dict:
        return {"quote": self.quote, "reason": self.reason, "severity": self.severity}


def level_from_score(score: int) -> str:
    if score >= LEVEL_BANDS[DANGEROUS][0]:
        return DANGEROUS
    if score >= LEVEL_BANDS[SUSPICIOUS][0]:
        return SUSPICIOUS
    return LOW


def higher_level(a: str, b: str) -> str:
    return a if LEVEL_ORDER.index(a) >= LEVEL_ORDER.index(b) else b


def clamp_to_level(score: int, level: str) -> int:
    low, high = LEVEL_BANDS[level]
    return max(low, min(high, int(score)))


def score_flags(flags: list[RedFlag]) -> tuple[str, int]:
    """Rules score: each category counts once, at its worst severity."""
    worst: dict[str, int] = {}
    for flag in flags:
        points = SEVERITY_POINTS[flag.severity]
        worst[flag.category] = max(worst.get(flag.category, 0), points)
    score = min(100, sum(worst.values()))
    return level_from_score(score), score


def combine(rule_level: str, rule_score: int, llm_level: str, llm_score: int) -> tuple[str, int]:
    """Final risk = whichever is HIGHER. The LLM can raise risk, never lower it."""
    llm_score = clamp_to_level(llm_score, llm_level)
    level = higher_level(rule_level, llm_level)
    score = clamp_to_level(max(rule_score, llm_score), level)
    return level, score


def sort_flags(flags: list[RedFlag]) -> list[RedFlag]:
    return sorted(flags, key=lambda f: SEVERITY_ORDER[f.severity])
