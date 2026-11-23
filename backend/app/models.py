from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


# Rejects unexpected request fields instead of silently accepting typos or extras.
class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


# Validates the private path submitted when an employer opens a page.
class AccessRequest(StrictModel):
    access_path: str = Field(
        min_length=5,
        max_length=160,
        pattern=r"^[a-z0-9-]+/[a-z0-9-]+$",
    )
    preview: bool = False


# Validates an editable company-and-role vanity path chosen in the admin studio.
class ApplicationPathUpdate(StrictModel):
    public_path: str = Field(
        min_length=5,
        max_length=160,
        pattern=r"^[a-z0-9-]+/[a-z0-9-]+$",
    )


# Represents one bounded user or assistant message in recent chat history.
class Message(StrictModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=1000)


# Validates a recruiter question and at most six prior conversation messages.
class ChatRequest(StrictModel):
    message: str = Field(min_length=1, max_length=600)
    history: list[Message] = Field(default_factory=list, max_length=6)


# Validates the password submitted to the private application studio.
class AdminLogin(StrictModel):
    password: str = Field(min_length=8, max_length=200)


# Validates editable AI question ceilings while preserving a site-wide safety brake.
class RateLimitSettings(StrictModel):
    visitor_limit: int = Field(ge=1, le=100)
    global_limit: int = Field(ge=1, le=1000)

    # Prevents one visitor's allowance from exceeding the whole site's allowance.
    @model_validator(mode="after")
    def require_consistent_limits(self):
        if self.global_limit < self.visitor_limit:
            raise ValueError("The site-wide limit must be at least the per-visitor limit")
        return self


# Captures the initial job information used to generate follow-up questions.
class ApplicationIntake(StrictModel):
    company: str = Field(min_length=2, max_length=120)
    role: str = Field(min_length=2, max_length=160)
    job_description: str = Field(min_length=100, max_length=20000)
    company_interest: str = Field(min_length=20, max_length=3000)
    notes: str = Field(default="", max_length=10000)


# Describes how one important job requirement relates to Katy's approved knowledge.
class IntakeReviewItem(StrictModel):
    question: str = Field(min_length=3, max_length=500)
    status: Literal["confirm", "expand", "new"]
    source_ids: list[str] = Field(max_length=6)
    guidance: str = Field(min_length=3, max_length=1000)


# Defines the structured comparison OpenAI must return for application intake.
class IntakeReview(StrictModel):
    introduction: str = Field(min_length=3, max_length=10000)
    items: list[IntakeReviewItem] = Field(max_length=6)


# Requires every AI-written résumé phrase to point to approved source material.
class GroundedDraftText(StrictModel):
    text: str = Field(min_length=1, max_length=1500)
    source_ids: list[str] = Field(min_length=1, max_length=8)


# Represents one recent position selected for a tailored résumé draft.
class GroundedResumeExperience(StrictModel):
    company: GroundedDraftText
    role: GroundedDraftText
    dates: GroundedDraftText | None
    bullets: list[GroundedDraftText] = Field(min_length=1, max_length=6)


# Represents one education entry only when approved material explicitly supports it.
class GroundedResumeEducation(StrictModel):
    school: GroundedDraftText
    credential: GroundedDraftText
    dates: GroundedDraftText | None


# Defines the evidence-linked job documents OpenAI may propose for Katy's review.
class GroundedApplicationDocuments(StrictModel):
    summary: GroundedDraftText
    skills: list[GroundedDraftText] = Field(default_factory=list, max_length=15)
    experience: list[GroundedResumeExperience] = Field(min_length=1, max_length=4)
    education: list[GroundedResumeEducation] = Field(default_factory=list, max_length=3)
    cover_letter_pitch: GroundedDraftText


# Stores one AI-generated intake question and Katy's truthful answer.
class IntakeAnswer(StrictModel):
    question: str = Field(min_length=3, max_length=500)
    answer: str = Field(min_length=1, max_length=3000)
    reusable: bool = True


# Carries one optional application-specific PDF without making it reusable AI knowledge.
class UploadedResume(StrictModel):
    filename: str = Field(min_length=5, max_length=255)
    file_base64: str = Field(min_length=8, max_length=7100000)

    # Keeps the browser and API contract limited to PDFs that can display consistently.
    @model_validator(mode="after")
    def require_pdf_filename(self):
        if not self.filename.casefold().endswith(".pdf"):
            raise ValueError("The uploaded résumé must be a PDF")
        return self


# Adds the answered intake questions needed to create a private draft.
class ApplicationDraft(ApplicationIntake):
    answers: list[IntakeAnswer] = Field(default_factory=list, max_length=20)
    uploaded_resume: UploadedResume | None = None


# Stores one editable position in an application-specific résumé.
class ResumeExperience(StrictModel):
    company: str = Field(min_length=1, max_length=160)
    role: str = Field(min_length=1, max_length=160)
    dates: str = Field(default="", max_length=120)
    bullets: list[str] = Field(default_factory=list, max_length=6)


