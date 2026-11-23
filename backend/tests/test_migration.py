import json
import sqlite3

from app.content import ApplicationRepository, token_hash
from app.migration import migrate_legacy_data
from app.question_log import QuestionLog


# Confirms legacy private files import once and remain untouched as backups.
def test_legacy_files_migrate_once_without_being_deleted(tmp_path):
    applications_path = tmp_path / "applications"
    logs_path = tmp_path / "logs"
    applications_path.mkdir()
    logs_path.mkdir()
    legacy_application = {
        "id": "example-one",
        "status": "published",
        "access_path_hash": token_hash("example-private-token"),
        "page": {
            "company": "Example",
            "role": "Engineer",
            "eyebrow": "A NOTE FOR EXAMPLE",
            "headline": "A headline",
            "introduction": "An introduction",
            "accomplishments": [
                {"title": "APIs", "detail": "Built integrations."}
            ],
        },
        "job_description": "A job description",
        "profile_answers": [
            {"question": "What did you build?", "answer": "Integrations."}
        ],
        "fact_ids": ["api-work"],
        "mock_answers": {"fit": "Approved fit answer."},
    }
    application_file = applications_path / "example.application.private.json"
    application_file.write_text(json.dumps(legacy_application))
    log_file = logs_path / "questions.jsonl"
    log_file.write_text(
        json.dumps(
            {
                "timestamp": "2026-01-01T00:00:00+00:00",
                "application_id": "example-one",
                "question": "What is missing?",
                "answer": "I am not sure.",
                "outcome": "unanswered",
            }
        )
        + "\n"
    )
    original_application = application_file.read_text()
    original_log = log_file.read_text()
    repository = ApplicationRepository(tmp_path / "ask-katy.private.db")
    question_log = QuestionLog(repository.path)

    migrate_legacy_data(repository, question_log, applications_path, logs_path)
    migrate_legacy_data(repository, question_log, applications_path, logs_path)

    imported = repository.for_admin("example-one")
    assert imported["page"]["accomplishments"][0]["title"] == "APIs"
    assert imported["profile_answers"][0]["answer"] == "Integrations."
    assert imported["fact_ids"] == ["api-work"]
    assert imported["mock_answers"]["fit"] == "Approved fit answer."
    assert len(question_log.recent()) == 1
    assert application_file.read_text() == original_application
    assert log_file.read_text() == original_log

    repository.delete("example-one")
    migrate_legacy_data(repository, question_log, applications_path, logs_path)
    assert repository.for_admin("example-one") is None


# Confirms the SQLite database file is private to the server account.
def test_database_file_uses_private_permissions(tmp_path):
    repository = ApplicationRepository(tmp_path / "ask-katy.private.db")

    assert repository.path.stat().st_mode & 0o777 == 0o600


# Confirms the schema records its version so future migrations can be deliberate.
def test_database_schema_has_a_version(tmp_path):
    repository = ApplicationRepository(tmp_path / "ask-katy.private.db")

    with repository.database.connect() as connection:
        version = connection.execute("PRAGMA user_version").fetchone()[0]

    assert version == 9


# Confirms an existing version-one database gains vanity URLs without losing data.
def test_version_one_database_upgrades_to_vanity_urls(tmp_path):
    database_path = tmp_path / "ask-katy.private.db"
    connection = sqlite3.connect(database_path)
    connection.executescript(
        """
        CREATE TABLE applications (
            id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            access_path_hash TEXT UNIQUE,
            company TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT '',
            eyebrow TEXT NOT NULL DEFAULT '',
            headline TEXT NOT NULL DEFAULT '',
            introduction TEXT NOT NULL DEFAULT '',
            job_description TEXT NOT NULL DEFAULT ''
        );
        INSERT INTO applications(id, status, company, role)
        VALUES ('existing', 'draft', 'Existing Co', 'Engineer');
        PRAGMA user_version = 1;
        """
    )
    connection.commit()
    connection.close()

    repository = ApplicationRepository(database_path)
    with repository.database.connect() as upgraded:
        columns = {
            row["name"] for row in upgraded.execute("PRAGMA table_info(applications)")
        }
        version = upgraded.execute("PRAGMA user_version").fetchone()[0]

    assert "public_path" in columns
    assert "company_interest" in columns
    assert "resume_json" in columns
    assert "cover_letter_pitch" in columns
    assert "uploaded_resume_filename" in columns
    assert "uploaded_resume_content" in columns
    assert version == 9


# Confirms existing profile facts survive while the new knowledge tables are added.
def test_existing_profile_upgrades_to_skills_and_about_without_data_loss(tmp_path):
    repository = ApplicationRepository(tmp_path / "ask-katy.private.db")
    repository.save_profile_fact("What does Katy know?", "A preserved fact.")
    with repository.database.connect() as connection:
        connection.execute("DROP TABLE profile_skills")
        connection.execute("DROP TABLE about_facts")
        connection.execute("PRAGMA user_version = 4")

    upgraded = ApplicationRepository(repository.path)

    assert upgraded.list_profile_facts()[0]["answer"] == "A preserved fact."
    assert upgraded.list_profile_knowledge()["skills"] == []
    assert upgraded.list_profile_knowledge()["about"] == []


# Confirms existing application answers become reusable profile knowledge once.
def test_existing_intake_answers_migrate_to_shared_profile(tmp_path):
    repository = ApplicationRepository(tmp_path / "ask-katy.private.db")
    application = {
        "id": "existing-answer",
        "status": "draft",
        "page": {"company": "Example", "role": "Consultant"},
        "profile_answers": [{
            "question": "What SaaS work have you done?",
            "answer": "Implemented enterprise SaaS workflows.",
        }],
    }
    repository.import_legacy(application)

    # Simulates the version-two database state immediately before the upgrade.
    with repository.database.connect() as connection:
        connection.execute("DELETE FROM profile_facts")
        connection.execute("PRAGMA user_version = 2")
    upgraded = ApplicationRepository(repository.path)

    assert upgraded.list_profile_facts()[0]["answer"] == (
        "Implemented enterprise SaaS workflows."
    )
