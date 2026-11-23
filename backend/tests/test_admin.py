import base64

import app.main as main_module
import pytest
from app.content import ApplicationRepository
from app.main import app
from app.question_log import QuestionLog
from app.rate_limit import SlidingWindowRateLimiter
from fastapi.testclient import TestClient


class IntakeResponder:
    # Returns a proofread introduction alongside the predictable intake questions.
    def intake_review(self, intake):
        return {
            "introduction": "Katy’s grammatically polished application introduction.",
            "questions": self.intake_questions(intake),
        }

    # Returns a predictable grounded intake review without calling OpenAI.
    def intake_questions(self, intake):
        return [{
            "question": f"What evidence supports the {intake['role']} requirements?",
            "status": "new",
            "suggested_answer": "",
            "guidance": "No approved answer covers this requirement yet.",
            "source_ids": [],
        }]

    # Returns predictable job documents without making a provider request.
    def application_documents(self, intake):
        return {
            "resume": {
                "summary": "Customer-focused technical implementation specialist.",
                "skills": ["SaaS implementation", "API integrations"],
                "experience": [{
                    "company": "Example Company",
                    "role": "Implementation Specialist",
                    "dates": "",
                    "bullets": ["Implemented truthful customer workflows."],
                }],
                "education": [],
            },
            "cover_letter_pitch": (
                "I bring customer-focused technical implementation experience"
            ),
        }

    # Returns one predictable candidate without writing it to the test database.
    def profile_facts(self, source_text, existing_facts):
        assert "enterprise SaaS" in source_text
        assert existing_facts == []
        return [{
            "question": "What SaaS experience does Katy have?",
            "answer": "Katy implemented enterprise SaaS workflows.",
            "evidence_quote": "enterprise SaaS implementation experience",
        }]

    # Classifies imported material into skills, about facts, and legacy Q&A facts.
    def profile_knowledge(self, source_text, existing_knowledge):
        assert "enterprise SaaS" in source_text
        return {
            "skills": [{
                "name": "SaaS implementation",
                "proficiency": None,
                "years": None,
                "used_at": "",
                "detail": "Implemented enterprise SaaS workflows.",
                "evidence_quote": "enterprise SaaS implementation experience",
            }],
            "about": [{
                "title": "Customer advocate",
                "statement": "Katy centers customer needs while solving technical problems.",
                "evidence_quote": "enterprise SaaS implementation experience",
            }],
            "facts": [],
        }

class QuestionLogStub:
    # Returns one predictable unanswered question for the admin review test.
    def page(self, page, page_size):
        questions = [{"question": "What is missing?", "answer": "Not known", "outcome": "unanswered", "application_id": "one", "timestamp": "2026-01-01T00:00:00+00:00"}]
        return {"questions": questions, "page": page, "page_size": page_size, "total": 1, "total_pages": 1}


# Prevents admin tests from making real OpenAI calls while creating private drafts.
@pytest.fixture(autouse=True)
def stub_admin_responder(monkeypatch):
    monkeypatch.setattr(main_module, "responder", IntakeResponder())


# Builds a complete, valid application request shared by the admin tests.
def payload():
    return {
        "company": "Example Company",
        "role": "Implementation Specialist",
        "job_description": "A detailed job description " * 8,
        "company_interest": (
            "Example Company builds tools that make complex customer work easier, "
            "which matches Katy's interest in useful, people-centered technology."
        ),
        "notes": "Katy's approved starting notes.",
    }


# Configures the test password and signs the test browser into the admin studio.
def login(client, monkeypatch):
    monkeypatch.setenv("ASK_KATY_ADMIN_PASSWORD", "correct-horse-battery")
    return client.post("/v1/admin/login", json={"password": "correct-horse-battery"})


# Confirms private admin actions reject browsers without a valid login cookie.
def test_admin_routes_require_authentication():
    client = TestClient(app)
    assert client.get("/v1/admin/settings/rate-limits").status_code == 401
    assert client.put(
        "/v1/admin/settings/rate-limits",
        json={"visitor_limit": 20, "global_limit": 120},
    ).status_code == 401
    assert client.post("/v1/admin/intake/questions", json=payload()).status_code == 401
    assert client.delete("/v1/admin/questions").status_code == 401
    assert client.post("/v1/admin/applications", json={**payload(), "answers": []}).status_code == 401
    assert client.get("/v1/admin/applications/not-mine/resume").status_code == 401
    assert client.delete("/v1/admin/applications/not-mine").status_code == 401
    assert client.post(
        "/v1/admin/profile/import/preview",
        json={"pasted_text": "Katy has enterprise SaaS experience."},
    ).status_code == 401
    assert client.post(
        "/v1/admin/profile/import/approve",
        json={"facts": [{"question": "What?", "answer": "Something true."}]},
    ).status_code == 401


