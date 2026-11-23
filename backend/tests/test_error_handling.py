import logging
import stat
from unittest.mock import Mock

import app.main as main_module
from app.error_logging import configure_error_logger
from app.main import app
from fastapi.testclient import TestClient


# Confirms operational errors are written to a private file with restricted permissions.
def test_error_logger_writes_to_restricted_private_file(tmp_path):
    log_path = tmp_path / "logs" / "ask-katy.errors.log"
    logger = configure_error_logger(
        log_path,
        logger_name="ask_katy_test_file",
        include_console=False,
    )

    logger.error("safe test diagnostic")
    for handler in logger.handlers:
        handler.flush()

    assert "safe test diagnostic" in log_path.read_text()
    assert stat.S_IMODE(log_path.stat().st_mode) == 0o600


# Confirms an unexpected failure is logged by reference without exposing details publicly.
def test_unexpected_api_error_returns_safe_reference(monkeypatch):
    recorded_logger = Mock(spec=logging.Logger)
    monkeypatch.setattr(main_module, "error_logger", recorded_logger, raising=False)

    # Provides an isolated failing route used only by this test process.
    def raise_unexpected_error():
        raise RuntimeError("private database detail must stay hidden")

    app.add_api_route("/__test__/unexpected-error", raise_unexpected_error)
    response = TestClient(app, raise_server_exceptions=False).get(
        "/__test__/unexpected-error"
    )

    assert response.status_code == 500
    assert response.json()["detail"] == (
        "Ask Katy is experiencing some technical difficulties. Please refresh "
        "the page and try again, or contact Katy at katyannhenning@gmail.com."
    )
    assert len(response.json()["error_id"]) == 8
    assert response.headers["x-error-id"] == response.json()["error_id"]
    assert "private database detail" not in response.text
    recorded_logger.exception.assert_called_once()
