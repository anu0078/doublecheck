"""Settings loaded from the .env file.

Secrets (Gemini key, Telegram token) live ONLY in .env, never in code.
"""
import os

from dotenv import load_dotenv

load_dotenv()

# Fixed limits from the spec (kept as constants so they're easy to explain).
LLM_TIMEOUT_SECONDS = 8          # Gemini must answer within 8 s, else rules-only
RATE_LIMIT_PER_MINUTE = 30       # per IP address
MAX_TEXT_CHARS = 5000            # longest message we accept
MAX_BODY_BYTES = 20_000          # reject bigger request bodies before parsing


class Settings:
    def __init__(self) -> None:
        self.gemini_api_key: str = os.getenv("GEMINI_API_KEY", "").strip()
        self.gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-flash-latest").strip()
        self.telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        self.family_db_path: str = os.getenv("FAMILY_DB_PATH", "family.db").strip()
        # Public https address of this server. Render sets RENDER_EXTERNAL_URL by itself.
        # When set together with TELEGRAM_BOT_TOKEN, the bot runs inside the server (webhook).
        public_url = os.getenv("PUBLIC_URL") or os.getenv("RENDER_EXTERNAL_URL") or ""
        self.public_url: str = public_url.strip().rstrip("/")
        # Behind a hosting proxy every request comes from the proxy's IP. With
        # TRUST_PROXY=true we read the visitor's IP from X-Forwarded-For instead.
        self.trust_proxy: bool = os.getenv("TRUST_PROXY", "false").strip().lower() == "true"
        origins = os.getenv("ALLOWED_ORIGINS", "*")
        self.allowed_origins: list[str] = [o.strip() for o in origins.split(",") if o.strip()]


settings = Settings()