# Confirms an incorrect admin password cannot start a session.
def test_admin_login_rejects_wrong_password(monkeypatch):
    monkeypatch.setenv("ASK_KATY_ADMIN_PASSWORD", "correct-horse-battery")
    response = TestClient(app).post("/v1/admin/login", json={"password": "definitely-wrong"})
    assert response.status_code == 401


# Confirms a foreign website cannot submit a browser login or admin mutation.
def test_admin_routes_reject_unapproved_browser_origins(monkeypatch):
    monkeypatch.setenv("ASK_KATY_ADMIN_PASSWORD", "correct-horse-battery")
    client = TestClient(app)

    login_response = client.post(
        "/v1/admin/login",
        headers={"Origin": "https://attacker.example"},
        json={"password": "correct-horse-battery"},
    )
    update_response = client.put(
        "/v1/admin/settings/rate-limits",
        headers={"Origin": "https://attacker.example"},
        json={"visitor_limit": 20, "global_limit": 120},
    )

    assert login_response.status_code == 403
    assert "set-cookie" not in login_response.headers
    assert update_response.status_code == 403
    assert login_response.json()["detail"] == "Unapproved admin request origin"


# Confirms the configured frontend origin can still sign in and update private data.
def test_admin_routes_accept_configured_browser_origin(monkeypatch):
    monkeypatch.setenv("ASK_KATY_ADMIN_PASSWORD", "correct-horse-battery")
    client = TestClient(app)
    headers = {"Origin": "http://localhost:5173"}

    assert client.post(
        "/v1/admin/login",
        headers=headers,
        json={"password": "correct-horse-battery"},
    ).status_code == 200
    assert client.put(
        "/v1/admin/settings/rate-limits",
        headers=headers,
        json={"visitor_limit": 20, "global_limit": 120},
    ).status_code == 200


# Confirms non-ASCII input is treated as a wrong password instead of causing a server error.
def test_admin_login_safely_rejects_unicode_passwords(monkeypatch):
    monkeypatch.setenv("ASK_KATY_ADMIN_PASSWORD", "correct-horse-battery")
    response = TestClient(app).post("/v1/admin/login", json={"password": "incorrect-☃"})
    assert response.status_code == 401


# Confirms repeated failed sign-ins are throttled without blocking a later correct password.
def test_admin_login_throttles_repeated_failures(monkeypatch):
    clock = lambda: 100.0
    monkeypatch.setattr(
        main_module,
        "admin_login_visitor_limiter",
        SlidingWindowRateLimiter(limit=2, window_seconds=900, clock=clock),
    )
    monkeypatch.setattr(
        main_module,
        "admin_login_global_limiter",
        SlidingWindowRateLimiter(limit=20, window_seconds=900, clock=clock),
    )
    monkeypatch.setenv("ASK_KATY_ADMIN_PASSWORD", "correct-horse-battery")
    client = TestClient(app)

    assert client.post("/v1/admin/login", json={"password": "wrong-value"}).status_code == 401
    assert client.post("/v1/admin/login", json={"password": "wrong-value"}).status_code == 401
    blocked = client.post("/v1/admin/login", json={"password": "wrong-value"})

    assert blocked.status_code == 429
    assert blocked.headers["Retry-After"] == "900"
    assert client.post(
        "/v1/admin/login",
        json={"password": "correct-horse-battery"},
    ).status_code == 200


# Confirms the browser can restore a still-valid eight-hour admin session after refresh.
def test_admin_session_can_be_restored_from_cookie(monkeypatch):
    client = TestClient(app)
    assert client.get("/v1/admin/session").status_code == 401
    assert login(client, monkeypatch).status_code == 200
    assert client.get("/v1/admin/session").json() == {"authenticated": True}


# Confirms logout expires the signed cookie and immediately blocks private routes.
def test_admin_logout_ends_the_current_session(monkeypatch):
    client = TestClient(app)
    assert login(client, monkeypatch).status_code == 200

    response = client.post("/v1/admin/logout")

    assert response.status_code == 200
    assert response.json() == {"authenticated": False}
    assert "ask_katy_admin=" in response.headers["set-cookie"]
    assert "Max-Age=0" in response.headers["set-cookie"]
    assert client.get("/v1/admin/session").status_code == 401


