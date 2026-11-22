import asyncio
import json
from pathlib import Path

import pytest

from app import llm
from app.config import settings

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def no_real_gemini(monkeypatch):
    """Tests never call the real Gemini API. Individual tests can fake it."""
    monkeypatch.setattr(settings, "gemini_api_key", "")


def run(coro):
    return asyncio.run(coro)


def fake_llm(monkeypatch, output: dict | None, calls: list | None = None):
    """Make llm.check return `output` (as a validated LLMOutput) or None."""
    async def _fake(feature, text, lang, rule_findings, context=None):
        if calls is not None:
            calls.append({"feature": feature, "text": text, "rule_findings": rule_findings})
        return None if output is None else llm.LLMOutput.model_validate(output)

    monkeypatch.setattr(llm, "check", _fake)


@pytest.fixture
def demo_samples():
    return json.loads((ROOT / "demo_samples.json").read_text(encoding="utf-8"))
