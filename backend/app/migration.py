import hashlib
import json
from pathlib import Path

from .content import ApplicationRepository
from .question_log import QuestionLog

PRIVATE_CONTENT = Path(__file__).resolve().parents[1] / "private_content"
LEGACY_APPLICATIONS = PRIVATE_CONTENT / "applications"
LEGACY_LOGS = PRIVATE_CONTENT / "logs"


# Imports legacy JSON data into SQLite once while preserving every source file.
def migrate_legacy_data(
    repository: ApplicationRepository,
    question_log: QuestionLog,
    applications_path: Path = LEGACY_APPLICATIONS,
    logs_path: Path = LEGACY_LOGS,
) -> None:
    migration_name = "legacy-json-v1"
    if repository.migration_completed(migration_name):
        return
    if applications_path.exists():
        for file in applications_path.glob("*.private.json"):
            repository.import_legacy(json.loads(file.read_text()))
    log_file = logs_path / "questions.jsonl"
    if log_file.exists():
        for line_number, line in enumerate(log_file.read_text().splitlines(), start=1):
            if not line.strip():
                continue
            fingerprint = hashlib.sha256(line.encode()).hexdigest()
            source_key = f"{log_file.name}:{line_number}:{fingerprint}"
            question_log.import_legacy(json.loads(line), source_key)
    repository.mark_migration_completed(migration_name)