# Confirms Katy can persist safe question limits and apply them immediately.
def test_admin_can_edit_public_question_limits(tmp_path, monkeypatch):
    repository = ApplicationRepository(tmp_path / "ask-katy.private.db")
    visitor_limiter = SlidingWindowRateLimiter(limit=20, window_seconds=600)
    global_limiter = SlidingWindowRateLimiter(limit=120, window_seconds=3600)
    monkeypatch.setattr(main_module, "repo", repository)
    monkeypatch.setattr(main_module, "chat_visitor_limiter", visitor_limiter)
    monkeypatch.setattr(main_module, "chat_global_limiter", global_limiter)
    client = TestClient(app)
    assert login(client, monkeypatch).status_code == 200

    initial = client.get("/v1/admin/settings/rate-limits")
    updated = client.put(
        "/v1/admin/settings/rate-limits",
        json={"visitor_limit": 8, "global_limit": 75},
    )

    assert initial.json() == {
        "visitor_limit": 20,
        "visitor_window_seconds": 600,
        "global_limit": 120,
        "global_window_seconds": 3600,
    }
    assert updated.status_code == 200
    assert updated.json()["visitor_limit"] == 8
    assert updated.json()["global_limit"] == 75
    assert visitor_limiter.limit == 8
    assert global_limiter.limit == 75
    assert repository.rate_limit_settings() == {
        "visitor_limit": 8,
        "global_limit": 75,
    }


# Confirms the admin cannot accidentally remove the cost-protection ceilings.
def test_admin_question_limits_have_safe_bounds(monkeypatch):
    client = TestClient(app)
    assert login(client, monkeypatch).status_code == 200

    too_high = client.put(
        "/v1/admin/settings/rate-limits",
        json={"visitor_limit": 101, "global_limit": 120},
    )
    inconsistent = client.put(
        "/v1/admin/settings/rate-limits",
        json={"visitor_limit": 20, "global_limit": 10},
    )

    assert too_high.status_code == 422
    assert inconsistent.status_code == 422


# Confirms a signed-in admin can request tailored evidence questions.
def test_authenticated_admin_gets_ai_questions(monkeypatch):
    monkeypatch.setattr(main_module, "responder", IntakeResponder())
    client = TestClient(app)
    assert login(client, monkeypatch).status_code == 200
    response = client.post("/v1/admin/intake/questions", json=payload())
    assert response.status_code == 200
    assert response.json()["introduction"] == (
        "Katy’s grammatically polished application introduction."
    )
    assert response.json()["questions"] == [{
        "question": "What evidence supports the Implementation Specialist requirements?",
        "status": "new",
        "suggested_answer": "",
        "guidance": "No approved answer covers this requirement yet.",
        "source_ids": [],
    }]


# Confirms draft content is private and receives a readable default URL.
def test_authenticated_admin_creates_gitignored_private_draft(tmp_path, monkeypatch):
    repository = ApplicationRepository(tmp_path / "ask-katy.private.db")
    monkeypatch.setattr(main_module, "repo", repository)
    client = TestClient(app)
    assert login(client, monkeypatch).status_code == 200
    response = client.post(
        "/v1/admin/applications",
        json={**payload(), "answers": [{"question": "What did you build?", "answer": "A truthful example."}]},
    )
    assert response.status_code == 200
    result = response.json()
    data = repository.for_admin(result["id"])
    assert data["status"] == "draft"
    assert data["page"]["company"] == "Example Company"
    assert data["company_interest"].startswith("Example Company builds tools")
    assert data["page"]["suggested_questions"][0] == (
        "Why is Katy interested in Example Company?"
    )
    assert "Why is Katy interested in Example Company?" not in data["suggested_answers"]
    assert data["profile_answers"][0]["answer"] == "A truthful example."
    assert result["public_path"] == "example-company/implementation-specialist"


# Confirms an optional existing PDF is stored inside the private application database.
def test_admin_can_attach_an_existing_pdf_resume_to_a_new_application(
    tmp_path, monkeypatch
):
    repository = ApplicationRepository(tmp_path / "ask-katy.private.db")
    monkeypatch.setattr(main_module, "repo", repository)
    client = TestClient(app)
    assert login(client, monkeypatch).status_code == 200
    pdf = b"%PDF-1.7\n% existing resume\n"

    response = client.post(
        "/v1/admin/applications",
        json={
            **payload(),
            "answers": [],
            "uploaded_resume": {
                "filename": "Katy-Henning-Resume.pdf",
                "file_base64": base64.b64encode(pdf).decode(),
            },
        },
    )

    assert response.status_code == 200
    application = repository.for_admin(response.json()["id"])
    assert application["uploaded_resume_filename"] == "Katy-Henning-Resume.pdf"
    assert repository.uploaded_resume(application["id"]) == {
        "filename": "Katy-Henning-Resume.pdf",
        "content": pdf,
    }
    preview = client.get(f"/v1/admin/applications/{application['id']}/resume")
    assert preview.status_code == 200
    assert preview.content == pdf
    assert preview.headers["x-content-type-options"] == "nosniff"


