"""DoubleCheck API (FastAPI, port 8000) + website + (optional) Telegram webhook.

Run:  uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-access-log
"""
import hashlib
import logging
import time
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import llm, services, telegram_webhook
from app.config import MAX_BODY_BYTES, RATE_LIMIT_PER_MINUTE, settings
from app.ratelimit import SlidingWindowRateLimiter
from app.schemas import (
    AIGuardIn,
    AIGuardResult,
    CallCopilotIn,
    CallCopilotResult,
    ErrorResult,
    HealthResult,
    PayGuardIn,
    PayGuardResult,
)

# Privacy: we log ONLY endpoint, risk level and response time. Never message text.
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("doublecheck")
logging.getLogger("httpx").setLevel(logging.WARNING)   # don't log outgoing request URLs



@asynccontextmanager
async def lifespan(_app: FastAPI):
    # On a host with a public https address (e.g. Render) and a bot token,
    # the Telegram bot runs inside this server. Locally: use `python bot.py`.
    if telegram_webhook.webhook_enabled():
        await telegram_webhook.start()
    yield
    await telegram_webhook.stop()


app = FastAPI(title="DoubleCheck API", version="1.0.0", lifespan=lifespan,
              description="Scam protection for Indian users. Nothing you send is stored.")

rate_limiter = SlidingWindowRateLimiter(limit=RATE_LIMIT_PER_MINUTE, window_seconds=60)


def error(status: int, message: str, code: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": message, "code": code})


def client_ip(request: Request) -> str:
    """Visitor IP for rate limiting. Behind a hosting proxy (TRUST_PROXY=true) the
    direct connection is the proxy, so we read the first X-Forwarded-For entry.
    (A visitor could fake that header to dodge the limit, the usual trade-off.)"""
    if settings.trust_proxy:
        first = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        if first:
            return first
    return request.client.host if request.client else "unknown"


def log_request(endpoint: str, risk_level: str, started: float) -> None:
    ms = (time.perf_counter() - started) * 1000
    logger.info("endpoint=%s risk=%s ms=%.0f", endpoint, risk_level, ms)


# ---------------------------------------------------------------- middleware
@app.middleware("http")
async def guard_requests(request: Request, call_next):
    # 1) reject oversized bodies before reading them
    path = request.url.path
    limit = MAX_BODY_BYTES * 10 if path == telegram_webhook.WEBHOOK_PATH else MAX_BODY_BYTES
    length = request.headers.get("content-length")
    if length and length.isdigit() and int(length) > limit:
        return error(413, "Request is too large.", "PAYLOAD_TOO_LARGE")

    # 2) rate limit per IP. /api/health is exempt so the host's health checks
    #    and uptime pings can never lock the app out.
    is_api = path.startswith("/api/")
    rate_limited = is_api and path != "/api/health" and request.method != "OPTIONS"
    if rate_limited and not rate_limiter.allow(client_ip(request)):
        return error(429, "Too many requests. Please wait a minute.", "RATE_LIMITED")

    response = await call_next(request)
    # 3) API results are personal: never cache them. Website files set their own
    #    short cache (see frontend section) so phones don't re-download them.
    if is_api or path.startswith("/telegram/"):
        response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


# Compress responses over 500 bytes (the website and long results shrink ~70-80%,
# which matters on slow mobile data).
app.add_middleware(GZipMiddleware, minimum_size=500)

# Added last = outermost, so even 429/413 responses carry CORS headers.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
    allow_credentials=False,
)


# ---------------------------------------------------------------- error format
@app.exception_handler(RequestValidationError)
async def on_validation_error(request: Request, exc: RequestValidationError):
    # Don't echo the input back (FastAPI's default does) — it may contain bank details.
    first = exc.errors()[0] if exc.errors() else {}
    field = ".".join(str(p) for p in first.get("loc", []) if p != "body") or "body"
    message = str(first.get("msg", "Invalid input")).replace("Value error, ", "")
    return error(422, f"Invalid input: {field}: {message}", "INVALID_INPUT")


