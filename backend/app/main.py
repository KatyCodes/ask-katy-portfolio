import base64
import binascii
import hmac
import ipaddress
import os
import secrets
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Cookie, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .ai import (
    OFF_TOPIC_RESPONSE,
    SAFEGUARD_RESPONSE,
    UNKNOWN_RESPONSE,
    AIResponseError,
    OpenAIResponder,
)
from .content import ApplicationRepository
from .error_logging import configure_error_logger
from .migration import migrate_legacy_data
from .models import (
    AccessRequest,
    AdminLogin,
    ApplicationContentUpdate,
    ApplicationDraft,
    ApplicationIntake,
    ApplicationPathUpdate,
    ApprovedAboutFact,
    ApprovedProfileFact,
    ApprovedSkill,
    ChatRequest,
    ProfileImportApproval,
    ProfileImportRequest,
    QuestionCorrection,
    RateLimitSettings,
    UploadedResume,
)
from .profile_import import ProfileImportError, extract_uploaded_text
from .question_log import QuestionLog
from .rate_limit import SlidingWindowRateLimiter
from .security import (
    sign_session,
    validate_production_configuration,
    validate_session_secret,
    verify_session,
)

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

TECHNICAL_DIFFICULTIES_RESPONSE = (
    "Ask Katy is experiencing some technical difficulties. Please refresh the "
    "page and try again, or contact Katy at katyannhenning@gmail.com."
)

LOCAL_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("ASK_KATY_ALLOWED_ORIGINS", ",".join(LOCAL_ORIGINS)).split(",")
    if origin.strip()
]
COOKIE_SECURE = os.getenv("ASK_KATY_COOKIE_SECURE", "false").lower() == "true"
TRUST_PROXY = os.getenv("ASK_KATY_TRUST_PROXY", "false").lower() == "true"
validate_session_secret(require_secure=COOKIE_SECURE)
validate_production_configuration(
    cookie_secure=COOKIE_SECURE,
    allowed_origins=ALLOWED_ORIGINS,
)
OFF_TOPIC_TERMS = {
    "weather",
    "recipe",
    "sports",
    "politics",
    "movie",
    "joke",
    "dating",
    "celebrity",
    "horoscope",
}
MANIPULATION_TERMS = {
    "ignore previous",
    "ignore your instructions",
    "forget your instructions",
    "change your instructions",
    "reveal your prompt",
    "system prompt",
    "developer message",
    "hidden instructions",
    "jailbreak",
}


