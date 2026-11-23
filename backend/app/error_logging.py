import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

DEFAULT_ERROR_LOG = (
    Path(__file__).resolve().parents[1]
    / "private_content"
    / "logs"
    / "ask-katy.errors.log"
)


# Reapplies private permissions whenever rotation opens a new active log file.
class PrivateRotatingFileHandler(RotatingFileHandler):
    # Opens the active log and prevents other server users from reading it.
    def _open(self):
        stream = super()._open()
        Path(self.baseFilename).chmod(0o600)
        return stream


# Chooses the private error-log location from configuration or the local default.
def default_error_log_path() -> Path:
    configured = os.getenv("ASK_KATY_ERROR_LOG_PATH")
    return Path(configured).expanduser() if configured else DEFAULT_ERROR_LOG


# Creates one size-limited private logger without recording request bodies or secrets.
def configure_error_logger(
    path: Path | None = None,
    *,
    logger_name: str = "ask_katy.errors",
    include_console: bool = True,
) -> logging.Logger:
    logger = logging.getLogger(logger_name)
    if logger.handlers:
        return logger
    log_path = path or default_error_log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    log_path.parent.chmod(0o700)
    if not log_path.exists():
        log_path.touch(mode=0o600)
    log_path.chmod(0o600)

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )
    file_handler = PrivateRotatingFileHandler(
        log_path,
        maxBytes=1_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    if include_console:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger
