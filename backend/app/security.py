import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from urllib.parse import urlsplit

# Uses a process-local key in development so even an unconfigured local cookie is not forgeable.
DEVELOPMENT_SESSION_SECRET = secrets.token_urlsafe(32)
MINIMUM_SESSION_SECRET_LENGTH = 32


# Returns the configured signing key while preserving the legacy variable during migration.
def session_secret() -> str:
    return (
        os.getenv("ASK_KATY_SESSION_SECRET")
        or os.getenv("ASK_KATHRYN_SESSION_SECRET")
        or DEVELOPMENT_SESSION_SECRET
    )


# Prevents production from starting with a missing or easily guessed cookie-signing key.
def validate_session_secret(*, require_secure: bool) -> None:
    if not require_secure:
        return
    configured = os.getenv("ASK_KATY_SESSION_SECRET") or os.getenv(
        "ASK_KATHRYN_SESSION_SECRET"
    )
    if not configured:
        raise RuntimeError(
            "ASK_KATY_SESSION_SECRET must be configured when secure cookies are enabled"
        )
    if len(configured) < MINIMUM_SESSION_SECRET_LENGTH:
        raise RuntimeError("ASK_KATY_SESSION_SECRET must be at least 32 characters")


# Fails closed when production could accept credentialed browser requests from an unsafe origin.
def validate_production_configuration(
    *,
    cookie_secure: bool,
    allowed_origins: list[str],
) -> None:
    if not cookie_secure:
        return
    if not allowed_origins:
        raise RuntimeError("Production CORS must contain exact HTTPS origins")
    for origin in allowed_origins:
        parsed = urlsplit(origin)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.path
            or parsed.query
            or parsed.fragment
            or parsed.username
            or parsed.password
            or "*" in origin
        ):
            raise RuntimeError("Production CORS must contain exact HTTPS origins")


# Loads the signing secret while accepting the original variable name during migration.
def _secret() -> bytes:
    return session_secret().encode()


# Creates a signed, expiring session value that cannot be altered by the browser.
def sign_session(application_id: str, ttl: int = 3600) -> str:
    data = {"app": application_id, "exp": int(time.time()) + ttl}
    payload = base64.urlsafe_b64encode(json.dumps(data).encode()).decode().rstrip("=")
    signature = hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{signature}"


# Validates a session signature and expiry, returning its application scope if valid.
def verify_session(value: str | None) -> str | None:
    if not value or "." not in value:
        return None
    payload, signature = value.rsplit(".", 1)
    expected = hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return None
    try:
        padded = payload + "=" * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded))
        return data["app"] if data["exp"] >= time.time() else None
    except (ValueError, KeyError, json.JSONDecodeError):
        return None