# Reads a positive integer setting while retaining a safe default for invalid values.
def positive_int_setting(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except ValueError:
        return default


chat_visitor_limiter = SlidingWindowRateLimiter(
    limit=positive_int_setting("ASK_KATY_CHAT_VISITOR_LIMIT", 20),
    window_seconds=positive_int_setting("ASK_KATY_CHAT_VISITOR_WINDOW_SECONDS", 600),
)
chat_global_limiter = SlidingWindowRateLimiter(
    limit=positive_int_setting("ASK_KATY_CHAT_GLOBAL_LIMIT", 120),
    window_seconds=positive_int_setting("ASK_KATY_CHAT_GLOBAL_WINDOW_SECONDS", 3600),
)
admin_login_visitor_limiter = SlidingWindowRateLimiter(limit=5, window_seconds=900)
admin_login_global_limiter = SlidingWindowRateLimiter(limit=50, window_seconds=900)
access_exchange_limiter = SlidingWindowRateLimiter(limit=30, window_seconds=600)
error_logger = configure_error_logger()

app = FastAPI(title="Ask Katy API", docs_url=None, redoc_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type"],
)
repo = ApplicationRepository()
saved_rate_limits = repo.rate_limit_settings()
saved_visitor_limit = min(
    100,
    max(1, saved_rate_limits.get("visitor_limit", chat_visitor_limiter.limit)),
)
saved_global_limit = max(
    saved_visitor_limit,
    min(
        1000,
        max(1, saved_rate_limits.get("global_limit", chat_global_limiter.limit)),
    ),
)
chat_visitor_limiter.reconfigure(limit=saved_visitor_limit)
chat_global_limiter.reconfigure(limit=saved_global_limit)
responder = OpenAIResponder()
question_log = QuestionLog(repo.path)
migrate_legacy_data(repo, question_log)


# Records a known service failure and returns a safe message with a searchable reference.
def service_unavailable_error(
    operation: str,
    public_message: str,
    error: Exception,
) -> HTTPException:
    error_id = secrets.token_hex(4)
    cause = error.__cause__ or error
    error_logger.error(
        "service_error error_id=%s operation=%s error_type=%s",
        error_id,
        operation,
        type(cause).__name__,
    )
    return HTTPException(503, f"{public_message} Reference: {error_id}.")


# Hides unexpected technical details while recording a private traceback by reference.
@app.exception_handler(Exception)
async def handle_unexpected_error(request: Request, error: Exception) -> JSONResponse:
    error_id = secrets.token_hex(4)
    error_logger.exception(
        "unexpected_error error_id=%s method=%s path=%s error_type=%s",
        error_id,
        request.method,
        request.url.path,
        type(error).__name__,
    )
    return JSONResponse(
        status_code=500,
        content={
            "detail": TECHNICAL_DIFFICULTIES_RESPONSE,
            "error_id": error_id,
        },
        headers={"X-Error-ID": error_id},
    )


# Rejects foreign admin forms and adds private browser protections to every API response.
@app.middleware("http")
async def add_privacy_headers(request, call_next):
    origin = request.headers.get("origin")
    is_admin_write = (
        request.url.path.startswith("/v1/admin/")
        and request.method not in {"GET", "HEAD", "OPTIONS"}
    )
    if is_admin_write and origin and origin not in ALLOWED_ORIGINS:
        response = JSONResponse(
            status_code=403,
            content={"detail": "Unapproved admin request origin"},
        )
    else:
        response = await call_next(request)
    response.headers["X-Robots-Tag"] = (
        "noindex, nofollow, noimageindex, nosnippet"
    )
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Permissions-Policy"] = (
        "camera=(), microphone=(), geolocation=()"
    )
    return response


# Provides a small endpoint that hosting monitors can use to confirm the API is alive.
@app.get("/v1/health")
def health() -> dict:
    return {"status": "ok"}


# Rejects an admin request unless its signed login cookie is valid.
def require_admin(ask_katy_admin: str | None) -> None:
    if verify_session(ask_katy_admin) != "__admin__":
        raise HTTPException(401, "Admin sign-in required")


# Converts a missing repository result into the same non-revealing 404 response.
def require_application(application: dict | None) -> dict:
    if not application:
        raise HTTPException(404, "This note is unavailable")
    return application