# Confirms a renamed non-PDF cannot be saved or exposed as a recruiter document.
def test_admin_rejects_an_invalid_uploaded_resume(tmp_path, monkeypatch):
    repository = ApplicationRepository(tmp_path / "ask-katy.private.db")
    monkeypatch.setattr(main_module, "repo", repository)
    client = TestClient(app)
    assert login(client, monkeypatch).status_code == 200

    response = client.post(
        "/v1/admin/applications",
        json={
            **payload(),
            "answers": [],
            "uploaded_resume": {
                "filename": "not-really-a-resume.pdf",
                "file_base64": base64.b64encode(b"plain text").decode(),
            },
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Choose a valid PDF résumé."
    assert repository.list_for_admin() == []


# Confirms an existing application can add, replace, and remove its private PDF.
def test_admin_can_manage_a_premade_resume_for_an_existing_application(
    tmp_path, monkeypatch
):
    repository = ApplicationRepository(tmp_path / "ask-katy.private.db")
    monkeypatch.setattr(main_module, "repo", repository)
    client = TestClient(app)
    assert login(client, monkeypatch).status_code == 200
    created = client.post(
        "/v1/admin/applications", json={**payload(), "answers": []}
    ).json()
    pdf = b"%PDF-1.7\n% replacement resume\n"

    uploaded = client.put(
        f"/v1/admin/applications/{created['id']}/resume",
        json={
            "filename": "Katy-Henning-Solutions-Resume.pdf",
            "file_base64": base64.b64encode(pdf).decode(),
        },
    )

    assert uploaded.status_code == 200
    assert uploaded.json()["uploaded_resume_filename"] == (
        "Katy-Henning-Solutions-Resume.pdf"
    )
    assert uploaded.json()["resume_source"] == "uploaded"
    assert repository.uploaded_resume(created["id"])["content"] == pdf

    removed = client.delete(
        f"/v1/admin/applications/{created['id']}/resume"
    )

    assert removed.status_code == 200
    assert removed.json()["uploaded_resume_filename"] == ""
    assert removed.json()["resume_source"] == "generated"
    assert repository.uploaded_resume(created["id"]) is None


# Confirms an existing application can replace its documents from current knowledge.
def test_admin_can_regenerate_application_documents(tmp_path, monkeypatch):
    repository = ApplicationRepository(tmp_path / "ask-katy.private.db")
    monkeypatch.setattr(main_module, "repo", repository)
    client = TestClient(app)
    assert login(client, monkeypatch).status_code == 200
    created = client.post(
        "/v1/admin/applications", json={**payload(), "answers": []}
    ).json()
    assert client.post(
        f"/v1/admin/applications/{created['id']}/publish"
    ).status_code == 200

    regenerated = client.post(
        f"/v1/admin/applications/{created['id']}/documents/regenerate"
    )

    assert regenerated.status_code == 200
    assert regenerated.json()["status"] == "draft"
    assert regenerated.json()["resume"]["summary"].startswith("Customer-focused")
    assert regenerated.json()["cover_letter_pitch"].startswith("I bring")
    saved = repository.for_admin(created["id"])
    assert saved["resume"] == regenerated.json()["resume"]
    assert repository.find(created["public_path"]) is None


# Confirms reusable answers become private Katy knowledge for every later application.
def test_reusable_intake_answers_are_shared_across_applications(tmp_path, monkeypatch):
    repository = ApplicationRepository(tmp_path / "ask-katy.private.db")
    monkeypatch.setattr(main_module, "repo", repository)
    client = TestClient(app)
    assert login(client, monkeypatch).status_code == 200
    first = client.post(
        "/v1/admin/applications",
        json={
            **payload(),
            "answers": [{
                "question": "What SaaS experience do you have?",
                "answer": "I implemented and supported enterprise SaaS workflows.",
                "reusable": True,
            }],
        },
    ).json()
    second = client.post(
        "/v1/admin/applications",
        json={**payload(), "company": "Example Bank", "answers": []},
    ).json()

    shared = repository.for_admin(second["id"])["shared_profile"]
    assert shared == [{
        "id": shared[0]["id"],
        "question": "What SaaS experience do you have?",
        "answer": "I implemented and supported enterprise SaaS workflows.",
    }]
    assert repository.for_admin(first["id"])["profile_answers"][0]["answer"].startswith(
        "I implemented"
    )


# Confirms a job-specific answer remains isolated when Katy turns reuse off.
def test_non_reusable_intake_answer_stays_with_one_application(tmp_path, monkeypatch):
    repository = ApplicationRepository(tmp_path / "ask-katy.private.db")
    monkeypatch.setattr(main_module, "repo", repository)
    client = TestClient(app)
    assert login(client, monkeypatch).status_code == 200
    created = client.post(
        "/v1/admin/applications",
        json={
            **payload(),
            "answers": [{
                "question": "Why this company?",
                "answer": "A company-specific reason.",
                "reusable": False,
            }],
        },
    ).json()

    assert repository.for_admin(created["id"])["shared_profile"] == []


# Confirms Katy can review and remove knowledge from her reusable profile.
def test_admin_can_list_and_delete_shared_profile_facts(tmp_path, monkeypatch):
    repository = ApplicationRepository(tmp_path / "ask-katy.private.db")
    monkeypatch.setattr(main_module, "repo", repository)
    client = TestClient(app)
    assert login(client, monkeypatch).status_code == 200
    client.post(
        "/v1/admin/applications",
        json={
            **payload(),
            "answers": [{
                "question": "Do you know APIs?",
                "answer": "Yes, I have built API integrations.",
                "reusable": True,
            }],
        },
    )

    facts = client.get("/v1/admin/profile").json()["facts"]
    assert facts[0]["answer"] == "Yes, I have built API integrations."
    assert client.delete(f"/v1/admin/profile/{facts[0]['id']}").status_code == 200
    assert client.get("/v1/admin/profile").json()["facts"] == []


# Confirms Katy can correct reusable knowledge without deleting and recreating it.
def test_admin_can_edit_every_reusable_knowledge_type(tmp_path, monkeypatch):
    repository = ApplicationRepository(tmp_path / "ask-katy.private.db")
    monkeypatch.setattr(main_module, "repo", repository)
    client = TestClient(app)
    assert login(client, monkeypatch).status_code == 200
    repository.save_profile_fact("Does Katy know APIs?", "Old API answer")
    repository.save_profile_skill({"name": "Python", "proficiency": "familiar"})
    repository.save_about_fact({"title": "Communication", "statement": "Old statement"})
    knowledge = client.get("/v1/admin/profile").json()

    fact = client.put(
        f"/v1/admin/profile/{knowledge['facts'][0]['id']}",
        json={"question": "Does Katy know APIs?", "answer": "Katy builds API integrations."},
    )
    skill = client.put(
        f"/v1/admin/profile/skills/{knowledge['skills'][0]['id']}",
        json={"name": "Python", "proficiency": "proficient"},
    )
    about = client.put(
        f"/v1/admin/profile/about/{knowledge['about'][0]['id']}",
        json={"title": "Communication", "statement": "Katy explains technical ideas clearly."},
    )

    assert fact.status_code == skill.status_code == about.status_code == 200
    refreshed = client.get("/v1/admin/profile").json()
    assert refreshed["facts"][0]["answer"] == "Katy builds API integrations."
    assert refreshed["skills"][0]["proficiency"] == "proficient"
    assert refreshed["about"][0]["statement"] == "Katy explains technical ideas clearly."


# Confirms an AI import preview cannot silently change Katy's reusable knowledge.
def test_admin_can_preview_then_approve_imported_profile_facts(tmp_path, monkeypatch):
    repository = ApplicationRepository(tmp_path / "ask-katy.private.db")
    monkeypatch.setattr(main_module, "repo", repository)
    monkeypatch.setattr(main_module, "responder", IntakeResponder())
    client = TestClient(app)
    assert login(client, monkeypatch).status_code == 200

    preview = client.post(
        "/v1/admin/profile/import/preview",
        json={"pasted_text": "Katy has enterprise SaaS implementation experience."},
    )

    assert preview.status_code == 200
    assert preview.json()["skills"][0]["name"] == "SaaS implementation"
    assert repository.list_profile_facts() == []

    approval = client.post(
        "/v1/admin/profile/import/approve",
        json={"facts": [{
            "question": "What SaaS experience does Katy have?",
            "answer": "Katy implemented and supported enterprise SaaS workflows.",
        }]},
    )

    assert approval.status_code == 200
    assert approval.json()["saved"] == 1
    assert repository.list_profile_facts()[0]["answer"].startswith("Katy implemented")


# Confirms skills and human qualities save independently with every detail optional.
def test_admin_can_save_structured_skills_and_about_facts(tmp_path, monkeypatch):
    repository = ApplicationRepository(tmp_path / "ask-katy.private.db")
    monkeypatch.setattr(main_module, "repo", repository)
    client = TestClient(app)
    assert login(client, monkeypatch).status_code == 200

    response = client.post(
        "/v1/admin/profile/import/approve",
        json={
            "skills": [
                {
                    "name": "JavaScript",
                    "proficiency": "proficient",
                    "years": 5.5,
                    "used_at": "CD Baby — Software Engineer",
                    "detail": "Built and supported production applications.",
                    "evidence_quote": "five years as a software engineer at CD Baby",
                },
                {"name": "AWS"},
            ],
            "about": [{
                "title": "People skills",
                "statement": "Katy is a thoughtful communicator who makes technical work understandable.",
            }],
            "facts": [],
        },
    )

    assert response.status_code == 200
    assert response.json() == {"saved": 3}
    knowledge = client.get("/v1/admin/profile").json()
    assert knowledge["skills"][0]["name"] in {"JavaScript", "AWS"}
    javascript = next(item for item in knowledge["skills"] if item["name"] == "JavaScript")
    assert javascript["proficiency"] == "proficient"
    assert javascript["years"] == 5.5
    assert "CD Baby" in javascript["used_at"]
    aws = next(item for item in knowledge["skills"] if item["name"] == "AWS")
    assert aws["proficiency"] is None
    assert aws["years"] is None
    assert knowledge["about"][0]["title"] == "People skills"


# Confirms Katy can remove a structured skill or about fact without touching the rest.
def test_admin_can_delete_structured_knowledge(tmp_path, monkeypatch):
    repository = ApplicationRepository(tmp_path / "ask-katy.private.db")
    monkeypatch.setattr(main_module, "repo", repository)
    repository.save_profile_skill({"name": "Python"})
    repository.save_about_fact({"title": "Curiosity", "statement": "Katy asks thoughtful questions."})
    client = TestClient(app)
    assert login(client, monkeypatch).status_code == 200
    knowledge = client.get("/v1/admin/profile").json()

    assert client.delete(f"/v1/admin/profile/skills/{knowledge['skills'][0]['id']}").status_code == 200
    assert client.delete(f"/v1/admin/profile/about/{knowledge['about'][0]['id']}").status_code == 200
    refreshed = client.get("/v1/admin/profile").json()
    assert refreshed["skills"] == []
    assert refreshed["about"] == []


# Confirms unsupported or malformed uploads are rejected before reaching AI.
def test_profile_import_rejects_unsupported_files(monkeypatch):
    monkeypatch.setattr(main_module, "responder", IntakeResponder())
    client = TestClient(app)
    assert login(client, monkeypatch).status_code == 200

    response = client.post(
        "/v1/admin/profile/import/preview",
        json={"filename": "resume.exe", "file_base64": "aGVsbG8="},
    )

    assert response.status_code == 400
    assert "PDF, DOCX, TXT, or Markdown" in response.json()["detail"]

# Confirms Katy can review questions the recruiter chatbot could not answer.
def test_authenticated_admin_can_review_unanswered_questions(monkeypatch):
    monkeypatch.setattr(main_module, "question_log", QuestionLogStub())
    client = TestClient(app)
    assert login(client, monkeypatch).status_code == 200
    response = client.get("/v1/admin/questions")
    assert response.status_code == 200
    assert response.json()["questions"][0]["outcome"] == "unanswered"
    assert response.json()["total_pages"] == 1


# Confirms clearing recruiter history cannot remove applications or approved knowledge.
def test_admin_can_clear_only_the_question_log(tmp_path, monkeypatch):
    database_path = tmp_path / "ask-katy.private.db"
    repository = ApplicationRepository(database_path)
    log = QuestionLog(database_path)
    monkeypatch.setattr(main_module, "repo", repository)
    monkeypatch.setattr(main_module, "question_log", log)
    client = TestClient(app)
    assert login(client, monkeypatch).status_code == 200
    application = client.post(
        "/v1/admin/applications", json={**payload(), "answers": []}
    ).json()
    repository.save_profile_fact("What does Katy know?", "Approved knowledge.")
    log.record(application["id"], "Recruiter question?", "Answer.", "answered")

    response = client.delete("/v1/admin/questions")

    assert response.status_code == 200
    assert response.json() == {"deleted": 1}
    assert repository.for_admin(application["id"]) is not None
    assert repository.list_profile_facts()[0]["answer"] == "Approved knowledge."
    assert log.page(page=1, page_size=10)["total"] == 0


# Confirms a correction from the question log teaches future application bots.
def test_admin_can_correct_an_unanswered_recruiter_question(tmp_path, monkeypatch):
    database_path = tmp_path / "ask-katy.private.db"
    repository = ApplicationRepository(database_path)
    log = QuestionLog(database_path)
    monkeypatch.setattr(main_module, "repo", repository)
    monkeypatch.setattr(main_module, "question_log", log)
    client = TestClient(app)
    assert login(client, monkeypatch).status_code == 200
    application = client.post(
        "/v1/admin/applications", json={**payload(), "answers": []}
    ).json()
    log.record(application["id"], "Has Katy used webhooks?", "I’m not sure.", "unanswered")
    question_id = client.get("/v1/admin/questions").json()["questions"][0]["id"]

    corrected = client.put(
        f"/v1/admin/questions/{question_id}",
        json={"answer": "Katy has implemented webhook integrations.", "reusable": True},
    )

    assert corrected.status_code == 200
    assert corrected.json()["outcome"] == "answered"
    assert repository.list_profile_facts()[0]["answer"] == "Katy has implemented webhook integrations."


# Confirms each application visibility control changes employer access correctly.
def test_admin_can_preview_publish_unpublish_and_revoke_application(tmp_path, monkeypatch):
    repository = ApplicationRepository(tmp_path / "ask-katy.private.db")
    monkeypatch.setattr(main_module, "repo", repository)
    client = TestClient(app)
    assert login(client, monkeypatch).status_code == 200

    created = client.post(
        "/v1/admin/applications",
        json={**payload(), "answers": []},
    ).json()
    application_id = created["id"]

    preview = client.get(f"/v1/admin/applications/{application_id}")
    assert preview.status_code == 200
    assert preview.json()["page"]["company"] == "Example Company"
    assert preview.json()["status"] == "draft"

    published = client.post(f"/v1/admin/applications/{application_id}/publish")
    assert published.status_code == 200
    assert published.json()["status"] == "published"
    assert repository.find(created["public_path"])["id"] == application_id

    unpublished = client.post(f"/v1/admin/applications/{application_id}/unpublish")
    assert unpublished.status_code == 200
    assert unpublished.json()["status"] == "draft"
    assert repository.find(created["public_path"]) is None

    revoked = client.post(f"/v1/admin/applications/{application_id}/revoke")
    assert revoked.status_code == 200
    assert revoked.json()["status"] == "revoked"
    assert repository.find(created["public_path"]) is None

    unrevoked = client.post(f"/v1/admin/applications/{application_id}/unrevoke")
    assert unrevoked.status_code == 200
    assert unrevoked.json()["status"] == "draft"
    assert repository.find(created["public_path"]) is None

    republished = client.post(f"/v1/admin/applications/{application_id}/publish")
    assert republished.status_code == 200
    assert repository.find(created["public_path"])["id"] == application_id


# Confirms an older application cannot publish before its guaranteed company answer exists.
def test_admin_cannot_publish_without_company_interest(tmp_path, monkeypatch):
    repository = ApplicationRepository(tmp_path / "ask-katy.private.db")
    monkeypatch.setattr(main_module, "repo", repository)
    client = TestClient(app)
    assert login(client, monkeypatch).status_code == 200
    created = client.post(
        "/v1/admin/applications",
        json={**payload(), "answers": []},
    ).json()
    with repository.database.connect() as connection:
        connection.execute(
            "UPDATE applications SET company_interest = '' WHERE id = ?",
            (created["id"],),
        )

    response = client.post(f"/v1/admin/applications/{created['id']}/publish")
    listing = client.get("/v1/admin/applications").json()["applications"][0]

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Add Katy's company-interest notes before publishing."
    )
    assert listing["company_interest_ready"] is False


# Confirms a legacy summary-only draft cannot publish as if it were a full résumé.
def test_admin_cannot_publish_incomplete_generated_resume(tmp_path, monkeypatch):
    repository = ApplicationRepository(tmp_path / "ask-katy.private.db")
    monkeypatch.setattr(main_module, "repo", repository)
    client = TestClient(app)
    assert login(client, monkeypatch).status_code == 200
    created = client.post(
        "/v1/admin/applications",
        json={**payload(), "answers": []},
    ).json()
    with repository.database.connect() as connection:
        connection.execute(
            "UPDATE applications SET resume_json = '{}' WHERE id = ?",
            (created["id"],),
        )

    response = client.post(f"/v1/admin/applications/{created['id']}/publish")

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Add at least one work experience entry to the generated résumé before "
        "publishing."
    )


