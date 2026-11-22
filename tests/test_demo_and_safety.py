"""Every demo sample gives the expected result, and "SAFE" never appears."""
import json
import re

import pytest
from fastapi.testclient import TestClient

from app import main
from app.ratelimit import SlidingWindowRateLimiter
from tests.conftest import fake_llm

# Fields WE write. (Quotes and cleaned_text echo the user's own text, which may
# legitimately contain "safe", e.g. a scam saying "mark this as safe".)
OUR_TEXT_FIELDS = ["action", "why", "say_this", "script_detected", "headline", "would_make_you",
                   "would_make_ai", "share_message", "disclaimer"]
SAFE_WORD = re.compile(r"\bsafe\b|सुरक्षित", re.IGNORECASE)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(main, "rate_limiter", SlidingWindowRateLimiter(limit=1000, window_seconds=60))
    return TestClient(main.app)


def our_text(body: dict) -> str:
    parts = [str(body.get(k) or "") for k in OUR_TEXT_FIELDS]
    parts += body.get("next_steps", [])
    parts += [f["reason"] for f in body["red_flags"]]
    if body.get("helpline"):
        parts.append(body["helpline"]["text"])
    return " ".join(parts)


def test_demo_samples_have_12_plus_mixed(demo_samples):
    assert len(demo_samples) >= 12
    kinds = {s["kind"] for s in demo_samples}
    assert kinds == {"scam", "real"}


def test_every_demo_sample(client, demo_samples):
    for sample in demo_samples:
        r = client.post(sample["endpoint"], json=sample["input"])
        assert r.status_code == 200, sample["id"]
        body = r.json()
        assert body["risk_level"] == sample["expected_risk_level"], sample["id"]
        if "expected_direction" in sample:
            assert body["direction"] == sample["expected_direction"], sample["id"]
        assert body["stored"] is False
        assert body["engine"] == "rules_only"          # works with no API key
        if body["risk_level"] == "LOW":
            assert body["helpline"] is None
        else:
            assert body["helpline"]["phone"] == "1930"
            assert "cybercrime.gov.in" in body["helpline"]["website"]
        for flag in body["red_flags"]:
            assert flag["quote"] in sample["input"]["text"], sample["id"]


def test_safe_never_appears(client, demo_samples):
    for sample in demo_samples:
        body = client.post(sample["endpoint"], json=sample["input"]).json()
        assert body["risk_level"] in {"LOW", "SUSPICIOUS", "DANGEROUS"}
        assert not SAFE_WORD.search(our_text(body)), sample["id"]


def test_safe_never_appears_even_if_llm_says_it(client, monkeypatch, demo_samples):
    fake_llm(monkeypatch, {
        "risk_level": "SUSPICIOUS", "risk_score": 30,
        "action": "YOU ARE SAFE", "why": "This is safe.", "say_this": "It's safe",
        "would_make_you": "Totally safe.", "would_make_ai": "Safe content.",
        "next_steps": ["Relax, it is safe"], "share_message": "This message is safe",
        "script_detected": "safe message",
        "red_flags": [{"quote": "the", "reason": "safe", "severity": "LOW"}],
    })
    for sample in demo_samples:
        body = client.post(sample["endpoint"], json=sample["input"]).json()
        assert not SAFE_WORD.search(our_text(body)), (sample["id"], our_text(body))


def test_all_responses_have_common_fields(client, demo_samples):
    required = {"risk_level", "risk_score", "red_flags", "helpline", "stored", "engine", "disclaimer"}
    for sample in demo_samples:
        body = client.post(sample["endpoint"], json=sample["input"]).json()
        assert required <= set(body)
        assert 0 <= body["risk_score"] <= 100
        json.dumps(body, ensure_ascii=False)