# Decodes and verifies one bounded PDF before any private application is created.
def decode_uploaded_resume(upload: dict | None) -> dict | None:
    if not upload:
        return None
    try:
        content = base64.b64decode(upload["file_base64"], validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(400, "Choose a valid PDF résumé.")
    if len(content) > 5 * 1024 * 1024 or not content.startswith(b"%PDF-"):
        raise HTTPException(400, "Choose a valid PDF résumé.")
    return {
        "filename": Path(upload["filename"]).name,
        "content": content,
    }


# Builds one consistently private inline-PDF response for admin and recruiter routes.
def pdf_resume_response(resume: dict) -> Response:
    return Response(
        content=resume["content"],
        media_type="application/pdf",
        headers={
            "Content-Disposition": 'inline; filename="Katy-Henning-Resume.pdf"',
            "X-Content-Type-Options": "nosniff",
        },
    )


# Detects common attempts to replace the assistant's private rules or reveal them.
def is_manipulation_attempt(message: str) -> bool:
    normalized = " ".join(message.casefold().split())
    return any(term in normalized for term in MANIPULATION_TERMS)


# Identifies one visitor in memory, trusting proxy headers only when explicitly enabled.
def visitor_address(request: Request) -> str:
    fallback = request.client.host if request.client else "unknown"
    if not TRUST_PROXY:
        return fallback
    forwarded = request.headers.get("x-forwarded-for", "").split(",", 1)[0].strip()
    try:
        return str(ipaddress.ip_address(forwarded))
    except ValueError:
        return fallback


# Applies both the per-visitor allowance and the site-wide OpenAI cost ceiling.
def enforce_chat_rate_limit(request: Request) -> None:
    visitor = chat_visitor_limiter.consume(visitor_address(request))
    if not visitor.allowed:
        raise HTTPException(
            429,
            "Ask Katy has answered several questions recently. Please wait a few minutes and try again.",
            headers={"Retry-After": str(visitor.retry_after)},
        )
    global_limit = chat_global_limiter.consume("all-visitors")
    if not global_limit.allowed:
        raise HTTPException(
            429,
            "Ask Katy is taking a short break after lots of questions. Please try again later.",
            headers={"Retry-After": str(global_limit.retry_after)},
        )


# Slows automated guessing of unlisted company-and-role application paths.
def enforce_access_exchange_rate_limit(request: Request) -> None:
    decision = access_exchange_limiter.consume(visitor_address(request))
    if not decision.allowed:
        raise HTTPException(
            429,
            "Too many application links tried. Please wait and try again.",
            headers={"Retry-After": str(decision.retry_after)},
        )


# Counts one failed sign-in and temporarily rejects repeated guessing attempts.
def reject_failed_admin_login(request: Request) -> None:
    visitor = admin_login_visitor_limiter.consume(visitor_address(request))
    global_limit = admin_login_global_limiter.consume("all-visitors")
    blocked_retries = [
        decision.retry_after
        for decision in (visitor, global_limit)
        if not decision.allowed
    ]
    if blocked_retries:
        raise HTTPException(
            429,
            "Too many failed sign-in attempts. Please wait and try again.",
            headers={"Retry-After": str(max(blocked_retries))},
        )
    raise HTTPException(401, "Invalid credentials")


# Verifies Katy's password and starts an eight-hour private admin session.
@app.post("/v1/admin/login")
def admin_login(request: AdminLogin, response: Response, http_request: Request) -> dict:
    configured = os.getenv("ASK_KATY_ADMIN_PASSWORD", "")
    if not configured:
        raise HTTPException(503, "Admin access is not configured")
    if not hmac.compare_digest(request.password.encode(), configured.encode()):
        reject_failed_admin_login(http_request)
    response.set_cookie(
        "ask_katy_admin",
        sign_session("__admin__", ttl=28800),
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="strict",
        max_age=28800,
    )
    return {"authenticated": True}


# Expires the signed admin cookie even when the previous session already expired.
@app.post("/v1/admin/logout")
def admin_logout(response: Response) -> dict:
    response.delete_cookie(
        "ask_katy_admin",
        path="/",
        secure=COOKIE_SECURE,
        httponly=True,
        samesite="strict",
    )
    return {"authenticated": False}


# Lets the admin page restore a valid login after a refresh without asking again.
@app.get("/v1/admin/session")
def admin_session(ask_katy_admin: str | None = Cookie(default=None)) -> dict:
    require_admin(ask_katy_admin)
    return {"authenticated": True}


# Returns the active question ceilings and their fixed rolling time windows.
def current_rate_limit_settings() -> dict:
    return {
        "visitor_limit": chat_visitor_limiter.limit,
        "visitor_window_seconds": chat_visitor_limiter.window_seconds,
        "global_limit": chat_global_limiter.limit,
        "global_window_seconds": chat_global_limiter.window_seconds,
    }


# Lets Katy review the active AI question ceilings from the private studio.
@app.get("/v1/admin/settings/rate-limits")
def get_rate_limit_settings(
    ask_katy_admin: str | None = Cookie(default=None),
) -> dict:
    require_admin(ask_katy_admin)
    return current_rate_limit_settings()


# Saves validated question ceilings and applies them without restarting the app.
@app.put("/v1/admin/settings/rate-limits")
def update_rate_limit_settings(
    request: RateLimitSettings,
    ask_katy_admin: str | None = Cookie(default=None),
) -> dict:
    require_admin(ask_katy_admin)
    settings = request.model_dump()
    repo.save_rate_limit_settings(settings)
    chat_visitor_limiter.reconfigure(limit=request.visitor_limit)
    chat_global_limiter.reconfigure(limit=request.global_limit)
    return current_rate_limit_settings()


# Compares a role with approved knowledge before asking Katy for missing evidence.
@app.post("/v1/admin/intake/questions")
def intake_questions(
    request: ApplicationIntake,
    ask_katy_admin: str | None = Cookie(default=None),
) -> dict:
    require_admin(ask_katy_admin)
    try:
        intake = request.model_dump()
        intake["known_knowledge"] = repo.list_profile_knowledge()
        return responder.intake_review(intake)
    except AIResponseError as exc:
        raise service_unavailable_error(
            "intake_questions",
            "Could not generate questions.",
            exc,
        ) from exc


# Saves a new private application as an unpublished draft.
@app.post("/v1/admin/applications")
def create_application(
    request: ApplicationDraft,
    ask_katy_admin: str | None = Cookie(default=None),
) -> dict:
    require_admin(ask_katy_admin)
    intake = request.model_dump()
    uploaded_resume = decode_uploaded_resume(intake.pop("uploaded_resume", None))
    intake["known_knowledge"] = repo.list_profile_knowledge()
    try:
        intake["documents"] = responder.application_documents(intake)
    except AIResponseError as exc:
        raise service_unavailable_error(
            "application_documents",
            "Could not create the résumé and cover-letter drafts.",
            exc,
        ) from exc
    intake["uploaded_resume"] = uploaded_resume
    return repo.create_draft(intake)


# Lists every application's safe summary for the private studio.
@app.get("/v1/admin/applications")
def list_applications(
    ask_katy_admin: str | None = Cookie(default=None),
) -> dict:
    require_admin(ask_katy_admin)
    return {"applications": repo.list_for_admin()}


# Lists the reusable professional facts available to every application assistant.
@app.get("/v1/admin/profile")
def list_profile(ask_katy_admin: str | None = Cookie(default=None)) -> dict:
    require_admin(ask_katy_admin)
    return repo.list_profile_knowledge()


# Produces evidence-backed draft facts from pasted text or an in-memory document.
@app.post("/v1/admin/profile/import/preview")
def preview_profile_import(
    request: ProfileImportRequest,
    ask_katy_admin: str | None = Cookie(default=None),
) -> dict:
    require_admin(ask_katy_admin)
    try:
        source_text = request.pasted_text.strip() or extract_uploaded_text(
            request.filename, request.file_base64
        )
        knowledge = responder.profile_knowledge(
            source_text, repo.list_profile_knowledge()
        )
    except ProfileImportError as exc:
        raise HTTPException(400, str(exc)) from exc
    except AIResponseError as exc:
        raise service_unavailable_error(
            "profile_import",
            "Could not review that career material.",
            exc,
        ) from exc
    return knowledge


# Saves only the facts Katy selected and edited in the private review screen.
@app.post("/v1/admin/profile/import/approve")
def approve_profile_import(
    request: ProfileImportApproval,
    ask_katy_admin: str | None = Cookie(default=None),
) -> dict:
    require_admin(ask_katy_admin)
    for skill in request.skills:
        repo.save_profile_skill(skill.model_dump())
    for fact in request.about:
        repo.save_about_fact(fact.model_dump())
    for fact in request.facts:
        repo.save_profile_fact(fact.question, fact.answer)
    return {"saved": len(request.skills) + len(request.about) + len(request.facts)}


# Replaces one reviewed reusable fact without forcing Katy to delete and recreate it.
@app.put("/v1/admin/profile/{fact_id}")
def update_profile_fact(
    fact_id: int,
    request: ApprovedProfileFact,
    ask_katy_admin: str | None = Cookie(default=None),
) -> dict:
    require_admin(ask_katy_admin)
    return require_application(
        repo.update_profile_fact(fact_id, request.question, request.answer)
    )


# Replaces the editable metadata for one reusable skill.
@app.put("/v1/admin/profile/skills/{skill_id}")
def update_profile_skill(
    skill_id: int,
    request: ApprovedSkill,
    ask_katy_admin: str | None = Cookie(default=None),
) -> dict:
    require_admin(ask_katy_admin)
    return require_application(repo.update_profile_skill(skill_id, request.model_dump()))


# Replaces one reusable About Katy statement.
@app.put("/v1/admin/profile/about/{fact_id}")
def update_about_fact(
    fact_id: int,
    request: ApprovedAboutFact,
    ask_katy_admin: str | None = Cookie(default=None),
) -> dict:
    require_admin(ask_katy_admin)
    return require_application(repo.update_about_fact(fact_id, request.model_dump()))


# Removes one structured skill from Katy's reusable professional knowledge.
@app.delete("/v1/admin/profile/skills/{skill_id}")
def delete_profile_skill(
    skill_id: int,
    ask_katy_admin: str | None = Cookie(default=None),
) -> dict:
    require_admin(ask_katy_admin)
    require_application(repo.delete_profile_skill(skill_id))
    return {"id": skill_id, "deleted": True}


# Removes one About Katy statement from the reusable knowledge base.
@app.delete("/v1/admin/profile/about/{fact_id}")
def delete_about_fact(
    fact_id: int,
    ask_katy_admin: str | None = Cookie(default=None),
) -> dict:
    require_admin(ask_katy_admin)
    require_application(repo.delete_about_fact(fact_id))
    return {"id": fact_id, "deleted": True}


# Removes one fact from Katy's reusable professional profile.
@app.delete("/v1/admin/profile/{fact_id}")
def delete_profile_fact(
    fact_id: int,
    ask_katy_admin: str | None = Cookie(default=None),
) -> dict:
    require_admin(ask_katy_admin)
    require_application(repo.delete_profile_fact(fact_id))
    return {"id": fact_id, "deleted": True}


# Returns an unpublished or published application for private admin preview.
@app.get("/v1/admin/applications/{application_id}")
def preview_application(
    application_id: str,
    ask_katy_admin: str | None = Cookie(default=None),
) -> dict:
    require_admin(ask_katy_admin)
    return require_application(repo.for_admin(application_id))


# Opens one uploaded application résumé for the signed-in admin only.
@app.get("/v1/admin/applications/{application_id}/resume")
def preview_uploaded_resume(
    application_id: str,
    ask_katy_admin: str | None = Cookie(default=None),
) -> Response:
    require_admin(ask_katy_admin)
    require_application(repo.for_admin(application_id))
    resume = repo.uploaded_resume(application_id)
    if not resume:
        raise HTTPException(404, "This résumé is unavailable")
    return pdf_resume_response(resume)


# Adds or replaces one application's private premade PDF résumé.
@app.put("/v1/admin/applications/{application_id}/resume")
def update_uploaded_resume(
    application_id: str,
    request: UploadedResume,
    ask_katy_admin: str | None = Cookie(default=None),
) -> dict:
    require_admin(ask_katy_admin)
    resume = decode_uploaded_resume(request.model_dump())
    if not resume:
        raise HTTPException(400, "Choose a valid PDF résumé.")
    return require_application(repo.update_uploaded_resume(application_id, resume))


# Removes one premade PDF so the application returns to its generated résumé.
@app.delete("/v1/admin/applications/{application_id}/resume")
def delete_uploaded_resume(
    application_id: str,
    ask_katy_admin: str | None = Cookie(default=None),
) -> dict:
    require_admin(ask_katy_admin)
    return require_application(repo.update_uploaded_resume(application_id, None))


# Rebuilds one job's résumé and cover letter from current approved knowledge.
@app.post("/v1/admin/applications/{application_id}/documents/regenerate")
def regenerate_application_documents(
    application_id: str,
    ask_katy_admin: str | None = Cookie(default=None),
) -> dict:
    require_admin(ask_katy_admin)
    application = require_application(repo.for_admin(application_id))
    intake = {
        "company": application["page"]["company"],
        "role": application["page"]["role"],
        "job_description": application["job_description"],
        "company_interest": application["company_interest"],
        "notes": application["page"]["introduction"],
        "answers": application["profile_answers"],
        "known_knowledge": repo.list_profile_knowledge(),
    }
    try:
        documents = responder.application_documents(intake)
    except AIResponseError as exc:
        raise service_unavailable_error(
            "application_documents",
            "Could not regenerate the résumé and cover-letter drafts.",
            exc,
        ) from exc
    return require_application(
        repo.update_application_documents(application_id, documents)
    )


# Saves corrections made after previewing one application without changing its URL.
@app.put("/v1/admin/applications/{application_id}")
def update_application_content(
    application_id: str,
    request: ApplicationContentUpdate,
    ask_katy_admin: str | None = Cookie(default=None),
) -> dict:
    require_admin(ask_katy_admin)
    return require_application(
        repo.update_application_content(application_id, request.model_dump())
    )


# Permanently removes one application and its recruiter-question history.
@app.delete("/v1/admin/applications/{application_id}")
def delete_application(
    application_id: str,
    ask_katy_admin: str | None = Cookie(default=None),
) -> dict:
    require_admin(ask_katy_admin)
    require_application(repo.delete(application_id))
    return {"id": application_id, "deleted": True}


# Makes a reviewed application available at its unlisted employer URL.
@app.post("/v1/admin/applications/{application_id}/publish")
def publish_application(
    application_id: str,
    ask_katy_admin: str | None = Cookie(default=None),
) -> dict:
    require_admin(ask_katy_admin)
    try:
        application = repo.set_status(application_id, "published")
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"id": application_id, "status": require_application(application)["status"]}


