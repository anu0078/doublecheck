"""Deployment pieces: Telegram webhook security, proxy IPs, health check exempt from rate limit."""
import asyncio

import pytest
from fastapi.testclient import TestClient
from telegram import Bot

from app import main, telegram_webhook
from app.config import settings
from app.ratelimit import SlidingWindowRateLimiter

UPDATE = {"update_id": 1, "message": {"message_id": 5, "date": 0, "text": "hello",
                                      "chat": {"id": 42, "type": "private"},
                                      "from": {"id": 42, "is_bot": False, "first_name": "Sunita"}}}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(main, "rate_limiter", SlidingWindowRateLimiter(limit=3, window_seconds=60))
    return TestClient(main.app)


class FakeApplication:
    def __init__(self):
        self.bot = Bot("123456:TEST-TOKEN-NOT-REAL")
        self.update_queue = asyncio.Queue()


@pytest.fixture
def webhook_app(monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", "123456:TEST-TOKEN-NOT-REAL")
    fake = FakeApplication()
    monkeypatch.setattr(telegram_webhook, "_application", fake)
    return fake


def test_webhook_off_without_token_or_url(monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", "")
    monkeypatch.setattr(settings, "public_url", "https://x.onrender.com")
    assert telegram_webhook.webhook_enabled() is False
    monkeypatch.setattr(settings, "telegram_bot_token", "1:A")
    monkeypatch.setattr(settings, "public_url", "")
    assert telegram_webhook.webhook_enabled() is False


def test_webhook_secret_is_telegram_safe(monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", "123456:ABC-def")
    secret = telegram_webhook.webhook_secret()
    assert len(secret) == 64 and secret.isalnum()
    assert "123456" not in secret


def test_webhook_rejects_missing_or_wrong_secret(client, webhook_app):
    r = client.post("/telegram/webhook", json=UPDATE)
    assert r.status_code == 404
    r = client.post("/telegram/webhook", json=UPDATE,
                    headers={"X-Telegram-Bot-Api-Secret-Token": "guess"})
    assert r.status_code == 404
    assert webhook_app.update_queue.empty()


def test_webhook_accepts_genuine_update(client, webhook_app):
    r = client.post("/telegram/webhook", json=UPDATE,
                    headers={"X-Telegram-Bot-Api-Secret-Token": telegram_webhook.webhook_secret()})
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    update = webhook_app.update_queue.get_nowait()
    assert update.message.text == "hello"


def test_webhook_404_when_bot_not_running(client, monkeypatch):
    monkeypatch.setattr(telegram_webhook, "_application", None)
    assert client.post("/telegram/webhook", json=UPDATE).status_code == 404


def test_proxy_ip_used_only_when_trusted(client, monkeypatch):
    # Not trusted: X-Forwarded-For is ignored -> everyone from the same proxy shares a limit
    monkeypatch.setattr(settings, "trust_proxy", False)
    for i in range(3):
        client.post("/api/ai-guard", json={"text": "hi"}, headers={"X-Forwarded-For": f"1.1.1.{i}"})
    assert client.post("/api/ai-guard", json={"text": "hi"},
                       headers={"X-Forwarded-For": "9.9.9.9"}).status_code == 429

    # Trusted (on Render): each visitor gets their own limit
    monkeypatch.setattr(main, "rate_limiter", SlidingWindowRateLimiter(limit=3, window_seconds=60))
    monkeypatch.setattr(settings, "trust_proxy", True)
    for _ in range(3):
        client.post("/api/ai-guard", json={"text": "hi"}, headers={"X-Forwarded-For": "1.1.1.1, 10.0.0.1"})
    assert client.post("/api/ai-guard", json={"text": "hi"},
                       headers={"X-Forwarded-For": "1.1.1.1"}).status_code == 429
    assert client.post("/api/ai-guard", json={"text": "hi"},
                       headers={"X-Forwarded-For": "2.2.2.2"}).status_code == 200


def test_health_never_rate_limited(client):
    for _ in range(10):
        assert client.get("/api/health").status_code == 200


def test_app_starts_without_bot_settings(monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", "")
    with TestClient(main.app) as c:          # runs the lifespan startup + shutdown
        assert c.get("/api/health").status_code == 200


def test_bad_bot_token_does_not_crash_site(monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", "not-a-real-token")
    monkeypatch.setattr(settings, "public_url", "https://example.onrender.com")
    with TestClient(main.app) as c:
        assert c.get("/api/health").status_code == 200
        assert c.post("/telegram/webhook", json=UPDATE).status_code == 404


def test_responses_are_gzip_compressed(client):
    r = client.get("/", headers={"Accept-Encoding": "gzip"})
    assert r.headers.get("content-encoding") == "gzip"
    r = client.post("/api/ai-guard", json={"text": "x " * 400}, headers={"Accept-Encoding": "gzip"})
    assert r.headers.get("content-encoding") == "gzip"


def test_website_files_cached_but_api_never(client):
    page = client.get("/script.js")
    assert page.headers["cache-control"] == "public, max-age=300"
    etag = page.headers["etag"]
    again = client.get("/script.js", headers={"If-None-Match": etag})
    assert again.status_code == 304 and again.content == b""
    api = client.post("/api/ai-guard", json={"text": "hello"})
    assert api.headers["cache-control"] == "no-store"