# Stores one editable education entry without forcing unknown dates.
class ResumeEducation(StrictModel):
    school: str = Field(min_length=1, max_length=200)
    credential: str = Field(min_length=1, max_length=240)
    dates: str = Field(default="", max_length=120)


# Stores the ATS-safe résumé content unique to one job application.
class ApplicationResume(StrictModel):
    summary: str = Field(min_length=3, max_length=3000)
    skills: list[str] = Field(default_factory=list, max_length=15)
    experience: list[ResumeExperience] = Field(default_factory=list, max_length=4)
    education: list[ResumeEducation] = Field(default_factory=list, max_length=3)


# Represents one AI-proposed reusable fact plus its exact source evidence.
class ProfileCandidate(StrictModel):
    question: str = Field(min_length=3, max_length=500)
    answer: str = Field(min_length=3, max_length=3000)
    evidence_quote: str = Field(min_length=3, max_length=1000)


# Defines the schema OpenAI must follow when proposing reusable profile facts.
class ProfileCandidates(StrictModel):
    facts: list[ProfileCandidate] = Field(default_factory=list, max_length=20)


Proficiency = Literal["learning", "familiar", "working", "proficient", "advanced", "expert"]


# Represents one AI-proposed skill with optional depth and experience details.
class SkillCandidate(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    proficiency: Proficiency | None = None
    years: float | None = Field(default=None, ge=0, le=60)
    used_at: str = Field(default="", max_length=500)
    detail: str = Field(default="", max_length=1500)
    evidence_quote: str = Field(min_length=3, max_length=1000)


# Represents one personal or working-style fact that does not fit a skill scale.
class AboutCandidate(StrictModel):
    title: str = Field(min_length=2, max_length=120)
    statement: str = Field(min_length=3, max_length=1500)
    evidence_quote: str = Field(min_length=3, max_length=1000)


# Defines the structured categories OpenAI returns from career source material.
class KnowledgeCandidates(StrictModel):
    skills: list[SkillCandidate] = Field(default_factory=list, max_length=30)
    about: list[AboutCandidate] = Field(default_factory=list, max_length=20)
    facts: list[ProfileCandidate] = Field(default_factory=list, max_length=20)


# Accepts either pasted text or one supported in-memory career document.
class ProfileImportRequest(StrictModel):
    pasted_text: str = Field(default="", max_length=60000)
    filename: str = Field(default="", max_length=255)
    file_base64: str = Field(default="", max_length=7500000)

    # Requires exactly one useful source while allowing an optional filename for files.
    @model_validator(mode="after")
    def require_source(self):
        has_text = bool(self.pasted_text.strip())
        has_file = bool(self.file_base64.strip())
        if has_text == has_file:
            raise ValueError("Provide pasted text or one file")
        if has_file and not self.filename.strip():
            raise ValueError("A filename is required for an uploaded file")
        return self


# Represents one reviewed fact Katy explicitly approves for permanent reuse.
class ApprovedProfileFact(StrictModel):
    question: str = Field(min_length=3, max_length=500)
    answer: str = Field(min_length=3, max_length=3000)


# Validates application-specific corrections without altering reusable Katy knowledge.
class ApplicationContentUpdate(StrictModel):
    company: str = Field(min_length=2, max_length=120)
    role: str = Field(min_length=2, max_length=160)
    job_description: str = Field(min_length=100, max_length=20000)
    company_interest: str = Field(min_length=20, max_length=3000)
    introduction: str = Field(min_length=3, max_length=10000)
    answers: list[ApprovedProfileFact] = Field(default_factory=list, max_length=20)
    resume: ApplicationResume
    cover_letter_pitch: str = Field(min_length=3, max_length=1500)


# Stores one reviewed skill while allowing unknown details to remain blank.
class ApprovedSkill(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    proficiency: Proficiency | None = None
    years: float | None = Field(default=None, ge=0, le=60)
    used_at: str = Field(default="", max_length=500)
    detail: str = Field(default="", max_length=1500)
    evidence_quote: str = Field(default="", max_length=1000)


# Stores one reviewed About Katy statement without forcing skill-like metadata.
class ApprovedAboutFact(StrictModel):
    title: str = Field(min_length=2, max_length=120)
    statement: str = Field(min_length=3, max_length=1500)
    evidence_quote: str = Field(default="", max_length=1000)


# Validates Katy's correction to an answer captured in the recruiter question log.
class QuestionCorrection(StrictModel):
    answer: str = Field(min_length=3, max_length=3000)
    reusable: bool = True


# Batches reviewed facts for one deliberate profile approval action.
class ProfileImportApproval(StrictModel):
    skills: list[ApprovedSkill] = Field(default_factory=list, max_length=30)
    about: list[ApprovedAboutFact] = Field(default_factory=list, max_length=20)
    facts: list[ApprovedProfileFact] = Field(default_factory=list, max_length=20)

    # Requires at least one reviewed item across the three knowledge categories.
    @model_validator(mode="after")
    def require_knowledge(self):
        if not (self.skills or self.about or self.facts):
            raise ValueError("Approve at least one knowledge item")
        return self
