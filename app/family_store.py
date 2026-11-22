"""Storage for the Telegram bot.

SQLite stores ONLY: chat IDs, parent->child links, and language preference.
No messages, no names, no phone numbers.

Link codes live in memory only (they expire after 15 minutes anyway).
"""
import secrets
import sqlite3
import threading
import time

CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"   # no 0/O, 1/I to avoid confusion
CODE_LENGTH = 6
CODE_TTL_SECONDS = 15 * 60


class FamilyStore:
    def __init__(self, path: str) -> None:
        self.path = path
        # One connection reused for the life of the bot (no reconnect per query).
        # Queries are tiny and indexed by primary key; the lock keeps it thread-safe.
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock, self._conn as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(
                "CREATE TABLE IF NOT EXISTS users ("
                " chat_id INTEGER PRIMARY KEY,"
                " lang TEXT NOT NULL DEFAULT 'en' CHECK (lang IN ('en', 'hi')))"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS family_links ("
                " parent_chat_id INTEGER NOT NULL,"
                " child_chat_id INTEGER NOT NULL,"
                " PRIMARY KEY (parent_chat_id, child_chat_id))"
            )

    def _run(self, sql: str, params: tuple = ()) -> list[tuple]:
        # parameterised queries only (no string formatting -> no SQL injection)
        with self._lock, self._conn as conn:
            return conn.execute(sql, params).fetchall()

    def close(self) -> None:
        self._conn.close()

    def get_lang(self, chat_id: int) -> str:
        rows = self._run("SELECT lang FROM users WHERE chat_id = ?", (chat_id,))
        return rows[0][0] if rows else "en"

    def set_lang(self, chat_id: int, lang: str) -> None:
        if lang not in ("en", "hi"):
            raise ValueError("lang must be 'en' or 'hi'")
        self._run(
            "INSERT INTO users (chat_id, lang) VALUES (?, ?) "
            "ON CONFLICT(chat_id) DO UPDATE SET lang = excluded.lang",
            (chat_id, lang),
        )

    def add_link(self, parent_chat_id: int, child_chat_id: int) -> None:
        self._run(
            "INSERT OR IGNORE INTO family_links (parent_chat_id, child_chat_id) VALUES (?, ?)",
            (parent_chat_id, child_chat_id),
        )

    def get_children(self, parent_chat_id: int) -> list[int]:
        rows = self._run("SELECT child_chat_id FROM family_links WHERE parent_chat_id = ?",
                         (parent_chat_id,))
        return [r[0] for r in rows]

    def remove_links_for(self, chat_id: int) -> list[int]:
        """/stopfamily from EITHER side. Returns the other people who were linked."""
        rows = self._run(
            "SELECT child_chat_id FROM family_links WHERE parent_chat_id = ? "
            "UNION SELECT parent_chat_id FROM family_links WHERE child_chat_id = ?",
            (chat_id, chat_id),
        )
        self._run("DELETE FROM family_links WHERE parent_chat_id = ? OR child_chat_id = ?",
                  (chat_id, chat_id))
        return [r[0] for r in rows]


class PendingCodes:
    """One-time 6-character codes, created only AFTER the parent agreed."""

    def __init__(self, ttl_seconds: int = CODE_TTL_SECONDS, clock=time.monotonic) -> None:
        self.ttl = ttl_seconds
        self.clock = clock
        self._codes: dict[str, tuple[int, float]] = {}   # code -> (parent_chat_id, created)

    def create(self, parent_chat_id: int) -> str:
        self.cancel_for(parent_chat_id)                   # one active code per parent
        while True:
            code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
            if code not in self._codes:
                break
        self._codes[code] = (parent_chat_id, self.clock())
        return code

    def redeem(self, code: str, child_chat_id: int) -> tuple[str, int | None]:
        """Returns ("ok", parent_id) | ("self", None) | ("invalid", None)."""
        code = (code or "").strip().upper()
        entry = self._codes.get(code)
        if entry is None:
            return "invalid", None
        parent_chat_id, created = entry
        if self.clock() - created > self.ttl:
            del self._codes[code]
            return "invalid", None
        if parent_chat_id == child_chat_id:
            return "self", None
        del self._codes[code]                              # single use
        return "ok", parent_chat_id

    def cancel_for(self, parent_chat_id: int) -> None:
        for code in [c for c, (p, _) in self._codes.items() if p == parent_chat_id]:
            del self._codes[code]