# Confirms the studio lists every URL and lets Katy edit a generated vanity path.
def test_admin_can_list_and_edit_application_urls(tmp_path, monkeypatch):
    repository = ApplicationRepository(tmp_path / "ask-katy.private.db")
    monkeypatch.setattr(main_module, "repo", repository)
    client = TestClient(app)
    assert login(client, monkeypatch).status_code == 200
    created = client.post(
        "/v1/admin/applications",
        json={**payload(), "answers": []},
    ).json()

    listing = client.get("/v1/admin/applications")
    assert listing.status_code == 200
    assert listing.json()["applications"][0]["id"] == created["id"]
    assert listing.json()["applications"][0]["public_path"] == created["public_path"]
    assert "access_path_hash" not in listing.text

    updated = client.post(
        f"/v1/admin/applications/{created['id']}/url",
        json={"public_path": "example-company/int-consultant"},
    )
    assert updated.status_code == 200
    assert updated.json()["public_path"] == "example-company/int-consultant"
    assert client.get("/v1/admin/applications").json()["applications"][0][
        "public_path"
    ] == "example-company/int-consultant"


# Confirms preview mistakes can be corrected without changing the URL or visibility.
def test_admin_can_edit_application_content(tmp_path, monkeypatch):
    repository = ApplicationRepository(tmp_path / "ask-katy.private.db")
    monkeypatch.setattr(main_module, "repo", repository)
    client = TestClient(app)
    assert login(client, monkeypatch).status_code == 200
    created = client.post(
        "/v1/admin/applications", json={**payload(), "answers": []}
    ).json()

    updated = client.put(
        f"/v1/admin/applications/{created['id']}",
        json={
            "company": "Corrected Company",
            "role": "Integration Consultant",
            "job_description": "Corrected detailed job description " * 5,
            "company_interest": (
                "Corrected Company solves customer workflow problems that Katy "
                "would be excited to help make simpler."
            ),
            "introduction": "Corrected notes for this application.",
            "answers": [{
                "question": "What experience is most relevant?",
                "answer": "Katy has implementation and integration experience.",
            }],
            "resume": {
                "summary": "Customer-focused integration specialist.",
                "skills": ["SaaS implementation", "API integrations"],
                "experience": [{
                    "company": "CD Baby",
                    "role": "Software Engineer",
                    "dates": "",
                    "bullets": ["Implemented and integrated customer workflows."],
                }],
                "education": [],
            },
            "cover_letter_pitch": (
                "I bring implementation and integration experience"
            ),
        },
    )

    assert updated.status_code == 200
    application = client.get(
        f"/v1/admin/applications/{created['id']}"
    ).json()
    assert application["page"]["company"] == "Corrected Company"
    assert application["page"]["role"] == "Integration Consultant"
    assert application["page"]["introduction"] == "Corrected notes for this application."
    assert application["company_interest"].startswith("Corrected Company solves")
    assert application["page"]["suggested_questions"][0] == (
        "Why is Katy interested in Corrected Company?"
    )
    assert application["profile_answers"][0]["answer"].startswith("Katy has")
    assert application["public_path"] == created["public_path"]
    assert application["status"] == "draft"


