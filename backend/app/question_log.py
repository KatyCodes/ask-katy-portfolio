from datetime import UTC, datetime
from pathlib import Path

from .database import PrivateDatabase


# Persists recruiter questions in the same private SQLite database as applications.
class QuestionLog:
    # Uses the production database unless a test supplies a temporary file.
    def __init__(self, path: Path | None = None):
        self.database = PrivateDatabase(path)
        self.path = self.database.path

    # Stores one recruiter question and answer with a UTC timestamp.
    def record(
        self,
        application_id: str,
        question: str,
        answer: str,
        outcome: str,
    ) -> None:
        self._insert(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "application_id": application_id,
                "question": question,
                "answer": answer,
                "outcome": outcome,
            }
        )

    # Imports one legacy log entry once using a stable source identifier.
    def import_legacy(self, entry: dict, source_key: str) -> bool:
        return self._insert(entry, source_key)

    # Inserts a question record and reports whether SQLite accepted it.
    def _insert(self, entry: dict, source_key: str | None = None) -> bool:
        with self.database.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO question_logs(
                    timestamp, application_id, question, answer, outcome, source_key
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_key) DO NOTHING
                """,
                (
                    entry["timestamp"],
                    entry["application_id"],
                    entry["question"],
                    entry["answer"],
                    entry["outcome"],
                    source_key,
                ),
            )
            return cursor.rowcount == 1

    # Returns one counted page with unanswered questions placed before answered ones.
    def page(self, page: int = 1, page_size: int = 10) -> dict:
        safe_page = max(1, page)
        safe_page_size = max(1, page_size)
        with self.database.connect() as connection:
            total = connection.execute(
                "SELECT COUNT(*) FROM question_logs"
            ).fetchone()[0]
            total_pages = max(1, (total + safe_page_size - 1) // safe_page_size)
            safe_page = min(safe_page, total_pages)
            rows = connection.execute(
                """
                SELECT id, timestamp, application_id, question, answer, outcome
                FROM question_logs
                ORDER BY CASE WHEN outcome = 'unanswered' THEN 0 ELSE 1 END,
                         timestamp DESC,
                         id DESC
                LIMIT ? OFFSET ?
                """,
                (safe_page_size, (safe_page - 1) * safe_page_size),
            ).fetchall()
            return {
                "questions": [dict(row) for row in rows],
                "page": safe_page,
                "page_size": safe_page_size,
                "total": total,
                "total_pages": total_pages,
            }

    # Keeps the older newest-question helper available to existing callers.
    def recent(self, limit: int = 100) -> list[dict]:
        return self.page(page=1, page_size=limit)["questions"]

    # Permanently deletes recruiter-question history without touching other private data.
    def clear(self) -> int:
        with self.database.connect() as connection:
            cursor = connection.execute("DELETE FROM question_logs")
            return cursor.rowcount

    # Replaces a weak or missing answer and marks that log entry as corrected.
    def correct(self, question_id: int, answer: str) -> dict | None:
        with self.database.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE question_logs
                SET answer = ?, outcome = 'answered'
                WHERE id = ?
                """,
                (answer.strip(), question_id),
            )
            if cursor.rowcount != 1:
                return None
            row = connection.execute(
                """
                SELECT id, timestamp, application_id, question, answer, outcome
                FROM question_logs WHERE id = ?
                """,
                (question_id,),
            ).fetchone()
            return dict(row)
