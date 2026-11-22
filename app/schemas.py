"""Request and response shapes. Literal types make "SAFE" impossible to return."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.config import MAX_TEXT_CHARS

Lang = Literal["en", "hi"]
RiskLevel = Literal["LOW", "SUSPICIOUS", "DANGEROUS"]


class _TextIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    text: str = Field(min_length=1, max_length=MAX_TEXT_CHARS)

    @field_validator("text")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("text must not be empty")
        return v


# ---------------------------------------------------------------- requests
class CallCopilotIn(_TextIn):
    lang: Lang = "en"


class PayGuardIn(_TextIn):
    amount: float | None = Field(default=None, ge=0, le=100_000_000)
    sender: str | None = Field(default=None, max_length=100)
    lang: Lang = "en"


class AIGuardIn(_TextIn):
    pass


# ---------------------------------------------------------------- responses
class RedFlagOut(BaseModel):
    quote: str
    reason: str
    severity: Literal["LOW", "MEDIUM", "HIGH"]


class Helpline(BaseModel):
    phone: str
    website: str
    text: str


class BaseResult(BaseModel):
    risk_level: RiskLevel
    risk_score: int = Field(ge=0, le=100)
    red_flags: list[RedFlagOut]
    helpline: Helpline | None          # filled on SUSPICIOUS / DANGEROUS, null on LOW
    stored: Literal[False] = False
    engine: Literal["rules+llm", "rules_only"]
    disclaimer: str


class CallCopilotResult(BaseResult):
    action: str
    script_detected: str | None
    why: str
    say_this: str | None


class PayGuardResult(BaseResult):
    direction: Literal["SENDING", "RECEIVING", "UNKNOWN"]
    headline: str
    would_make_you: str
    next_steps: list[str]
    share_message: str


class AIGuardResult(BaseResult):
    would_make_ai: str
    cleaned_text: str
    next_steps: list[str]
    share_message: str


class HealthResult(BaseModel):
    status: Literal["ok"]
    llm_available: bool


class ErrorResult(BaseModel):
    error: str
    code: str
