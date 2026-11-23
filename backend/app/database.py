import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

PRIVATE_CONTENT = Path(__file__).resolve().parents[1] / "private_content"


# Chooses the private database location from configuration or the local default.
def default_database_path() -> Path:
    configured = os.getenv("ASK_KATY_DATABASE_PATH")
    if configured:
        return Path(configured).expanduser()
    return PRIVATE_CONTENT / "ask-katy.private.db"


# Owns SQLite setup and provides short, safely closed database connections.
class PrivateDatabase:
    # Creates the private database file and initializes its tables when necessary.
    def __init__(self, path: Path | None = None):
        self.path = path or default_database_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.touch(mode=0o600)
        self.path.chmod(0o600)
        self._initialize()

    # Opens one transaction, committing on success and rolling back on failure.
    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    # Creates the relational schema without changing tables that already exist.
    def _initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS applications (
                    id TEXT PRIMARY KEY,
                    status TEXT NOT NULL CHECK (status IN ('draft', 'published', 'revoked')),
                    access_path_hash TEXT UNIQUE,
                    public_path TEXT,
                    company TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT '',
                    eyebrow TEXT NOT NULL DEFAULT '',
                    headline TEXT NOT NULL DEFAULT '',
                    introduction TEXT NOT NULL DEFAULT '',
                    job_description TEXT NOT NULL DEFAULT '',
                    company_interest TEXT NOT NULL DEFAULT '',
                    resume_json TEXT NOT NULL DEFAULT '{}',
                    cover_letter_pitch TEXT NOT NULL DEFAULT '',
                    uploaded_resume_filename TEXT NOT NULL DEFAULT '',
                    uploaded_resume_content BLOB
                );

                CREATE TABLE IF NOT EXISTS accomplishments (
                    application_id TEXT NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
                    position INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    detail TEXT NOT NULL,
                    PRIMARY KEY (application_id, position)
                );

                CREATE TABLE IF NOT EXISTS profile_answers (
                    application_id TEXT NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
                    position INTEGER NOT NULL,
                    question TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    PRIMARY KEY (application_id, position)
                );

                CREATE TABLE IF NOT EXISTS application_facts (
                    application_id TEXT NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
                    position INTEGER NOT NULL,
                    fact_id TEXT NOT NULL,
                    PRIMARY KEY (application_id, position)
                );

                CREATE TABLE IF NOT EXISTS mock_answers (
                    application_id TEXT NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
                    name TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    PRIMARY KEY (application_id, name)
                );

                CREATE TABLE IF NOT EXISTS question_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    application_id TEXT NOT NULL,
                    question TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    outcome TEXT NOT NULL CHECK (outcome IN ('answered', 'unanswered', 'off_topic')),
                    source_key TEXT UNIQUE
                );

                CREATE TABLE IF NOT EXISTS profile_facts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    question TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    normalized_question TEXT NOT NULL UNIQUE,
                    source_application_id TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS profile_skills (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    normalized_name TEXT NOT NULL UNIQUE,
                    proficiency TEXT CHECK (
                        proficiency IS NULL OR proficiency IN (
                            'learning', 'familiar', 'working', 'proficient',
                            'advanced', 'expert'
                        )
                    ),
                    years REAL CHECK (years IS NULL OR (years >= 0 AND years <= 60)),
                    used_at TEXT NOT NULL DEFAULT '',
                    detail TEXT NOT NULL DEFAULT '',
                    evidence_quote TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS about_facts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    statement TEXT NOT NULL,
                    normalized_title TEXT NOT NULL UNIQUE,
                    evidence_quote TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS migration_state (
                    name TEXT PRIMARY KEY,
                    completed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS site_settings (
                    name TEXT PRIMARY KEY,
                    value INTEGER NOT NULL
                );

                CREATE INDEX IF NOT EXISTS question_logs_review
                ON question_logs(outcome, timestamp DESC);

                """
            )
            self._upgrade_schema(connection)

    # Applies deliberate schema upgrades without discarding existing private content.
    def _upgrade_schema(self, connection: sqlite3.Connection) -> None:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(applications)")
        }
        if version < 2 and "public_path" not in columns:
            connection.execute("ALTER TABLE applications ADD COLUMN public_path TEXT")
        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS applications_public_path
            ON applications(public_path) WHERE public_path IS NOT NULL
            """
        )
        if version < 3:
            connection.execute(
                """
                INSERT OR IGNORE INTO profile_facts(
                    question, answer, normalized_question, source_application_id
                )
                SELECT question, answer, lower(trim(question)), application_id
                FROM profile_answers
                WHERE trim(answer) <> ''
                """
            )
        if "company_interest" not in columns:
            connection.execute(
                """
                ALTER TABLE applications
                ADD COLUMN company_interest TEXT NOT NULL DEFAULT ''
                """
            )
        if "resume_json" not in columns:
            connection.execute(
                "ALTER TABLE applications ADD COLUMN resume_json TEXT NOT NULL DEFAULT '{}'"
            )
        if "cover_letter_pitch" not in columns:
            connection.execute(
                """
                ALTER TABLE applications
                ADD COLUMN cover_letter_pitch TEXT NOT NULL DEFAULT ''
                """
            )
        if "uploaded_resume_filename" not in columns:
            connection.execute(
                """
                ALTER TABLE applications
                ADD COLUMN uploaded_resume_filename TEXT NOT NULL DEFAULT ''
                """
            )
        if "uploaded_resume_content" not in columns:
            connection.execute(
                "ALTER TABLE applications ADD COLUMN uploaded_resume_content BLOB"
            )
        connection.execute("PRAGMA user_version = 9")
