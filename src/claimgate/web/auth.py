"""Lightweight, local/dev session authentication for the ClaimGate web app.

This is intentionally NOT a production authentication system: users and
sessions are held in-memory (process-local, cleared on restart), exactly like
the existing `RunRegistry`. It exists to gate the `/app/*` product shell
behind a real sign-in flow rather than pretending the demo has no login at
all. Passwords are hashed with PBKDF2-HMAC-SHA256 (stdlib `hashlib`, no
plaintext storage, no new dependency) — a reasonable, well-understood scheme,
though a production deployment would want a dedicated identity provider,
persistent storage, rate limiting, and HTTPS-only cookies.
"""

from __future__ import annotations

import hashlib
import re
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone

SESSION_COOKIE_NAME = "claimgate_session"
_PBKDF2_ITERATIONS = 260_000
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def is_valid_email(value: str) -> bool:
    return bool(_EMAIL_PATTERN.match(value.strip()))


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), _PBKDF2_ITERATIONS
    ).hex()
    return f"pbkdf2_sha256${_PBKDF2_ITERATIONS}${salt}${digest}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, iterations_text, salt, expected_digest = encoded.split("$")
        iterations = int(iterations_text)
    except ValueError:
        return False
    if scheme != "pbkdf2_sha256":
        return False
    candidate = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), iterations
    ).hex()
    return secrets.compare_digest(candidate, expected_digest)


@dataclass(frozen=True)
class User:
    user_id: str
    full_name: str
    email: str
    workspace_name: str
    password_hash: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def public_profile(self) -> dict[str, str]:
        return {
            "user_id": self.user_id,
            "full_name": self.full_name,
            "email": self.email,
            "workspace_name": self.workspace_name,
        }


class EmailAlreadyRegisteredError(ValueError):
    pass


class UserStore:
    """In-memory user directory. Process-local by design (see module docstring)."""

    def __init__(self) -> None:
        self._by_email: dict[str, User] = {}
        self._by_id: dict[str, User] = {}

    def create(self, *, full_name: str, email: str, workspace_name: str, password: str) -> User:
        normalized_email = email.strip().lower()
        if normalized_email in self._by_email:
            raise EmailAlreadyRegisteredError(f"{email} is already registered")
        user = User(
            user_id=secrets.token_hex(12),
            full_name=full_name.strip(),
            email=normalized_email,
            workspace_name=workspace_name.strip(),
            password_hash=hash_password(password),
        )
        self._by_email[normalized_email] = user
        self._by_id[user.user_id] = user
        return user

    def get_by_email(self, email: str) -> User | None:
        return self._by_email.get(email.strip().lower())

    def get_by_id(self, user_id: str) -> User | None:
        return self._by_id.get(user_id)

    def authenticate(self, *, email: str, password: str) -> User | None:
        user = self.get_by_email(email)
        if user is None or not verify_password(password, user.password_hash):
            return None
        return user


class SessionStore:
    """Maps opaque session tokens to user ids. In-memory, process-local."""

    def __init__(self) -> None:
        self._sessions: dict[str, str] = {}

    def create(self, user_id: str) -> str:
        token = secrets.token_urlsafe(32)
        self._sessions[token] = user_id
        return token

    def user_id_for(self, token: str | None) -> str | None:
        if not token:
            return None
        return self._sessions.get(token)

    def destroy(self, token: str | None) -> None:
        if token:
            self._sessions.pop(token, None)