# Confirms two applications cannot accidentally share the same employer URL.
def test_admin_rejects_duplicate_application_url(tmp_path, monkeypatch):
    repository = ApplicationRepository(tmp_path / "ask-katy.private.db")
    monkeypatch.setattr(main_module, "repo", repository)
    client = TestClient(app)
    assert login(client, monkeypatch).status_code == 200
    first = client.post(
        "/v1/admin/applications", json={**payload(), "answers": []}
    ).json()
    second_payload = {**payload(), "company": "Another Company"}
    second = client.post(
        "/v1/admin/applications", json={**second_payload, "answers": []}
    ).json()

    response = client.post(
        f"/v1/admin/applications/{second['id']}/url",
        json={"public_path": first["public_path"]},
    )
    assert response.status_code == 409


# Confirms a deliberate admin deletion removes the application and its question history.
def test_admin_can_permanently_delete_application(tmp_path, monkeypatch):
    repository = ApplicationRepository(tmp_path / "ask-katy.private.db")
    monkeypatch.setattr(main_module, "repo", repository)
    client = TestClient(app)
    assert login(client, monkeypatch).status_code == 200
    created = client.post(
        "/v1/admin/applications", json={**payload(), "answers": []}
    ).json()
    with repository.database.connect() as connection:
        connection.execute(
            """
            INSERT INTO question_logs(
                timestamp, application_id, question, answer, outcome
            ) VALUES (?, ?, ?, ?, ?)
            """,
            ("2026-01-01T00:00:00+00:00", created["id"], "Q?", "A.", "answered"),
        )

    response = client.delete(f"/v1/admin/applications/{created['id']}")

    assert response.status_code == 200
    assert response.json() == {"id": created["id"], "deleted": True}
    assert repository.for_admin(created["id"]) is None
    with repository.database.connect() as connection:
        remaining = connection.execute(
            "SELECT COUNT(*) FROM question_logs WHERE application_id = ?",
            (created["id"],),
        ).fetchone()[0]
    assert remaining == 0
