import pytest
from app.security import validate_production_configuration, validate_session_secret


# Confirms production cannot silently sign private cookies with the public development fallback.
def test_secure_cookies_require_an_explicit_session_secret(monkeypatch):
    monkeypatch.delenv("ASK_KATY_SESSION_SECRET", raising=False)
    monkeypatch.delenv("ASK_KATHRYN_SESSION_SECRET", raising=False)

    with pytest.raises(RuntimeError, match="ASK_KATY_SESSION_SECRET"):
        validate_session_secret(require_secure=True)


# Confirms weak signing secrets are rejected when secure production cookies are enabled.
def test_secure_cookies_reject_a_short_session_secret(monkeypatch):
    monkeypatch.setenv("ASK_KATY_SESSION_SECRET", "too-short")

    with pytest.raises(RuntimeError, match="at least 32 characters"):
        validate_session_secret(require_secure=True)


# Confirms local development can retain its convenient fallback while production uses a strong key.
def test_session_secret_validation_accepts_safe_configurations(monkeypatch):
    monkeypatch.delenv("ASK_KATY_SESSION_SECRET", raising=False)
    monkeypatch.delenv("ASK_KATHRYN_SESSION_SECRET", raising=False)
    validate_session_secret(require_secure=False)

    monkeypatch.setenv("ASK_KATY_SESSION_SECRET", "a" * 32)
    validate_session_secret(require_secure=True)


# Confirms production accepts only explicit HTTPS browser origins.
@pytest.mark.parametrize(
    "origins",
    [
        [],
        ["*"],
        ["http://katycodes.example"],
        ["https://katycodes.example/admin"],
        ["https://katycodes.example", "http://localhost:5173"],
    ],
)
def test_production_rejects_unsafe_cors_origins(origins):
    with pytest.raises(RuntimeError, match="HTTPS origins"):
        validate_production_configuration(
            cookie_secure=True,
            allowed_origins=origins,
        )


# Confirms local HTTP development remains convenient while production is fail-closed.
def test_production_configuration_accepts_local_and_secure_modes():
    validate_production_configuration(
        cookie_secure=False,
        allowed_origins=["http://localhost:5173"],
    )
    validate_production_configuration(
        cookie_secure=True,
        allowed_origins=["https://katycodes.example"],
    )