# Hides an application while preserving its vanity URL for later reuse.
@app.post("/v1/admin/applications/{application_id}/unpublish")
def unpublish_application(
    application_id: str,
    ask_katy_admin: str | None = Cookie(default=None),
) -> dict:
    require_admin(ask_katy_admin)
    application = require_application(repo.set_status(application_id, "draft"))
    return {"id": application_id, "status": application["status"]}


# Disables an application's current link so it can never be used again.
@app.post("/v1/admin/applications/{application_id}/revoke")
def revoke_application(
    application_id: str,
    ask_katy_admin: str | None = Cookie(default=None),
) -> dict:
    require_admin(ask_katy_admin)
    application = require_application(repo.revoke(application_id))
    return {"id": application_id, "status": application["status"]}


# Restores a revoked application as a private draft without activating its link.
@app.post("/v1/admin/applications/{application_id}/unrevoke")
def unrevoke_application(
    application_id: str,
    ask_katy_admin: str | None = Cookie(default=None),
) -> dict:
    require_admin(ask_katy_admin)
    application = require_application(repo.set_status(application_id, "draft"))
    return {"id": application_id, "status": application["status"]}


# Saves an admin-selected company-and-role vanity URL for one application.
@app.post("/v1/admin/applications/{application_id}/url")
def update_application_url(
    application_id: str,
    request: ApplicationPathUpdate,
    ask_katy_admin: str | None = Cookie(default=None),
) -> dict:
    require_admin(ask_katy_admin)
    try:
        application = repo.update_public_path(application_id, request.public_path)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return require_application(application)


