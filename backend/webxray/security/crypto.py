"""Password hashing, session tokens, signed evidence links, and credential encryption."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from cryptography.fernet import Fernet, InvalidToken

from webxray.config import get_settings

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


# A fixed hash used to equalize timing when the user does not exist.
DUMMY_PASSWORD_HASH = _hasher.hash("timing-equalizer-not-a-real-password")


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    key = get_settings().secret_key.encode()
    return hmac.new(key, token.encode(), hashlib.sha256).hexdigest()


def sign_evidence_link(evidence_id: str, ttl_seconds: int | None = None) -> tuple[int, str]:
    settings = get_settings()
    exp = int(time.time()) + (ttl_seconds or settings.evidence_link_ttl_seconds)
    msg = f"evidence:{evidence_id}:{exp}".encode()
    sig = hmac.new(settings.secret_key.encode(), msg, hashlib.sha256).digest()
    return exp, base64.urlsafe_b64encode(sig).decode().rstrip("=")


def verify_evidence_link(evidence_id: str, exp: int, sig: str) -> bool:
    if exp < int(time.time()):
        return False
    msg = f"evidence:{evidence_id}:{exp}".encode()
    expected = hmac.new(get_settings().secret_key.encode(), msg, hashlib.sha256).digest()
    try:
        provided = base64.urlsafe_b64decode(sig + "=" * (-len(sig) % 4))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(expected, provided)


@dataclass(frozen=True)
class TestAccountSecret:
    __test__ = False
    username: str
    password: str


def _fernet() -> Fernet:
    return Fernet(get_settings().credential_encryption_key.encode())


def encrypt_credential(secret: TestAccountSecret) -> bytes:
    payload = json.dumps({"u": secret.username, "p": secret.password}).encode()
    return _fernet().encrypt(payload)


def decrypt_credential(ciphertext: bytes) -> TestAccountSecret:
    try:
        data = json.loads(_fernet().decrypt(bytes(ciphertext)))
    except (InvalidToken, ValueError) as exc:
        raise ValueError("Credential could not be decrypted") from exc
    return TestAccountSecret(username=data["u"], password=data["p"])


def mask_username(username: str) -> str:
    if "@" in username:
        local, domain = username.split("@", 1)
        return f"{local[:2]}{'•' * max(1, len(local) - 2)}@{domain}"
    return f"{username[:2]}{'•' * max(1, len(username) - 2)}"
