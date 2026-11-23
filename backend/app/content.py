import hashlib
import json
import re
import secrets
import sqlite3
from pathlib import Path

from .database import PrivateDatabase


# Converts a private URL token into the one-way value stored in the database.
def token_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


# Stores and retrieves each job application from the private SQLite database.
class ApplicationRepository:
    # Uses the production database unless a test supplies a temporary file.
    def __init__(self, path: Path | None = None):
        self.database = PrivateDatabase(path)
        self.path = self.database.path

    # Converts a company or role name into a short URL-safe label.
    def _slug(self, value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:70]

    # Chooses a readable default path and adds a small number only when it is already used.
    def _available_public_path(
        self, connection: sqlite3.Connection, company: str, role: str
    ) -> str:
        base = f"{self._slug(company)}/{self._slug(role)}"
        candidate = base
        suffix = 2
        while connection.execute(
            "SELECT 1 FROM applications WHERE public_path = ?", (candidate,)
        ).fetchone():
            candidate = f"{base}-{suffix}"
            suffix += 1
        return candidate

    # Reads every reusable fact Katy has approved for use across applications.
    def _profile_facts(self, connection: sqlite3.Connection) -> list[dict]:
        return [
            {
                "id": item["id"],
                "question": item["question"],
                "answer": item["answer"],
            }
            for item in connection.execute(
                "SELECT id, question, answer FROM profile_facts ORDER BY updated_at DESC, id DESC"
            )
        ]

    # Reads Katy's approved skills with optional proficiency and experience details.
    def _profile_skills(self, connection: sqlite3.Connection) -> list[dict]:
        return [
            {
                "id": item["id"],
                "name": item["name"],
                "proficiency": item["proficiency"],
                "years": item["years"],
                "used_at": item["used_at"],
                "detail": item["detail"],
                "evidence_quote": item["evidence_quote"],
            }
            for item in connection.execute(
                """
                SELECT id, name, proficiency, years, used_at, detail, evidence_quote
                FROM profile_skills ORDER BY updated_at DESC, id DESC
                """
            )
        ]

    # Reads approved personal qualities and working-style statements about Katy.
    def _about_facts(self, connection: sqlite3.Connection) -> list[dict]:
        return [
            {
                "id": item["id"],
                "title": item["title"],
                "statement": item["statement"],
                "evidence_quote": item["evidence_quote"],
            }
            for item in connection.execute(
                """
                SELECT id, title, statement, evidence_quote
                FROM about_facts ORDER BY updated_at DESC, id DESC
                """
            )
        ]

    # Reports whether a one-time private-data import has already completed.
    def migration_completed(self, name: str) -> bool:
        with self.database.connect() as connection:
            return connection.execute(
                "SELECT 1 FROM migration_state WHERE name = ?", (name,)
            ).fetchone() is not None

    # Records a completed import so deleted content is never recreated from backups.
    def mark_migration_completed(self, name: str) -> None:
        with self.database.connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO migration_state(name) VALUES (?)", (name,)
            )

    # Reads any question ceilings Katy has saved in the private database.
    def rate_limit_settings(self) -> dict[str, int]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT name, value FROM site_settings
                WHERE name IN ('visitor_limit', 'global_limit')
                """
            )
            return {row["name"]: int(row["value"]) for row in rows}

    # Persists both question ceilings together so they survive an app restart.
    def save_rate_limit_settings(self, settings: dict[str, int]) -> None:
        with self.database.connect() as connection:
            connection.executemany(
                """
                INSERT INTO site_settings(name, value) VALUES (?, ?)
                ON CONFLICT(name) DO UPDATE SET value = excluded.value
                """,
                [
                    ("visitor_limit", settings["visitor_limit"]),
                    ("global_limit", settings["global_limit"]),
                ],
            )

    # Pairs evidence starters with exact approved content while AI handles interest notes.
    def _suggested_answers(
        self,
        accomplishments: list[dict],
    ) -> dict[str, str]:
        answers = {}
        for item in accomplishments:
            if item.get("title", "").strip() and item.get("detail", "").strip():
                question = (
                    "Can you tell me more about Katy’s experience with "
                    f"{item['title'].lower()}?"
                )
                answers[question] = item["detail"].strip()
        return dict(list(answers.items())[:4])

    # Reads an application row and its related evidence into the existing API shape.
    def _hydrate(
        self,
        connection: sqlite3.Connection,
        row: sqlite3.Row,
        include_hash: bool = True,
    ) -> dict:
        application_id = row["id"]
        accomplishments = [
            {"title": item["title"], "detail": item["detail"]}
            for item in connection.execute(
                """
                SELECT title, detail FROM accomplishments
                WHERE application_id = ? ORDER BY position
                """,
                (application_id,),
            )
        ]
        profile_answers = [
            {"question": item["question"], "answer": item["answer"]}
            for item in connection.execute(
                """
                SELECT question, answer FROM profile_answers
                WHERE application_id = ? ORDER BY position
                """,
                (application_id,),
            )
        ]
        fact_ids = [
            item["fact_id"]
            for item in connection.execute(
                """
                SELECT fact_id FROM application_facts
                WHERE application_id = ? ORDER BY position
                """,
                (application_id,),
            )
        ]
        mock_answers = {
            item["name"]: item["answer"]
            for item in connection.execute(
                """
                SELECT name, answer FROM mock_answers
                WHERE application_id = ? ORDER BY name
                """,
                (application_id,),
            )
        }
        suggested_answers = self._suggested_answers(accomplishments)
        suggested_questions = []
        if row["company_interest"].strip():
            suggested_questions.append(
                f"Why is Katy interested in {row['company']}?"
            )
        suggested_questions.append("How does Ask Katy work?")
        suggested_questions.extend(suggested_answers)
        try:
            resume = json.loads(row["resume_json"] or "{}")
        except (TypeError, json.JSONDecodeError):
            resume = {}
        if not resume.get("summary"):
            resume = {
                "summary": row["introduction"].strip()
                or "Résumé draft pending Katy’s review.",
                "skills": [],
                "experience": [],
                "education": [],
            }
        application = {
            "id": application_id,
            "status": row["status"],
            "public_path": row["public_path"],
            "page": {
                "company": row["company"],
                "role": row["role"],
                "eyebrow": row["eyebrow"],
                "headline": row["headline"],
                "introduction": row["introduction"],
                "accomplishments": accomplishments,
                "suggested_questions": suggested_questions[:4],
            },
            "job_description": row["job_description"],
            "company_interest": row["company_interest"],
            "resume": resume,
            "resume_source": (
                "uploaded" if row["uploaded_resume_content"] else "generated"
            ),
            "uploaded_resume_filename": row["uploaded_resume_filename"],
            "cover_letter_pitch": row["cover_letter_pitch"].strip()
            or resume["summary"],
            "profile_answers": profile_answers,
            "fact_ids": fact_ids,
            "mock_answers": mock_answers,
            "suggested_answers": suggested_answers,
            "shared_profile": self._profile_facts(connection),
            "shared_skills": self._profile_skills(connection),
            "about_katy": self._about_facts(connection),
        }
        if include_hash:
            application["access_path_hash"] = row["access_path_hash"]
        return application

    # Inserts all child evidence for a newly created or migrated application.
    def _insert_children(
        self,
        connection: sqlite3.Connection,
        application_id: str,
        application: dict,
    ) -> None:
        page = application.get("page", {})
        connection.executemany(
            """
            INSERT INTO accomplishments(application_id, position, title, detail)
            VALUES (?, ?, ?, ?)
            """,
            [
                (application_id, position, item["title"], item["detail"])
                for position, item in enumerate(page.get("accomplishments", []))
            ],
        )
        connection.executemany(
            """
            INSERT INTO profile_answers(application_id, position, question, answer)
            VALUES (?, ?, ?, ?)
            """,
            [
                (application_id, position, item["question"], item["answer"])
                for position, item in enumerate(application.get("profile_answers", []))
            ],
        )
        connection.executemany(
            """
            INSERT INTO application_facts(application_id, position, fact_id)
            VALUES (?, ?, ?)
            """,
            [
                (application_id, position, fact_id)
                for position, fact_id in enumerate(application.get("fact_ids", []))
            ],
        )
        connection.executemany(
            """
            INSERT INTO mock_answers(application_id, name, answer)
            VALUES (?, ?, ?)
            """,
            [
                (application_id, name, answer)
                for name, answer in application.get("mock_answers", {}).items()
            ],
        )

    # Inserts a complete application if its ID has not already been imported.
    def import_legacy(self, application: dict) -> bool:
        page = application.get("page", {})
        uploaded_resume = application.get("uploaded_resume") or {}
        with self.database.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO applications(
                    id, status, access_path_hash, public_path, company, role, eyebrow,
                    headline, introduction, job_description, company_interest,
                    resume_json, cover_letter_pitch, uploaded_resume_filename,
                    uploaded_resume_content
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO NOTHING
                """,
                (
                    application["id"],
                    application.get("status", "draft"),
                    application.get("access_path_hash"),
                    application.get("public_path"),
                    page.get("company", ""),
                    page.get("role", ""),
                    page.get("eyebrow", ""),
                    page.get("headline", ""),
                    page.get("introduction", ""),
                    application.get("job_description", ""),
                    application.get("company_interest", ""),
                    json.dumps(application.get("resume", {})),
                    application.get("cover_letter_pitch", ""),
                    uploaded_resume.get("filename", ""),
                    uploaded_resume.get("content"),
                ),
            )
            if cursor.rowcount == 0:
                return False
            self._insert_children(connection, application["id"], application)
            return True

    # Resolves a readable vanity path only when its application is currently published.
    def find(self, access_path: str) -> dict | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM applications
                WHERE public_path = ? AND status = 'published'
                """,
                (access_path,),
            ).fetchone()
            return self._hydrate(connection, row) if row else None

    # Resolves any saved vanity path for a signed-in admin preview.
    def find_for_admin_preview(self, public_path: str) -> dict | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM applications WHERE public_path = ?",
                (public_path,),
            ).fetchone()
            return self._hydrate(connection, row) if row else None

    # Returns a published application by ID for an authorized chat session.
    def by_id(self, application_id: str) -> dict | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM applications WHERE id = ? AND status = 'published'",
                (application_id,),
            ).fetchone()
            return self._hydrate(connection, row) if row else None

    # Reads the private PDF bytes only for an API route that already checked access.
    def uploaded_resume(self, application_id: str) -> dict | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT uploaded_resume_filename, uploaded_resume_content
                FROM applications WHERE id = ?
                """,
                (application_id,),
            ).fetchone()
            if not row or not row["uploaded_resume_content"]:
                return None
            return {
                "filename": row["uploaded_resume_filename"],
                "content": bytes(row["uploaded_resume_content"]),
            }

    # Adds, replaces, or removes the private PDF attached to one application.
    def update_uploaded_resume(
        self, application_id: str, resume: dict | None
    ) -> dict | None:
        with self.database.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE applications
                SET uploaded_resume_filename = ?, uploaded_resume_content = ?
                WHERE id = ?
                """,
                (
                    resume["filename"] if resume else "",
                    resume["content"] if resume else None,
                    application_id,
                ),
            )
            if cursor.rowcount != 1:
                return None
            row = connection.execute(
                "SELECT * FROM applications WHERE id = ?", (application_id,)
            ).fetchone()
            return self._hydrate(connection, row, include_hash=False)

    # Returns an application to the admin without exposing its legacy link hash.
    def for_admin(self, application_id: str) -> dict | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM applications WHERE id = ?",
                (application_id,),
            ).fetchone()
            return self._hydrate(connection, row, include_hash=False) if row else None

    # Lists safe application summaries for the private admin studio.
    def list_for_admin(self) -> list[dict]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, status, public_path, company, role, company_interest,
                       uploaded_resume_filename
                FROM applications ORDER BY company, role
                """
            ).fetchall()
            return [
                {
                    "id": row["id"],
                    "status": row["status"],
                    "public_path": row["public_path"],
                    "company_interest_ready": bool(row["company_interest"].strip()),
                    "uploaded_resume_filename": row["uploaded_resume_filename"],
                    "page": {"company": row["company"], "role": row["role"]},
                }
                for row in rows
            ]

    # Lists Katy's reusable, application-independent professional knowledge.
    def list_profile_facts(self) -> list[dict]:
        with self.database.connect() as connection:
            return self._profile_facts(connection)

    # Lists every reusable knowledge category for admin review and AI grounding.
    def list_profile_knowledge(self) -> dict:
        with self.database.connect() as connection:
            return {
                "skills": self._profile_skills(connection),
                "about": self._about_facts(connection),
                "facts": self._profile_facts(connection),
            }

    # Saves or updates one reusable answer based on its normalized question.
    def save_profile_fact(
        self,
        question: str,
        answer: str,
        source_application_id: str | None = None,
    ) -> None:
        normalized_question = " ".join(question.casefold().split())
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO profile_facts(
                    question, answer, normalized_question, source_application_id
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(normalized_question) DO UPDATE SET
                    question = excluded.question,
                    answer = excluded.answer,
                    source_application_id = excluded.source_application_id,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (question.strip(), answer.strip(), normalized_question, source_application_id),
            )

    # Saves or updates one skill without inventing omitted proficiency details.
    def save_profile_skill(self, skill: dict) -> None:
        name = skill["name"].strip()
        normalized_name = " ".join(name.casefold().split())
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO profile_skills(
                    name, normalized_name, proficiency, years, used_at, detail,
                    evidence_quote
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(normalized_name) DO UPDATE SET
                    name = excluded.name,
                    proficiency = excluded.proficiency,
                    years = excluded.years,
                    used_at = excluded.used_at,
                    detail = excluded.detail,
                    evidence_quote = excluded.evidence_quote,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    name,
                    normalized_name,
                    skill.get("proficiency"),
                    skill.get("years"),
                    skill.get("used_at", "").strip(),
                    skill.get("detail", "").strip(),
                    skill.get("evidence_quote", "").strip(),
                ),
            )

    # Saves or updates one About Katy statement independently from skill metadata.
    def save_about_fact(self, fact: dict) -> None:
        title = fact["title"].strip()
        normalized_title = " ".join(title.casefold().split())
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO about_facts(
                    title, statement, normalized_title, evidence_quote
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(normalized_title) DO UPDATE SET
                    title = excluded.title,
                    statement = excluded.statement,
                    evidence_quote = excluded.evidence_quote,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    title,
                    fact["statement"].strip(),
                    normalized_title,
                    fact.get("evidence_quote", "").strip(),
                ),
            )

    # Updates one reusable fact by ID so its question and answer remain editable.
    def update_profile_fact(self, fact_id: int, question: str, answer: str) -> dict | None:
        normalized_question = " ".join(question.casefold().split())
        with self.database.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE profile_facts
                SET question = ?, answer = ?, normalized_question = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (question.strip(), answer.strip(), normalized_question, fact_id),
            )
            if cursor.rowcount != 1:
                return None
            return dict(connection.execute(
                "SELECT id, question, answer FROM profile_facts WHERE id = ?",
                (fact_id,),
            ).fetchone())

    # Updates every editable field on one saved skill while preserving its ID.
    def update_profile_skill(self, skill_id: int, skill: dict) -> dict | None:
        name = skill["name"].strip()
        normalized_name = " ".join(name.casefold().split())
        with self.database.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE profile_skills
                SET name = ?, normalized_name = ?, proficiency = ?, years = ?,
                    used_at = ?, detail = ?, evidence_quote = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    name,
                    normalized_name,
                    skill.get("proficiency"),
                    skill.get("years"),
                    skill.get("used_at", "").strip(),
                    skill.get("detail", "").strip(),
                    skill.get("evidence_quote", "").strip(),
                    skill_id,
                ),
            )
            if cursor.rowcount != 1:
                return None
            return dict(connection.execute(
                """
                SELECT id, name, proficiency, years, used_at, detail, evidence_quote
                FROM profile_skills WHERE id = ?
                """,
                (skill_id,),
            ).fetchone())

    # Updates one About Katy item without turning it into skill-like data.
    def update_about_fact(self, fact_id: int, fact: dict) -> dict | None:
        title = fact["title"].strip()
        normalized_title = " ".join(title.casefold().split())
        with self.database.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE about_facts
                SET title = ?, statement = ?, normalized_title = ?, evidence_quote = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    title,
                    fact["statement"].strip(),
                    normalized_title,
                    fact.get("evidence_quote", "").strip(),
                    fact_id,
                ),
            )
            if cursor.rowcount != 1:
                return None
            return dict(connection.execute(
                "SELECT id, title, statement, evidence_quote FROM about_facts WHERE id = ?",
                (fact_id,),
            ).fetchone())

    # Saves a corrected recruiter answer only inside its matching application.
    def save_application_answer(self, application_id: str, question: str, answer: str) -> None:
        with self.database.connect() as connection:
            existing = connection.execute(
                """
                SELECT position FROM profile_answers
                WHERE application_id = ? AND lower(trim(question)) = lower(trim(?))
                """,
                (application_id, question),
            ).fetchone()
            if existing:
                connection.execute(
                    """
                    UPDATE profile_answers SET question = ?, answer = ?
                    WHERE application_id = ? AND position = ?
                    """,
                    (question.strip(), answer.strip(), application_id, existing["position"]),
                )
                return
            next_position = connection.execute(
                "SELECT COALESCE(MAX(position), -1) + 1 FROM profile_answers WHERE application_id = ?",
                (application_id,),
            ).fetchone()[0]
            connection.execute(
                """
                INSERT INTO profile_answers(application_id, position, question, answer)
                VALUES (?, ?, ?, ?)
                """,
                (application_id, next_position, question.strip(), answer.strip()),
            )

    # Removes one reusable profile fact without changing its original application.
    def delete_profile_fact(self, fact_id: int) -> dict | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT id FROM profile_facts WHERE id = ?", (fact_id,)
            ).fetchone()
            if not row:
                return None
            connection.execute("DELETE FROM profile_facts WHERE id = ?", (fact_id,))
            return {"id": fact_id}

    # Removes one structured skill without changing other reusable knowledge.
    def delete_profile_skill(self, skill_id: int) -> dict | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT id FROM profile_skills WHERE id = ?", (skill_id,)
            ).fetchone()
            if not row:
                return None
            connection.execute("DELETE FROM profile_skills WHERE id = ?", (skill_id,))
            return {"id": skill_id}

    # Removes one About Katy statement without changing skill or application data.
    def delete_about_fact(self, fact_id: int) -> dict | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT id FROM about_facts WHERE id = ?", (fact_id,)
            ).fetchone()
            if not row:
                return None
            connection.execute("DELETE FROM about_facts WHERE id = ?", (fact_id,))
            return {"id": fact_id}

    # Permanently deletes one application and its separately stored question history.
    def delete(self, application_id: str) -> dict | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT id FROM applications WHERE id = ?",
                (application_id,),
            ).fetchone()
            if not row:
                return None
            connection.execute(
                "DELETE FROM question_logs WHERE application_id = ?",
                (application_id,),
            )
            connection.execute(
                "DELETE FROM applications WHERE id = ?",
                (application_id,),
            )
            return {"id": application_id}

    # Creates a private draft with a readable company-and-role vanity path.
    def create_draft(self, intake: dict) -> dict:
        slug = self._slug(intake["company"])
        application_id = f"{slug}-{secrets.token_hex(4)}"
        with self.database.connect() as connection:
            public_path = self._available_public_path(
                connection, intake["company"], intake["role"]
            )
        application = {
            "id": application_id,
            "status": "draft",
            "access_path_hash": None,
            "public_path": public_path,
            "page": {
                "company": intake["company"],
                "role": intake["role"],
                "eyebrow": f"A NOTE FOR {intake['company'].upper()}",
                "headline": "Technical depth, translated into customer results.",
                "introduction": intake.get("notes")
                or "Draft introduction pending Katy’s review.",
                "accomplishments": [],
            },
            "job_description": intake["job_description"],
            "company_interest": intake["company_interest"],
            "resume": intake["documents"]["resume"],
            "cover_letter_pitch": intake["documents"]["cover_letter_pitch"],
            "uploaded_resume": intake.get("uploaded_resume") or {},
            "profile_answers": intake.get("answers", []),
            "fact_ids": [],
            "mock_answers": {},
        }
        self.import_legacy(application)
        for answer in intake.get("answers", []):
            if answer.get("reusable", True):
                self.save_profile_fact(
                    answer["question"], answer["answer"], application_id
                )
        return {"id": application_id, "public_path": public_path, "status": "draft"}

    # Changes visibility while preserving the application's current vanity path.
    def set_status(self, application_id: str, status: str) -> dict | None:
        if status not in {"draft", "published"}:
            raise ValueError("Unsupported application status")
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM applications WHERE id = ?",
                (application_id,),
            ).fetchone()
            if not row:
                return None
            if not row["public_path"]:
                raise ValueError("Choose a URL before publishing")
            if status == "published" and not row["company_interest"].strip():
                raise ValueError(
                    "Add Katy's company-interest notes before publishing."
                )
            if status == "published" and not row["uploaded_resume_content"]:
                try:
                    resume = json.loads(row["resume_json"] or "{}")
                except (TypeError, json.JSONDecodeError):
                    resume = {}
                experience = (
                    resume.get("experience", [])
                    if isinstance(resume, dict)
                    else []
                )
                if not isinstance(experience, list) or not experience:
                    raise ValueError(
                        "Add at least one work experience entry to the generated "
                        "résumé before publishing."
                    )
            connection.execute(
                "UPDATE applications SET status = ? WHERE id = ?",
                (status, application_id),
            )
            updated = dict(row)
            updated["status"] = status
            return updated

    # Disables employer access while retaining the path in the private admin history.
    def revoke(self, application_id: str) -> dict | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT id FROM applications WHERE id = ?",
                (application_id,),
            ).fetchone()
            if not row:
                return None
            connection.execute(
                """
                UPDATE applications
                SET status = 'revoked', access_path_hash = NULL
                WHERE id = ?
                """,
                (application_id,),
            )
            return {"id": application_id, "status": "revoked"}

    # Corrects one application's saved content without changing its URL or shared profile.
    def update_application_content(
        self, application_id: str, content: dict
    ) -> dict | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT id FROM applications WHERE id = ?",
                (application_id,),
            ).fetchone()
            if not row:
                return None
            company = content["company"].strip()
            connection.execute(
                """
                UPDATE applications
                SET company = ?, role = ?, eyebrow = ?, introduction = ?,
                    job_description = ?, company_interest = ?, resume_json = ?,
                    cover_letter_pitch = ?
                WHERE id = ?
                """,
                (
                    company,
                    content["role"].strip(),
                    f"A NOTE FOR {company.upper()}",
                    content["introduction"].strip(),
                    content["job_description"].strip(),
                    content["company_interest"].strip(),
                    json.dumps(content["resume"]),
                    content["cover_letter_pitch"].strip(),
                    application_id,
                ),
            )
            connection.execute(
                "DELETE FROM profile_answers WHERE application_id = ?",
                (application_id,),
            )
            connection.executemany(
                """
                INSERT INTO profile_answers(application_id, position, question, answer)
                VALUES (?, ?, ?, ?)
                """,
                [
                    (
                        application_id,
                        position,
                        item["question"].strip(),
                        item["answer"].strip(),
                    )
                    for position, item in enumerate(content.get("answers", []))
                ],
            )
            updated = connection.execute(
                "SELECT * FROM applications WHERE id = ?",
                (application_id,),
            ).fetchone()
            return self._hydrate(connection, updated, include_hash=False)

    # Replaces only one application's generated documents after Katy confirms regeneration.
    def update_application_documents(
        self, application_id: str, documents: dict
    ) -> dict | None:
        with self.database.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE applications
                SET resume_json = ?, cover_letter_pitch = ?,
                    status = CASE
                        WHEN status = 'published' THEN 'draft'
                        ELSE status
                    END
                WHERE id = ?
                """,
                (
                    json.dumps(documents["resume"]),
                    documents["cover_letter_pitch"].strip(),
                    application_id,
                ),
            )
            if cursor.rowcount != 1:
                return None
            row = connection.execute(
                "SELECT * FROM applications WHERE id = ?", (application_id,)
            ).fetchone()
            return self._hydrate(connection, row, include_hash=False)

    # Replaces an application's vanity path and invalidates any legacy random link.
    def update_public_path(
        self, application_id: str, public_path: str
    ) -> dict | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT id, status FROM applications WHERE id = ?",
                (application_id,),
            ).fetchone()
            if not row:
                return None
            try:
                connection.execute(
                    """
                    UPDATE applications
                    SET public_path = ?, access_path_hash = NULL
                    WHERE id = ?
                    """,
                    (public_path, application_id),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("That URL is already in use") from exc
            return {
                "id": application_id,
                "public_path": public_path,
                "status": row["status"],
            }