# Returns one counted page of recruiter questions, prioritizing unanswered ones.
@app.get("/v1/admin/questions")
def admin_questions(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=5, le=50),
    ask_katy_admin: str | None = Cookie(default=None),
) -> dict:
    require_admin(ask_katy_admin)
    return question_log.page(page=page, page_size=page_size)


# Clears recruiter-question history without deleting applications or approved knowledge.
@app.delete("/v1/admin/questions")
def clear_admin_questions(
    ask_katy_admin: str | None = Cookie(default=None),
) -> dict:
    require_admin(ask_katy_admin)
    return {"deleted": question_log.clear()}


# Corrects a recruiter answer and teaches either this application or every bot.
@app.put("/v1/admin/questions/{question_id}")
def correct_admin_question(
    question_id: int,
    request: QuestionCorrection,
    ask_katy_admin: str | None = Cookie(default=None),
) -> dict:
    require_admin(ask_katy_admin)
    corrected = require_application(question_log.correct(question_id, request.answer))
    if request.reusable:
        repo.save_profile_fact(corrected["question"], request.answer)
    else:
        repo.save_application_answer(
            corrected["application_id"], corrected["question"], request.answer
        )
    return corrected


# Exchanges a valid employer link for a short-lived, application-scoped session.
@app.post("/v1/access/exchange")
def exchange(
    request: AccessRequest,
    response: Response,
    http_request: Request,
    ask_katy_admin: str | None = Cookie(default=None),
) -> dict:
    is_admin_preview = (
        request.preview and verify_session(ask_katy_admin) == "__admin__"
    )
    if not is_admin_preview:
        enforce_access_exchange_rate_limit(http_request)
    application = (
        repo.find_for_admin_preview(request.access_path)
        if is_admin_preview
        else repo.find(request.access_path)
    )
    application = require_application(application)
    response.set_cookie(
        "ask_katy_session",
        sign_session(application["id"]),
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
        max_age=3600,
    )
    return {
        **application["page"],
        "resume": application["resume"],
        "resume_source": application["resume_source"],
        "cover_letter_pitch": application["cover_letter_pitch"],
    }


