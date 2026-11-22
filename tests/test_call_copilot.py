"""Call co-pilot: instant DANGEROUS path, short actions, Hindi replies, API shell."""
import logging

import pytest
from fastapi.testclient import TestClient

from app import main
from app.ratelimit import SlidingWindowRateLimiter
from tests.conftest import fake_llm

DIGITAL_ARREST = "This is CBI officer. You are under digital arrest. Stay on the video call."


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(main, "rate_limiter", SlidingWindowRateLimiter(limit=30, window_seconds=60))
    return TestClient(main.app)


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "llm_available": False}


def test_digital_arrest_is_instant_and_skips_llm(client, monkeypatch):
    calls = []
    fake_llm(monkeypatch, {"risk_level": "LOW", "risk_score": 0}, calls)
    r = client.post("/api/call-copilot", json={"text": DIGITAL_ARREST, "lang": "en"})
    body = r.json()
    assert r.status_code == 200
    assert calls == []                       # Gemini never called
    assert body["risk_level"] == "DANGEROUS"
    assert body["action"] == "HANG UP NOW"
    assert body["script_detected"] == "Digital arrest scam"
    assert body["engine"] == "rules_only"
    assert body["stored"] is False
    assert body["helpline"]["phone"] == "1930"
    assert "cybercrime.gov.in" in body["helpline"]["website"]
    assert all(f["quote"] in DIGITAL_ARREST for f in body["red_flags"])


def test_action_is_short(client):
    for text in [DIGITAL_ARREST, "install anydesk please", "your parcel is seized by customs",
                 "please hurry, urgent", "hello how are you"]:
        body = client.post("/api/call-copilot", json={"text": text}).json()
        assert len(body["action"].split()) <= 6, body["action"]


def test_hindi_reply(client):
    r = client.post("/api/call-copilot", json={"text": "मैं CBI से बोल रहा हूँ, आप गिरफ्तार होंगे", "lang": "hi"})
    body = r.json()
    assert body["action"] == "अभी फ़ोन काटें"
    assert body["script_detected"] == "डिजिटल अरेस्ट धोखाधड़ी"
    assert "1930" in body["helpline"]["text"]


def test_low_result_wording(client):
    body = client.post("/api/call-copilot", json={"text": "Hi, this is your dentist confirming Monday."}).json()
    assert body["risk_level"] == "LOW"
    assert body["disclaimer"] == "No known scam pattern found. Still, never share your OTP or PIN."
    assert body["helpline"] is None
    assert body["stored"] is False


def test_llm_used_when_rules_unsure(client, monkeypatch):
    calls = []
    fake_llm(monkeypatch, {
        "risk_level": "DANGEROUS", "risk_score": 80,
        "action": "Hang up and call your son now please", "why": "Fake relative emergency.",
        "say_this": "I will call him myself.", "script_detected": "Fake relative emergency",
        "red_flags": [{"quote": "your son is in jail", "reason": "Emergency story", "severity": "HIGH"}],
    }, calls)
    body = client.post("/api/call-copilot", json={"text": "Uncle your son is in jail, send money"}).json()
    assert len(calls) == 1
    assert body["engine"] == "rules+llm"
    assert body["risk_level"] == "DANGEROUS"
    assert body["action"] == "HANG UP AND CALL YOUR SON"   # cut to 6 words, uppercased
    assert body["script_detected"] == "Fake relative emergency"


def test_errors_have_error_and_code(client):
    r = client.post("/api/call-copilot", json={"text": "   "})
    assert r.status_code == 422
    assert set(r.json()) == {"error", "code"}
    assert r.json()["code"] == "INVALID_INPUT"

    r = client.post("/api/call-copilot", json={"text": "x" * 6000})
    assert r.json()["code"] == "INVALID_INPUT"

    r = client.post("/api/call-copilot", json={"text": "hi", "lang": "fr"})
    assert r.json()["code"] == "INVALID_INPUT"

    assert client.get("/api/nope").json()["code"] == "NOT_FOUND"


def test_validation_error_does_not_echo_input(client):
    secret = "ACCOUNT-1234567890"
    r = client.post("/api/call-copilot", json={"text": secret, "lang": "xx"})
    assert secret not in r.text


def test_rate_limit(client):
    for _ in range(30):
        assert client.post("/api/call-copilot", json={"text": "hello"}).status_code == 200
    r = client.post("/api/call-copilot", json={"text": "hello"})
    assert r.status_code == 429
    assert r.json() == {"error": "Too many requests. Please wait a minute.", "code": "RATE_LIMITED"}


def test_message_text_never_logged(client, caplog):
    secret = "my account number is 987654321012 and CBI arrest"
    with caplog.at_level(logging.INFO, logger="doublecheck"):
        client.post("/api/call-copilot", json={"text": secret})
    assert "endpoint=/api/call-copilot" in caplog.text
    assert "risk=DANGEROUS" in caplog.text
    assert "987654321012" not in caplog.text


def test_no_store_header(client):
    r = client.post("/api/call-copilot", json={"text": "hello"})
    assert r.headers["cache-control"] == "no-store"


def test_frontend_served_from_same_address(client):
    r = client.get("/")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
    assert "DoubleCheck" in r.text
    assert client.get("/script.js").headers["content-type"].startswith("text/javascript")
    assert client.get("/styles.css").status_code == 200


def test_only_frontend_files_are_served(client):
    for path in ["/.env", "/.env.example", "/package.json", "/bot.py", "/family.db", "/README.md"]:
        r = client.get(path)
        assert r.status_code == 404, path
        assert r.json()["code"] == "NOT_FOUND"
    assert client.get("/api/health").json()["status"] == "ok"