@app.exception_handler(StarletteHTTPException)
async def on_http_error(request: Request, exc: StarletteHTTPException):
    codes = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}
    return error(exc.status_code, str(exc.detail), codes.get(exc.status_code, "HTTP_ERROR"))


@app.exception_handler(Exception)
async def on_unexpected_error(request: Request, exc: Exception):
    logger.error("endpoint=%s error=%s", request.url.path, type(exc).__name__)
    return error(500, "Something went wrong. Please try again.", "INTERNAL_ERROR")


_ERRORS = {422: {"model": ErrorResult}, 429: {"model": ErrorResult}}


# ---------------------------------------------------------------- routes
@app.get("/api/health", response_model=HealthResult)
async def health():
    return {"status": "ok", "llm_available": llm.is_available()}


@app.post("/api/call-copilot", response_model=CallCopilotResult, responses=_ERRORS)
async def call_copilot(body: CallCopilotIn):
    started = time.perf_counter()
    result = await services.run_call_copilot(body.text, body.lang)
    log_request("/api/call-copilot", result.risk_level, started)
    return result


@app.post("/api/pay-guard", response_model=PayGuardResult, responses=_ERRORS)
async def pay_guard(body: PayGuardIn):
    started = time.perf_counter()
    outcome = await services.run_pay_guard(body.text, body.amount, body.sender, body.lang)
    log_request("/api/pay-guard", outcome.response.risk_level, started)
    return outcome.response


@app.post("/api/ai-guard", response_model=AIGuardResult, responses=_ERRORS)
async def ai_guard(body: AIGuardIn):
    started = time.perf_counter()
    result = await services.run_ai_guard(body.text)
    log_request("/api/ai-guard", result.risk_level, started)
    return result


# ---------------------------------------------------------------- telegram webhook
@app.post(telegram_webhook.WEBHOOK_PATH, include_in_schema=False)
async def telegram_update(request: Request):
    if not await telegram_webhook.handle(request):
        return error(404, "Not Found", "NOT_FOUND")
    return {"ok": True}


# ---------------------------------------------------------------- frontend
# The backend also serves the website, so phone + API share ONE address:
# one HTTPS tunnel, working mic, no CORS / mixed-content problems.
# Only these three files are served — never .env, package.json etc.
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
FRONTEND_FILES = {"index.html": "text/html; charset=utf-8",
                  "styles.css": "text/css; charset=utf-8",
                  "script.js": "text/javascript; charset=utf-8"}


@app.get("/", include_in_schema=False)
async def frontend_index(request: Request):
    return _frontend_file("index.html", request)


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return Response(status_code=204)   # no icon file; stops a 404 in the browser console


@app.get("/{name}", include_in_schema=False)
async def frontend_asset(name: str, request: Request):
    if name not in FRONTEND_FILES:
        return error(404, "Not Found", "NOT_FOUND")
    return _frontend_file(name, request)


FRONTEND_CACHE_SECONDS = 300


@lru_cache(maxsize=len(FRONTEND_FILES))
def _load_frontend_file(name: str) -> tuple[bytes, str] | None:
    """Read each website file from disk ONCE and keep it in memory with an ETag."""
    path = FRONTEND_DIR / name
    if not path.is_file():
        return None
    body = path.read_bytes()
    return body, '"' + hashlib.sha256(body).hexdigest()[:16] + '"'


def _frontend_file(name: str, request: Request | None = None):
    loaded = _load_frontend_file(name)
    if loaded is None:
        return error(404, "Frontend not found. Put index.html, styles.css and script.js in /frontend.", "NOT_FOUND")
    body, etag = loaded
    headers = {"ETag": etag, "Cache-Control": f"public, max-age={FRONTEND_CACHE_SECONDS}"}
    # Browser already has this exact version -> send nothing (304 Not Modified)
    if request is not None and request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    return Response(content=body, media_type=FRONTEND_FILES[name], headers=headers)


if __name__ == "__main__":
    import os

    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")), access_log=False)