# Streams the current application's private PDF only after a valid employer exchange.
@app.get("/v1/resume")
def uploaded_resume_document(
    ask_katy_session: str | None = Cookie(default=None),
    ask_katy_admin: str | None = Cookie(default=None),
) -> Response:
    application_id = verify_session(ask_katy_session)
    application = (
        repo.for_admin(application_id)
        if application_id and verify_session(ask_katy_admin) == "__admin__"
        else repo.by_id(application_id) if application_id else None
    )
    application = require_application(application)
    resume = repo.uploaded_resume(application["id"])
    if not resume:
        raise HTTPException(404, "This résumé is unavailable")
    return pdf_resume_response(resume)


# Answers one recruiter question using only the current application's approved facts.
@app.post("/v1/chat")
def chat(
    request: ChatRequest,
    http_request: Request,
    ask_katy_session: str | None = Cookie(default=None),
) -> dict:
    application_id = verify_session(ask_katy_session)
    application = repo.by_id(application_id) if application_id else None
    application = require_application(application)
    if is_manipulation_attempt(request.message):
        question_log.record(
            application["id"],
            request.message,
            SAFEGUARD_RESPONSE,
            "off_topic",
        )
        return {
            "answer": SAFEGUARD_RESPONSE,
            "grounded_fact_ids": [],
            "disclaimer": "AI-generated from Katy's approved professional information.",
        }
    if any(term in request.message.lower() for term in OFF_TOPIC_TERMS):
        question_log.record(
            application["id"],
            request.message,
            OFF_TOPIC_RESPONSE,
            "off_topic",
        )
        return {
            "answer": OFF_TOPIC_RESPONSE,
            "grounded_fact_ids": [],
            "disclaimer": "AI-generated from Katy's approved professional information.",
        }
    enforce_chat_rate_limit(http_request)
    try:
        answer = responder.answer(
            application,
            request.message,
            [item.model_dump() for item in request.history],
        )
    except AIResponseError as exc:
        raise service_unavailable_error(
            "public_chat",
            TECHNICAL_DIFFICULTIES_RESPONSE,
            exc,
        ) from exc
    outcome = "unanswered" if answer == UNKNOWN_RESPONSE else "answered"
    question_log.record(application["id"], request.message, answer, outcome)
    return {
        "answer": answer,
        "grounded_fact_ids": application["fact_ids"],
        "disclaimer": "AI-generated from Katy's approved professional information.",
    }
