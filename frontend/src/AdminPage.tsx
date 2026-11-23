import { FormEvent, useEffect, useState } from "react";

const API =
  import.meta.env.VITE_API_URL ??
  `${window.location.protocol}//${window.location.hostname}:8000`;
const SITE = (import.meta.env.VITE_SITE_URL ?? window.location.origin).replace(/\/$/, "");
const QUESTION_LOG_PAGE_SIZE = 10;

type Intake = {
  company: string;
  role: string;
  job_description: string;
  company_interest: string;
  notes: string;
};

type IntakeQuestion = {
  question: string;
  status: "confirm" | "expand" | "new";
  suggested_answer: string;
  guidance: string;
  source_ids: string[];
};

type IntakeQuestionState = IntakeQuestion | string;

// Preserves older in-browser question state while upgrading it to the review shape.
export function normalizeIntakeQuestion(item: IntakeQuestionState): IntakeQuestion {
  if (typeof item !== "string") return item;
  return {
    question: item,
    status: "new",
    suggested_answer: "",
    guidance: "Ask Katy has not compared this question with saved knowledge yet.",
    source_ids: [],
  };
}

const INTAKE_STATUS_LABELS: Record<IntakeQuestion["status"], string> = {
  confirm: "Already known",
  expand: "Close match",
  new: "New information",
};

type Page = {
  company: string;
  role: string;
  eyebrow: string;
  headline: string;
  introduction: string;
  accomplishments: { title: string; detail: string }[];
};

type ApplicationResume = {
  summary: string;
  skills: string[];
  experience: { company: string; role: string; dates: string; bullets: string[] }[];
  education: { school: string; credential: string; dates: string }[];
};

type Application = {
  id: string;
  status: "draft" | "published" | "revoked";
  public_path: string | null;
  company_interest_ready?: boolean;
  page: Page;
  job_description?: string;
  company_interest?: string;
  uploaded_resume_filename?: string;
  profile_answers?: { question: string; answer: string }[];
  resume?: ApplicationResume;
  cover_letter_pitch?: string;
};

type QuestionEntry = {
  id: number;
  timestamp: string;
  application_id: string;
  question: string;
  answer: string;
  outcome: "answered" | "unanswered" | "off_topic";
};

type ProfileFact = {
  id: number;
  question: string;
  answer: string;
};

type ProfileSkill = {
  id: number;
  name: string;
  proficiency: "learning" | "familiar" | "working" | "proficient" | "advanced" | "expert" | null;
  years: number | null;
  used_at: string;
  detail: string;
  evidence_quote: string;
};

type AboutFact = {
  id: number;
  title: string;
  statement: string;
  evidence_quote: string;
};

type ProfileFactDraft = {
  question: string;
  answer: string;
  evidence_quote: string;
  selected: boolean;
};

type SkillDraft = Omit<ProfileSkill, "id"> & { selected: boolean };
type AboutDraft = Omit<AboutFact, "id"> & { selected: boolean };

type KnowledgeEdit =
  | { kind: "fact"; item: ProfileFact }
  | { kind: "skill"; item: ProfileSkill }
  | { kind: "about"; item: AboutFact };

type LinkResult = {
  id: string;
  public_path: string;
  status: string;
};

type RateLimitSettings = {
  visitor_limit: number;
  visitor_window_seconds: number;
  global_limit: number;
  global_window_seconds: number;
};

type AdminSection =
  | "teach"
  | "knowledge"
  | "new-application"
  | "application-control"
  | "settings"
  | "questions";

const INITIAL_COLLAPSED_SECTIONS: Record<AdminSection, boolean> = {
  teach: true,
  knowledge: true,
  "new-application": true,
  "application-control": false,
  settings: true,
  questions: true,
};


// Renders the one unobtrusive control added to each existing admin section.
function SectionToggle({
  label,
  section,
  collapsed,
  onToggle,
}: {
  label: string;
  section: AdminSection;
  collapsed: boolean;
  onToggle: (section: AdminSection) => void;
}) {
  return (
    <button
      type="button"
      className="section-toggle"
      aria-expanded={!collapsed}
      aria-controls={`${section}-content`}
      aria-label={`${collapsed ? "Expand" : "Minimize"} ${label}`}
      onClick={() => onToggle(section)}
    >
      {collapsed ? "+ Expand" : "− Minimize"}
    </button>
  );
}

export function AdminPage() {
  const [password, setPassword] = useState("");
  const [authenticated, setAuthenticated] = useState(false);
  const [checkingSession, setCheckingSession] = useState(true);
  const [signingOut, setSigningOut] = useState(false);
  const [intake, setIntake] = useState<Intake>({
    company: "",
    role: "",
    job_description: "",
    company_interest: "",
    notes: "",
  });
  const [questions, setQuestions] = useState<IntakeQuestionState[]>([]);
  const [answers, setAnswers] = useState<string[]>([]);
  const [reusableAnswers, setReusableAnswers] = useState<boolean[]>([]);
  const [result, setResult] = useState<LinkResult | null>(null);
  const [message, setMessage] = useState("");
  const [connectionError, setConnectionError] = useState("");
  const [rateLimits, setRateLimits] = useState<RateLimitSettings>({
    visitor_limit: 20,
    visitor_window_seconds: 600,
    global_limit: 120,
    global_window_seconds: 3600,
  });
  const [rateLimitMessage, setRateLimitMessage] = useState("");
  const [questionLog, setQuestionLog] = useState<QuestionEntry[]>([]);
  const [questionLogLoading, setQuestionLogLoading] = useState(false);
  const [questionLogPage, setQuestionLogPage] = useState(1);
  const [questionLogTotal, setQuestionLogTotal] = useState(0);
  const [questionLogTotalPages, setQuestionLogTotalPages] = useState(1);
  const [applications, setApplications] = useState<Application[]>([]);
  const [preview, setPreview] = useState<Application | null>(null);
  const [editingApplication, setEditingApplication] = useState<Application | null>(null);
  const [applicationSaveError, setApplicationSaveError] = useState("");
  const [applicationSaving, setApplicationSaving] = useState(false);
  const [urlDrafts, setUrlDrafts] = useState<Record<string, string>>({});
  const [profileFacts, setProfileFacts] = useState<ProfileFact[]>([]);
  const [profileSkills, setProfileSkills] = useState<ProfileSkill[]>([]);
  const [aboutFacts, setAboutFacts] = useState<AboutFact[]>([]);
  const [teachingText, setTeachingText] = useState("");
  const [teachingFile, setTeachingFile] = useState<File | null>(null);
  const [uploadedResume, setUploadedResume] = useState<File | null>(null);
  const [editingResumeUpload, setEditingResumeUpload] = useState<File | null>(null);
  const [resumeUploadBusy, setResumeUploadBusy] = useState(false);
  const [resumeUploadError, setResumeUploadError] = useState("");
  const [teachingDrafts, setTeachingDrafts] = useState<ProfileFactDraft[]>([]);
  const [teachingSkills, setTeachingSkills] = useState<SkillDraft[]>([]);
  const [teachingAbout, setTeachingAbout] = useState<AboutDraft[]>([]);
  const [teachingBusy, setTeachingBusy] = useState(false);
  const [knowledgeEdit, setKnowledgeEdit] = useState<KnowledgeEdit | null>(null);
  const [questionEditId, setQuestionEditId] = useState<number | null>(null);
  const [questionAnswer, setQuestionAnswer] = useState("");
  const [questionReusable, setQuestionReusable] = useState(true);
  const [collapsedSections, setCollapsedSections] = useState(INITIAL_COLLAPSED_SECTIONS);

  // Converts backend failures into safe responses and visible admin notifications.
  async function adminFetch(
    input: Parameters<typeof fetch>[0],
    init?: Parameters<typeof fetch>[1],
  ): Promise<Response> {
    try {
      const response = await fetch(input, init);
      if (response.status >= 500) {
        const data = await response.clone().json().catch(() => null);
        const detail = typeof data?.detail === "string"
          ? data.detail
          : "Ask Katy hit a temporary server problem. Please try again.";
        const reference = typeof data?.error_id === "string"
          ? ` Reference: ${data.error_id}.`
          : "";
        setConnectionError(`${detail}${reference}`);
      }
      return response;
    } catch {
      const detail = "Ask Katy could not reach the backend. Your changes were not saved. Please try again.";
      setConnectionError(detail);
      return new Response(JSON.stringify({ detail }), {
        status: 503,
        headers: { "Content-Type": "application/json" },
      });
    }
  }

  // Restores the server-side eight-hour login after a browser refresh.
  useEffect(() => {
    adminFetch(`${API}/v1/admin/session`, { credentials: "include" })
      .then((response) => {
        if (!response.ok) return;
        setAuthenticated(true);
        void loadQuestionLog();
        void loadApplications();
        void loadProfile();
        void loadRateLimits();
      })
      .finally(() => setCheckingSession(false));
  }, []);

  // Refreshes an open question log when Katy returns from testing another browser tab.
  useEffect(() => {
    if (!authenticated || collapsedSections.questions) return;
    const refreshOnFocus = () => void loadQuestionLog();
    window.addEventListener("focus", refreshOnFocus);
    return () => window.removeEventListener("focus", refreshOnFocus);
  }, [authenticated, collapsedSections.questions, questionLogPage]);

  // Loads one counted page of saved recruiter questions without reloading the browser.
  async function loadQuestionLog(requestedPage = questionLogPage) {
    setQuestionLogLoading(true);
    try {
      const query = requestedPage === 1
        ? ""
        : `?page=${requestedPage}&page_size=${QUESTION_LOG_PAGE_SIZE}`;
      const response = await adminFetch(`${API}/v1/admin/questions${query}`, {
        credentials: "include",
      });
      if (response.ok) {
        const data = await response.json();
        const loadedQuestions = data.questions ?? [];
        setQuestionLog(loadedQuestions);
        setQuestionLogPage(data.page ?? requestedPage);
        setQuestionLogTotal(data.total ?? loadedQuestions.length);
        setQuestionLogTotalPages(data.total_pages ?? 1);
      }
    } finally {
      setQuestionLogLoading(false);
    }
  }

  // Moves between recruiter-question pages while closing any unfinished correction.
  async function showQuestionPage(page: number) {
    if (page < 1 || page > questionLogTotalPages || page === questionLogPage) return;
    setQuestionEditId(null);
    setQuestionAnswer("");
    await loadQuestionLog(page);
  }

  // Clears only recruiter-question history after Katy confirms the permanent action.
  async function clearQuestionLog() {
    const confirmed = window.confirm(
      "Permanently clear all recruiter question history?\n\n" +
      "This does not remove your applications or approved Katy knowledge.",
    );
    if (!confirmed) return;
    setQuestionLogLoading(true);
    try {
      const response = await adminFetch(`${API}/v1/admin/questions`, {
        method: "DELETE",
        credentials: "include",
      });
      if (!response.ok) {
        setMessage("The recruiter question log could not be cleared.");
        return;
      }
      const data = await response.json();
      setQuestionEditId(null);
      setQuestionAnswer("");
      await loadQuestionLog(1);
      setMessage(
        data.deleted === 1
          ? "Cleared 1 recruiter question."
          : `Cleared ${data.deleted} recruiter questions.`,
      );
    } finally {
      setQuestionLogLoading(false);
    }
  }

  async function loadApplications() {
    const response = await adminFetch(`${API}/v1/admin/applications`, {
      credentials: "include",
    });
    if (response.ok) {
      const loaded: Application[] = (await response.json()).applications;
      setApplications(loaded);
      setUrlDrafts(
        Object.fromEntries(loaded.map((application) => [
          application.id,
          application.public_path ?? "",
        ])),
      );
    }
  }

  // Loads Katy's reusable professional knowledge for private review.
  async function loadProfile() {
    const response = await adminFetch(`${API}/v1/admin/profile`, {
      credentials: "include",
    });
    if (response.ok) {
      const data = await response.json();
      setProfileFacts(data.facts ?? []);
      setProfileSkills(data.skills ?? []);
      setAboutFacts(data.about ?? []);
    }
  }

  // Refreshes reusable knowledge without moving Katy away from the item she is reviewing.
  async function refreshProfileWithoutMoving() {
    const scrollLeft = window.scrollX;
    const scrollTop = window.scrollY;
    await loadProfile();
    if (scrollLeft === 0 && scrollTop === 0) return;
    window.requestAnimationFrame(() => window.scrollTo(scrollLeft, scrollTop));
  }

  // Loads the private cost and traffic controls without exposing them publicly.
  async function loadRateLimits() {
    const response = await adminFetch(`${API}/v1/admin/settings/rate-limits`, {
      credentials: "include",
    });
    if (!response.ok) return;
    const data = await response.json();
    if (
      typeof data.visitor_limit === "number"
      && typeof data.global_limit === "number"
      && typeof data.visitor_window_seconds === "number"
      && typeof data.global_window_seconds === "number"
    ) {
      setRateLimits(data);
    }
  }

  // Validates and saves both question ceilings while keeping their time windows fixed.
  async function saveRateLimits(event: FormEvent) {
    event.preventDefault();
    if (rateLimits.global_limit < rateLimits.visitor_limit) {
      setRateLimitMessage("The site-wide limit must be at least the per-visitor limit.");
      return;
    }
    setRateLimitMessage("Saving question limits…");
    const response = await adminFetch(`${API}/v1/admin/settings/rate-limits`, {
      method: "PUT",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        visitor_limit: rateLimits.visitor_limit,
        global_limit: rateLimits.global_limit,
      }),
    });
    if (!response.ok) {
      setRateLimitMessage("Those limits could not be saved. Please check the numbers.");
      return;
    }
    setRateLimits(await response.json());
    setRateLimitMessage("Question limits saved.");
  }

  // Reads a selected document as base64 so the API can process it without storing it.
  async function readFile(file: File) {
    return await new Promise<string>((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result).split(",", 2)[1] ?? "");
      reader.onerror = () => reject(new Error("That file could not be read."));
      reader.readAsDataURL(file);
    });
  }

  // Asks AI for evidence-backed drafts while leaving the saved profile unchanged.
  async function previewTeachingFacts(event: FormEvent) {
    event.preventDefault();
    if (!teachingText.trim() && !teachingFile) {
      setMessage("Paste information or choose a career document first.");
      return;
    }
    if (teachingFile && teachingFile.size > 5 * 1024 * 1024) {
      setMessage("Please choose a file smaller than 5 MB.");
      return;
    }
    setTeachingBusy(true);
    setMessage("Ask Katy is finding evidence-backed facts…");
    try {
      const body = teachingFile
        ? { filename: teachingFile.name, file_base64: await readFile(teachingFile) }
        : { pasted_text: teachingText.trim() };
      const response = await adminFetch(`${API}/v1/admin/profile/import/preview`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await response.json().catch(() => null);
      if (!response.ok) {
        setMessage(data?.detail ?? "That material could not be reviewed.");
        return;
      }
      setTeachingDrafts(data.facts.map((fact: Omit<ProfileFactDraft, "selected">) => ({
        ...fact,
        selected: true,
      })));
      setTeachingSkills((data.skills ?? []).map((skill: Omit<SkillDraft, "selected">) => ({
        ...skill,
        selected: true,
      })));
      setTeachingAbout((data.about ?? []).map((fact: Omit<AboutDraft, "selected">) => ({
        ...fact,
        selected: true,
      })));
      const candidateCount = (data.skills?.length ?? 0) + (data.about?.length ?? 0) + data.facts.length;
      setMessage(
        candidateCount
          ? "Review every draft carefully—AI suggestions can still be wrong."
          : "No new supported facts were found in that material.",
      );
    } catch {
      setMessage("That material could not be reviewed.");
    } finally {
      setTeachingBusy(false);
    }
  }

  // Saves only the checked facts after Katy has had a chance to edit each one.
  async function approveTeachingFacts() {
    const skills = teachingSkills
      .filter((skill) => skill.selected)
      .map(({ selected: _selected, ...skill }) => ({
        ...skill,
        name: skill.name.trim(),
        used_at: skill.used_at.trim(),
        detail: skill.detail.trim(),
        evidence_quote: skill.evidence_quote.trim(),
        years: skill.years === null || skill.years === undefined ? null : Number(skill.years),
      }))
      .filter((skill) => skill.name.length > 0);
    const about = teachingAbout
      .filter((fact) => fact.selected)
      .map(({ selected: _selected, ...fact }) => ({
        ...fact,
        title: fact.title.trim(),
        statement: fact.statement.trim(),
        evidence_quote: fact.evidence_quote.trim(),
      }))
      .filter((fact) => fact.title.length >= 2 && fact.statement.length >= 3);
    const facts = teachingDrafts
      .filter((fact) => fact.selected)
      .map(({ question, answer }) => ({ question: question.trim(), answer: answer.trim() }))
      .filter((fact) => fact.question.length >= 3 && fact.answer.length >= 3);
    if (!skills.length && !about.length && !facts.length) {
      setMessage("Select at least one complete fact to approve.");
      return;
    }
    setTeachingBusy(true);
    try {
      const response = await adminFetch(`${API}/v1/admin/profile/import/approve`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ skills, about, facts }),
      });
      if (!response.ok) {
        setMessage("Those facts could not be saved.");
        return;
      }
      const data = await response.json();
      await refreshProfileWithoutMoving();
      setTeachingDrafts([]);
      setTeachingSkills([]);
      setTeachingAbout([]);
      setTeachingText("");
      setTeachingFile(null);
      setMessage(`${data.saved} reusable ${data.saved === 1 ? "fact" : "facts"} approved.`);
    } catch {
      setMessage("Those facts could not be saved.");
    } finally {
      setTeachingBusy(false);
    }
  }

  // Updates one editable field or checkbox in an AI-proposed fact.
  function updateTeachingDraft(
    index: number,
    key: "question" | "answer" | "selected",
    value: string | boolean,
  ) {
    setTeachingDrafts(teachingDrafts.map((fact, factIndex) => (
      factIndex === index ? { ...fact, [key]: value } : fact
    )));
  }

  // Updates one editable field or checkbox in a proposed skill.
  function updateSkillDraft(
    index: number,
    key: keyof SkillDraft,
    value: string | number | boolean | null,
  ) {
    setTeachingSkills(teachingSkills.map((skill, skillIndex) => (
      skillIndex === index ? { ...skill, [key]: value } : skill
    )));
  }

  // Updates one editable field or checkbox in a proposed About Katy statement.
  function updateAboutDraft(
    index: number,
    key: keyof AboutDraft,
    value: string | boolean,
  ) {
    setTeachingAbout(teachingAbout.map((fact, factIndex) => (
      factIndex === index ? { ...fact, [key]: value } : fact
    )));
  }

  // Adds an empty skill card for knowledge Katy wants to enter directly.
  function addManualSkill() {
    setTeachingSkills([...teachingSkills, {
      name: "",
      proficiency: null,
      years: null,
      used_at: "",
      detail: "",
      evidence_quote: "",
      selected: true,
    }]);
  }

  // Adds an empty About Katy card for a quality that does not belong on a skill scale.
  function addManualAboutFact() {
    setTeachingAbout([...teachingAbout, {
      title: "",
      statement: "",
      evidence_quote: "",
      selected: true,
    }]);
  }

  // Expands or minimizes one section without unmounting its in-progress controls.
  function toggleSection(section: AdminSection) {
    const isOpening = collapsedSections[section];
    setCollapsedSections((current) => ({
      ...current,
      [section]: !current[section],
    }));
    if (section === "questions" && isOpening) void loadQuestionLog();
  }

  // Opens one navigation target and minimizes the other dashboard sections.
  function focusSection(section: AdminSection) {
    setCollapsedSections({
      teach: section !== "teach",
      knowledge: section !== "knowledge",
      "new-application": section !== "new-application",
      "application-control": section !== "application-control",
      settings: section !== "settings",
      questions: section !== "questions",
    });
    if (section === "questions") void loadQuestionLog();
  }

  async function login(event: FormEvent) {
    event.preventDefault();
    setMessage("Signing in…");
    const response = await adminFetch(`${API}/v1/admin/login`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password }),
    });
    if (!response.ok) {
      setMessage("That password didn’t work.");
      return;
    }
    setAuthenticated(true);
    setCheckingSession(false);
    setPassword("");
    setMessage("");
    void loadQuestionLog();
    void loadApplications();
    void loadProfile();
    void loadRateLimits();
  }

  // Ends the backend session and removes private dashboard data from browser memory.
  async function logout() {
    setSigningOut(true);
    setMessage("");
    const response = await adminFetch(`${API}/v1/admin/logout`, {
      method: "POST",
      credentials: "include",
    });
    if (!response.ok) {
      setMessage("Ask Katy couldn’t sign you out. Please try again.");
      setSigningOut(false);
      return;
    }
    setAuthenticated(false);
    setApplications([]);
    setPreview(null);
    setEditingApplication(null);
    setApplicationSaveError("");
    setUrlDrafts({});
    setProfileFacts([]);
    setProfileSkills([]);
    setAboutFacts([]);
    setQuestionLog([]);
    setQuestionLogPage(1);
    setQuestionLogTotal(0);
    setQuestionLogTotalPages(1);
    setQuestionEditId(null);
    setQuestionAnswer("");
    setResult(null);
    setQuestions([]);
    setAnswers([]);
    setReusableAnswers([]);
    setTeachingText("");
    setTeachingFile(null);
    setUploadedResume(null);
    setEditingResumeUpload(null);
    setResumeUploadBusy(false);
    setResumeUploadError("");
    setTeachingDrafts([]);
    setTeachingSkills([]);
    setTeachingAbout([]);
    setKnowledgeEdit(null);
    setPassword("");
    setMessage("You’re signed out.");
    setSigningOut(false);
  }

  async function analyze(event: FormEvent) {
    event.preventDefault();
    setMessage("Ask Katy is reviewing the role…");
    setResult(null);
    const response = await adminFetch(`${API}/v1/admin/intake/questions`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(intake),
    });
    if (!response.ok) {
      setMessage("I couldn’t generate questions yet. Check the API and try again.");
      return;
    }
    const data = await response.json();
    const proofreadIntroduction = typeof data.introduction === "string"
      ? data.introduction.trim()
      : "";
    const reviewedQuestions: IntakeQuestion[] = (
      data.questions as IntakeQuestionState[]
    ).map(normalizeIntakeQuestion);
    if (proofreadIntroduction) {
      setIntake((current) => ({ ...current, notes: proofreadIntroduction }));
    }
    setQuestions(reviewedQuestions);
    setAnswers(reviewedQuestions.map((question) => question.suggested_answer));
    setReusableAnswers(reviewedQuestions.map(
      (question) => !question.suggested_answer,
    ));
    setMessage("");
  }

  async function createDraft(event: FormEvent) {
    event.preventDefault();
    if (uploadedResume && uploadedResume.size > 5 * 1024 * 1024) {
      setMessage("Please choose a PDF résumé smaller than 5 MB.");
      return;
    }
    setMessage(
      uploadedResume
        ? "Creating the private page with your existing résumé…"
        : "Creating the private page, tailored résumé, and cover letter…",
    );
    let uploadedResumePayload = null;
    try {
      uploadedResumePayload = uploadedResume
        ? {
            filename: uploadedResume.name,
            file_base64: await readFile(uploadedResume),
          }
        : null;
    } catch {
      setMessage("That PDF résumé could not be read. Please choose it again.");
      return;
    }
    const response = await adminFetch(`${API}/v1/admin/applications`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ...intake,
        uploaded_resume: uploadedResumePayload,
        answers: questions
          .map((question, index) => {
            const item = normalizeIntakeQuestion(question);
            return {
              question: item.question,
              answer: answers[index]?.trim() ?? "",
              reusable: reusableAnswers[index] ?? true,
            };
          })
          .filter((item) => item.answer.length > 0),
      }),
    });
    if (!response.ok) {
      const data = await response.json().catch(() => null);
      setMessage(data?.detail ?? "The draft could not be created.");
      return;
    }
    setResult(await response.json());
    setQuestions([]);
    setAnswers([]);
    setReusableAnswers([]);
    setUploadedResume(null);
    setIntake({
      company: "",
      role: "",
      job_description: "",
      company_interest: "",
      notes: "",
    });
    setMessage("");
    void loadApplications();
    void loadProfile();
  }

  async function previewApplication(applicationId: string) {
    const response = await adminFetch(
      `${API}/v1/admin/applications/${applicationId}`,
      { credentials: "include" },
    );
    if (!response.ok) {
      setMessage("That preview could not be loaded.");
      return;
    }
    setPreview(await response.json());
    setMessage("");
  }

  // Rebuilds job documents from saved approved knowledge after a replacement warning.
  async function regenerateApplicationDocuments(application: Application) {
    const confirmed = window.confirm(
      `Regenerate the résumé and cover letter for ${application.page.role} at ${application.page.company}? This replaces any manual edits in those two documents. If the application is published, it will return to draft until you review and publish it again.`,
    );
    if (!confirmed) return;
    setMessage("Ask Katy is rebuilding the job-specific résumé and cover letter…");
    const response = await adminFetch(
      `${API}/v1/admin/applications/${application.id}/documents/regenerate`,
      { method: "POST", credentials: "include" },
    );
    if (!response.ok) {
      const data = await response.json().catch(() => null);
      setMessage(data?.detail ?? "Those documents could not be regenerated.");
      return;
    }
    const updated = await response.json();
    setEditingApplication(updated);
    setPreview(null);
    setApplicationSaveError("");
    setMessage("New document drafts are ready below. The application is private until you review and publish it again.");
    void loadApplications();
  }

  // Loads the complete saved application into an application-specific correction form.
  async function beginApplicationEdit(applicationId: string) {
    const response = await adminFetch(`${API}/v1/admin/applications/${applicationId}`, {
      credentials: "include",
    });
    if (!response.ok) {
      setMessage("That application could not be opened for editing.");
      return;
    }
    const application = await response.json();
    setEditingApplication({
      ...application,
      resume: application.resume ?? {
        summary: application.page.introduction,
        skills: [],
        experience: [],
        education: [],
      },
      cover_letter_pitch:
        application.cover_letter_pitch ?? application.page.introduction,
    });
    setApplicationSaveError("");
    setEditingResumeUpload(null);
    setResumeUploadError("");
    setPreview(null);
    setMessage("");
  }

  // Uploads one premade PDF for the application currently open in the editor.
  async function uploadPremadeResume() {
    if (!editingApplication || !editingResumeUpload) return;
    if (editingResumeUpload.size > 5 * 1024 * 1024) {
      setResumeUploadError("Please choose a PDF résumé smaller than 5 MB.");
      return;
    }
    setResumeUploadBusy(true);
    setResumeUploadError("");
    try {
      const response = await adminFetch(
        `${API}/v1/admin/applications/${editingApplication.id}/resume`,
        {
          method: "PUT",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            filename: editingResumeUpload.name,
            file_base64: await readFile(editingResumeUpload),
          }),
        },
      );
      if (!response.ok) {
        const data = await response.json().catch(() => null);
        setResumeUploadError(data?.detail ?? "That résumé could not be uploaded.");
        return;
      }
      setEditingApplication(await response.json());
      setEditingResumeUpload(null);
      setMessage("Premade résumé saved for this application.");
      void loadApplications();
    } catch {
      setResumeUploadError("That PDF résumé could not be read. Please choose it again.");
    } finally {
      setResumeUploadBusy(false);
    }
  }

  // Removes one premade PDF while keeping the generated résumé as a fallback.
  async function removePremadeResume() {
    if (!editingApplication) return;
    setResumeUploadBusy(true);
    setResumeUploadError("");
    try {
      const response = await adminFetch(
        `${API}/v1/admin/applications/${editingApplication.id}/resume`,
        { method: "DELETE", credentials: "include" },
      );
      if (!response.ok) {
        const data = await response.json().catch(() => null);
        setResumeUploadError(data?.detail ?? "That résumé could not be removed.");
        return;
      }
      setEditingApplication(await response.json());
      setEditingResumeUpload(null);
      setMessage("Premade résumé removed. Recruiters will see the generated résumé.");
      void loadApplications();
    } finally {
      setResumeUploadBusy(false);
    }
  }

  // Updates one Q&A row in the local application editor before anything is saved.
  function updateApplicationAnswer(
    index: number,
    key: "question" | "answer",
    value: string,
  ) {
    if (!editingApplication) return;
    const nextAnswers = [...(editingApplication.profile_answers ?? [])];
    nextAnswers[index] = { ...nextAnswers[index], [key]: value };
    setEditingApplication({ ...editingApplication, profile_answers: nextAnswers });
  }

  // Adds one blank application-only answer row to the correction form.
  function addApplicationAnswer() {
    if (!editingApplication) return;
    setEditingApplication({
      ...editingApplication,
      profile_answers: [
        ...(editingApplication.profile_answers ?? []),
        { question: "", answer: "" },
      ],
    });
  }

  // Removes one application-only answer row before the corrected content is saved.
  function removeApplicationAnswer(index: number) {
    if (!editingApplication) return;
    setEditingApplication({
      ...editingApplication,
      profile_answers: (editingApplication.profile_answers ?? []).filter(
        (_answer, answerIndex) => answerIndex !== index,
      ),
    });
  }

  // Updates one field in a job-specific résumé position before saving.
  function updateResumeExperience(
    index: number,
    key: "company" | "role" | "dates" | "bullets",
    value: string,
  ) {
    if (!editingApplication?.resume) return;
    const experience = [...editingApplication.resume.experience];
    experience[index] = {
      ...experience[index],
      [key]: key === "bullets" ? value.split("\n") : value,
    };
    setEditingApplication({
      ...editingApplication,
      resume: { ...editingApplication.resume, experience },
    });
  }

  // Adds one blank résumé position for an approved recent job.
  function addResumeExperience() {
    if (!editingApplication?.resume) return;
    setEditingApplication({
      ...editingApplication,
      resume: {
        ...editingApplication.resume,
        experience: [
          ...editingApplication.resume.experience,
          { company: "", role: "", dates: "", bullets: [] },
        ],
      },
    });
  }

  // Removes one résumé position from this application only.
  function removeResumeExperience(index: number) {
    if (!editingApplication?.resume) return;
    setEditingApplication({
      ...editingApplication,
      resume: {
        ...editingApplication.resume,
        experience: editingApplication.resume.experience.filter(
          (_item, itemIndex) => itemIndex !== index,
        ),
      },
    });
  }

  // Updates one education entry in the application-specific résumé.
  function updateResumeEducation(
    index: number,
    key: "school" | "credential" | "dates",
    value: string,
  ) {
    if (!editingApplication?.resume) return;
    const education = [...editingApplication.resume.education];
    education[index] = { ...education[index], [key]: value };
    setEditingApplication({
      ...editingApplication,
      resume: { ...editingApplication.resume, education },
    });
  }

  // Adds one blank education entry when approved knowledge supports it.
  function addResumeEducation() {
    if (!editingApplication?.resume) return;
    setEditingApplication({
      ...editingApplication,
      resume: {
        ...editingApplication.resume,
        education: [
          ...editingApplication.resume.education,
          { school: "", credential: "", dates: "" },
        ],
      },
    });
  }

  // Removes one education entry from this application only.
  function removeResumeEducation(index: number) {
    if (!editingApplication?.resume) return;
    setEditingApplication({
      ...editingApplication,
      resume: {
        ...editingApplication.resume,
        education: editingApplication.resume.education.filter(
          (_item, itemIndex) => itemIndex !== index,
        ),
      },
    });
  }

  // Saves preview corrections without changing the application's URL or reusable profile.
  async function saveApplicationContent(event: FormEvent) {
    event.preventDefault();
    if (!editingApplication) return;
    setApplicationSaveError("");
    setApplicationSaving(true);
    try {
      const response = await adminFetch(
        `${API}/v1/admin/applications/${editingApplication.id}`,
        {
          method: "PUT",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            company: editingApplication.page.company,
            role: editingApplication.page.role,
            job_description: editingApplication.job_description ?? "",
            company_interest: editingApplication.company_interest ?? "",
            introduction: editingApplication.page.introduction,
            answers: editingApplication.profile_answers ?? [],
            resume: {
              ...(editingApplication.resume ?? {
                summary: editingApplication.page.introduction,
                skills: [],
                experience: [],
                education: [],
              }),
              skills: (editingApplication.resume?.skills ?? []).filter(
                (skill) => skill.trim().length > 0,
              ),
              experience: (editingApplication.resume?.experience ?? []).map((item) => ({
                ...item,
                bullets: item.bullets.filter((bullet) => bullet.trim().length > 0),
              })),
            },
            cover_letter_pitch:
              editingApplication.cover_letter_pitch ?? editingApplication.page.introduction,
          }),
        },
      );
      if (!response.ok) {
        const data = await response.json().catch(() => null);
        setApplicationSaveError(
          typeof data?.detail === "string"
            ? data.detail
            : "Those application changes could not be saved.",
        );
        return;
      }
      const wasPublished = editingApplication.status === "published";
      setEditingApplication(null);
      setMessage(
        wasPublished
          ? "Application updated. Because it is published, the changes are live now."
          : "Application updated. Preview it again before publishing.",
      );
      void loadApplications();
    } catch {
      setApplicationSaveError(
        "The application could not reach the local backend. Restart Ask Katy and try again.",
      );
    } finally {
      setApplicationSaving(false);
    }
  }

  async function updateApplication(
    applicationId: string,
    action: "publish" | "unpublish" | "revoke" | "unrevoke",
  ) {
    const response = await adminFetch(
      `${API}/v1/admin/applications/${applicationId}/${action}`,
      { method: "POST", credentials: "include" },
    );
    if (!response.ok) {
      const data = await response.json().catch(() => null);
      setMessage(data?.detail ?? "That change could not be saved.");
      return;
    }
    await response.json();
    if (preview?.id === applicationId) {
      setPreview(null);
    }
    setMessage(
      action === "publish"
        ? "Published. The private employer link is active."
        : action === "unpublish"
          ? "Unpublished. The link is paused."
          : action === "revoke"
            ? "Revoked. This URL is no longer available to visitors."
            : action === "unrevoke"
              ? "Restored as a draft. Publish it when the link should be active again."
              : "Saved.",
    );
    void loadApplications();
  }

  // Saves a hand-edited company-and-role path without changing the application content.
  async function saveApplicationUrl(applicationId: string) {
    const publicPath = urlDrafts[applicationId]?.trim();
    const response = await adminFetch(
      `${API}/v1/admin/applications/${applicationId}/url`,
      {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ public_path: publicPath }),
      },
    );
    if (!response.ok) {
      const data = await response.json().catch(() => null);
      setMessage(data?.detail ?? "That URL could not be saved.");
      return;
    }
    setMessage("URL saved. If this page is published, the new address is active now.");
    void loadApplications();
  }

  // Permanently deletes an application only after an explicit browser confirmation.
  async function deleteApplication(application: Application) {
    const confirmed = window.confirm(
      `Permanently delete ${application.page.role} at ${application.page.company}? This also deletes its recruiter-question history and cannot be undone.`,
    );
    if (!confirmed) return;
    const response = await adminFetch(
      `${API}/v1/admin/applications/${application.id}`,
      { method: "DELETE", credentials: "include" },
    );
    if (!response.ok) {
      setMessage("That application could not be deleted.");
      return;
    }
    if (preview?.id === application.id) setPreview(null);
    setMessage(`${application.page.company} application deleted.`);
    void loadApplications();
    void loadQuestionLog();
  }

  // Saves an inline correction to reusable knowledge and refreshes every bot's facts.
  async function saveKnowledgeEdit() {
    if (!knowledgeEdit) return;
    const endpoint = knowledgeEdit.kind === "skill"
      ? `skills/${knowledgeEdit.item.id}`
      : knowledgeEdit.kind === "about"
        ? `about/${knowledgeEdit.item.id}`
        : String(knowledgeEdit.item.id);
    const { id: _id, ...payload } = knowledgeEdit.item;
    const response = await adminFetch(`${API}/v1/admin/profile/${endpoint}`, {
      method: "PUT",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      setMessage("That knowledge correction could not be saved.");
      return;
    }
    await refreshProfileWithoutMoving();
    setKnowledgeEdit(null);
    setMessage("Reusable knowledge corrected. Future answers will use the updated information.");
  }

  // Opens a recruiter answer for correction without changing it until Katy saves.
  function beginQuestionCorrection(entry: QuestionEntry) {
    setQuestionEditId(entry.id);
    setQuestionAnswer(entry.outcome === "answered" ? entry.answer : "");
    setQuestionReusable(true);
  }

  // Saves a corrected answer globally or only for the application that received it.
  async function saveQuestionCorrection(entry: QuestionEntry) {
    const response = await adminFetch(`${API}/v1/admin/questions/${entry.id}`, {
      method: "PUT",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ answer: questionAnswer, reusable: questionReusable }),
    });
    if (!response.ok) {
      setMessage("That corrected answer could not be saved.");
      return;
    }
    setQuestionEditId(null);
    setQuestionAnswer("");
    setMessage(
      questionReusable
        ? "Answer corrected and added to every application bot’s knowledge."
        : "Answer corrected for this application only.",
    );
    void loadQuestionLog();
    if (questionReusable) void loadProfile();
  }

  // Removes one reusable fact after confirmation while preserving application history.
  async function deleteProfileFact(fact: ProfileFact) {
    if (!window.confirm(`Remove this from Katy’s reusable profile?\n\n${fact.question}`)) {
      return;
    }
    const response = await adminFetch(`${API}/v1/admin/profile/${fact.id}`, {
      method: "DELETE",
      credentials: "include",
    });
    if (!response.ok) {
      setMessage("That profile fact could not be removed.");
      return;
    }
    setMessage("Reusable profile updated.");
    await refreshProfileWithoutMoving();
  }

  // Removes one saved skill after confirmation without changing other knowledge.
  async function deleteProfileSkill(skill: ProfileSkill) {
    if (!window.confirm(`Remove ${skill.name} from Katy’s skill list?`)) return;
    const response = await adminFetch(`${API}/v1/admin/profile/skills/${skill.id}`, {
      method: "DELETE",
      credentials: "include",
    });
    if (!response.ok) {
      setMessage("That skill could not be removed.");
      return;
    }
    setMessage("Skill list updated.");
    await refreshProfileWithoutMoving();
  }

  // Removes one saved About Katy statement after confirmation.
  async function deleteAboutFact(fact: AboutFact) {
    if (!window.confirm(`Remove “${fact.title}” from About Katy?`)) return;
    const response = await adminFetch(`${API}/v1/admin/profile/about/${fact.id}`, {
      method: "DELETE",
      credentials: "include",
    });
    if (!response.ok) {
      setMessage("That About Katy fact could not be removed.");
      return;
    }
    setMessage("About Katy updated.");
    await refreshProfileWithoutMoving();
  }

  function field(key: keyof Intake, value: string) {
    setIntake({ ...intake, [key]: value });
  }

  const approvedKnowledgeCount = profileFacts.length + profileSkills.length + aboutFacts.length;
  const teachingCandidateCount = teachingDrafts.length + teachingSkills.length + teachingAbout.length;
  const selectedKnowledgeCount =
    teachingDrafts.filter((fact) => fact.selected).length
    + teachingSkills.filter((skill) => skill.selected).length
    + teachingAbout.filter((fact) => fact.selected).length;

  return (
    <main className="admin-shell">
      {connectionError && (
        <aside className="admin-error-toast" role="alert">
          <div>
            <strong>Ask Katy needs attention</strong>
            <p>{connectionError}</p>
          </div>
          <button type="button" onClick={() => setConnectionError("")}>Dismiss</button>
        </aside>
      )}
      <section className="admin-window">
        <header className="terminal-bar">
          <div className="traffic-lights"><span></span><span></span><span></span></div>
          <p>katy@codes — private application studio</p>
          <div className="admin-session-actions">
            <span className="status">private</span>
            {authenticated && (
              <button type="button" onClick={() => void logout()} disabled={signingOut}>
                {signingOut ? "Signing out…" : "Log out"}
              </button>
            )}
          </div>
        </header>
        <div className="admin-body">
          <p className="eyebrow">ASK KATY ADMIN</p>
          <h1>{authenticated ? "Your application dashboard." : "Build a tailored application."}</h1>
          <p className="dek">
            {authenticated
              ? "Open, edit, publish, or remove every tailored application from one private place."
              : "Paste the role, let AI identify the missing evidence, then answer only what’s true. Drafts stay private until you review and publish them."}
          </p>

          {authenticated && (
            <>
              <nav className="admin-nav" aria-label="Admin sections">
                <a href="#application-control" onClick={() => focusSection("application-control")}>Application control</a>
                <a href="#teach" onClick={() => focusSection("teach")}>Teach Ask Katy</a>
                <a href="#knowledge" onClick={() => focusSection("knowledge")}>Katy knowledge</a>
                <a href="#new-application" onClick={() => focusSection("new-application")}>Create new</a>
                <a href="#settings" onClick={() => focusSection("settings")}>Question limits</a>
                <a href="#questions" onClick={() => focusSection("questions")}>Question log</a>
              </nav>
              <section className="teach-katy collapsible-admin-section" id="teach">
                <SectionToggle
                  label="Teach Ask Katy"
                  section="teach"
                  collapsed={collapsedSections.teach}
                  onToggle={toggleSection}
                />
                <div className="teach-heading">
                  <div>
                    <p className="eyebrow">TEACH ASK KATY</p>
                    <h2>Turn your career history into approved knowledge</h2>
                  </div>
                  <div className="knowledge-meter" aria-label={`${approvedKnowledgeCount} approved knowledge items`}>
                    <strong>{approvedKnowledgeCount}</strong>
                    <span>knowledge items</span>
                    <i><b style={{ width: `${Math.min(100, approvedKnowledgeCount / 20 * 100)}%` }} /></i>
                  </div>
                </div>
                <div id="teach-content" hidden={collapsedSections.teach}>
                <p>
                  Paste LinkedIn text or upload a résumé. AI sorts supported information into
                  skills, About Katy, and other useful knowledge. You review every word.
                </p>
                <form className="teach-form" onSubmit={previewTeachingFacts}>
                  <label>
                    Paste professional information
                    <textarea
                      rows={7}
                      value={teachingText}
                      placeholder="Paste résumé, LinkedIn, portfolio, or career notes here…"
                      onChange={(event) => {
                        setTeachingText(event.target.value);
                        if (event.target.value) setTeachingFile(null);
                      }}
                    />
                  </label>
                  <span className="teach-or">or</span>
                  <label className="file-picker">
                    Upload PDF, DOCX, TXT, or Markdown
                    <input
                      type="file"
                      accept=".pdf,.docx,.txt,.md"
                      onChange={(event) => {
                        const file = event.target.files?.[0] ?? null;
                        setTeachingFile(file);
                        if (file) setTeachingText("");
                      }}
                    />
                    <small>{teachingFile?.name ?? "Maximum 5 MB · processed in memory, then discarded"}</small>
                  </label>
                  <button disabled={teachingBusy}>
                    {teachingBusy ? "Reviewing…" : "Let AI organize this →"}
                  </button>
                </form>
                <div className="manual-knowledge-actions">
                  <span>Or add something directly:</span>
                  <button type="button" onClick={addManualSkill}>+ Add a skill</button>
                  <button type="button" onClick={addManualAboutFact}>+ Add About Katy</button>
                </div>
                <details className="proficiency-guide">
                  <summary>What do the proficiency levels mean?</summary>
                  <dl>
                    <div><dt>Learning</dt><dd>Actively learning; not yet using it independently.</dd></div>
                    <div><dt>Familiar</dt><dd>Understands the basics and has limited hands-on practice.</dd></div>
                    <div><dt>Working knowledge</dt><dd>Can complete routine tasks, sometimes using references.</dd></div>
                    <div><dt>Proficient</dt><dd>Can work independently on typical real-world tasks.</dd></div>
                    <div><dt>Advanced</dt><dd>Handles complex work and can guide other people.</dd></div>
                    <div><dt>Expert</dt><dd>Deep authority who can design, teach, and solve novel problems.</dd></div>
                  </dl>
                </details>
                {teachingCandidateCount > 0 && (
                  <div className="teaching-review">
                    <div>
                      <h3>Review before teaching</h3>
                      <p>Nothing is saved until you approve it.</p>
                    </div>
                    {teachingSkills.length > 0 && <h4>Skills</h4>}
                    {teachingSkills.map((skill, index) => (
                      <article className="skill-draft" key={`${skill.name}-${index}`}>
                        <label className="teach-select">
                          <input
                            type="checkbox"
                            checked={skill.selected}
                            onChange={(event) => updateSkillDraft(index, "selected", event.target.checked)}
                          />
                          Approve this skill
                        </label>
                        <div className="skill-fields">
                          <label>
                            Skill
                            <input
                              aria-label={`Skill name ${index + 1}`}
                              value={skill.name}
                              onChange={(event) => updateSkillDraft(index, "name", event.target.value)}
                            />
                          </label>
                          <label>
                            Proficiency <small>Optional</small>
                            <select
                              aria-label={`Skill proficiency ${index + 1}`}
                              value={skill.proficiency ?? ""}
                              onChange={(event) => updateSkillDraft(
                                index,
                                "proficiency",
                                event.target.value || null,
                              )}
                            >
                              <option value="">Not specified</option>
                              <option value="learning">Learning</option>
                              <option value="familiar">Familiar</option>
                              <option value="working">Working knowledge</option>
                              <option value="proficient">Proficient</option>
                              <option value="advanced">Advanced</option>
                              <option value="expert">Expert</option>
                            </select>
                          </label>
                          <label>
                            Years <small>Optional</small>
                            <input
                              type="number"
                              min="0"
                              max="60"
                              step="0.5"
                              aria-label={`Skill years ${index + 1}`}
                              value={skill.years ?? ""}
                              onChange={(event) => updateSkillDraft(
                                index,
                                "years",
                                event.target.value === "" ? null : Number(event.target.value),
                              )}
                            />
                          </label>
                        </div>
                        <label>
                          Where did you use it? <small>Optional company and role</small>
                          <input
                            aria-label={`Skill job ${index + 1}`}
                            value={skill.used_at}
                            onChange={(event) => updateSkillDraft(index, "used_at", event.target.value)}
                            placeholder="CD Baby — Software Engineer"
                          />
                        </label>
                        <label>
                          What did you do with it? <small>Optional</small>
                          <textarea
                            aria-label={`Skill detail ${index + 1}`}
                            rows={3}
                            value={skill.detail}
                            onChange={(event) => updateSkillDraft(index, "detail", event.target.value)}
                          />
                        </label>
                        {skill.evidence_quote && <blockquote>Based on: “{skill.evidence_quote}”</blockquote>}
                      </article>
                    ))}
                    {teachingAbout.length > 0 && <h4>About Katy</h4>}
                    {teachingAbout.map((fact, index) => (
                      <article className="about-draft" key={`${fact.title}-${index}`}>
                        <label className="teach-select">
                          <input
                            type="checkbox"
                            checked={fact.selected}
                            onChange={(event) => updateAboutDraft(index, "selected", event.target.checked)}
                          />
                          Approve this About Katy item
                        </label>
                        <label>
                          Short label
                          <input
                            aria-label={`About title ${index + 1}`}
                            value={fact.title}
                            onChange={(event) => updateAboutDraft(index, "title", event.target.value)}
                            placeholder="People skills"
                          />
                        </label>
                        <label>
                          What should Ask Katy know?
                          <textarea
                            aria-label={`About statement ${index + 1}`}
                            rows={3}
                            value={fact.statement}
                            onChange={(event) => updateAboutDraft(index, "statement", event.target.value)}
                          />
                        </label>
                        {fact.evidence_quote && <blockquote>Based on: “{fact.evidence_quote}”</blockquote>}
                      </article>
                    ))}
                    {teachingDrafts.length > 0 && <h4>Other professional knowledge</h4>}
                    {teachingDrafts.map((fact, index) => (
                      <article key={`${fact.evidence_quote}-${index}`}>
                        <label className="teach-select">
                          <input
                            type="checkbox"
                            checked={fact.selected}
                            onChange={(event) => updateTeachingDraft(index, "selected", event.target.checked)}
                          />
                          Approve this fact
                        </label>
                        <label>
                          Knowledge prompt
                          <input
                            aria-label={`Draft question ${index + 1}`}
                            value={fact.question}
                            onChange={(event) => updateTeachingDraft(index, "question", event.target.value)}
                          />
                        </label>
                        <label>
                          Approved statement
                          <textarea
                            aria-label={`Draft answer ${index + 1}`}
                            rows={3}
                            value={fact.answer}
                            onChange={(event) => updateTeachingDraft(index, "answer", event.target.value)}
                          />
                        </label>
                        <blockquote>Based on: “{fact.evidence_quote}”</blockquote>
                      </article>
                    ))}
                    <button
                      className="approve-facts"
                      disabled={teachingBusy}
                      onClick={() => void approveTeachingFacts()}
                    >
                      Approve {selectedKnowledgeCount}{" "}
                      {selectedKnowledgeCount === 1 ? "item" : "items"}
                    </button>
                  </div>
                )}
                </div>
              </section>
              <section className="profile-knowledge collapsible-admin-section" id="knowledge">
                <SectionToggle
                  label="Katy Knowledge"
                  section="knowledge"
                  collapsed={collapsedSections.knowledge}
                  onToggle={toggleSection}
                />
                <p className="eyebrow">REUSABLE KATY KNOWLEDGE</p>
                <h2>What every application bot knows</h2>
                <div id="knowledge-content" hidden={collapsedSections.knowledge}>
                <p>
                  These approved skills, qualities, and professional facts can answer questions for any job.
                  Company-specific answers stay separate when reuse is turned off.
                </p>
                <p className="knowledge-help">
                  Use <strong>Edit</strong> to correct saved information, <strong>Remove</strong> to forget it,
                  or <a href="#teach" onClick={() => focusSection("teach")}>Teach Ask Katy</a> to add something new.
                </p>
                {approvedKnowledgeCount === 0 && <p>No reusable knowledge yet.</p>}
                {profileSkills.length > 0 && (
                  <div className="knowledge-group">
                    <h3>Skills</h3>
                    <div className="skill-library">
                      {profileSkills.map((skill) => (
                        <article key={skill.id}>
                          {knowledgeEdit?.kind === "skill" && knowledgeEdit.item.id === skill.id ? (
                            <div className="knowledge-edit">
                              <label>Skill name<input value={knowledgeEdit.item.name} onChange={(event) => setKnowledgeEdit({ kind: "skill", item: { ...knowledgeEdit.item, name: event.target.value } })} /></label>
                              <label>Proficiency<select value={knowledgeEdit.item.proficiency ?? ""} onChange={(event) => setKnowledgeEdit({ kind: "skill", item: { ...knowledgeEdit.item, proficiency: (event.target.value || null) as ProfileSkill["proficiency"] } })}>
                                <option value="">Not specified</option><option value="learning">Learning</option><option value="familiar">Familiar</option><option value="working">Working knowledge</option><option value="proficient">Proficient</option><option value="advanced">Advanced</option><option value="expert">Expert</option>
                              </select></label>
                              <label>Years<input type="number" min="0" step="0.5" value={knowledgeEdit.item.years ?? ""} onChange={(event) => setKnowledgeEdit({ kind: "skill", item: { ...knowledgeEdit.item, years: event.target.value ? Number(event.target.value) : null } })} /></label>
                              <label>Where I used it<input value={knowledgeEdit.item.used_at} onChange={(event) => setKnowledgeEdit({ kind: "skill", item: { ...knowledgeEdit.item, used_at: event.target.value } })} /></label>
                              <label>Details<textarea value={knowledgeEdit.item.detail} onChange={(event) => setKnowledgeEdit({ kind: "skill", item: { ...knowledgeEdit.item, detail: event.target.value } })} /></label>
                              <div><button onClick={() => void saveKnowledgeEdit()}>Save changes</button><button onClick={() => setKnowledgeEdit(null)}>Cancel</button></div>
                            </div>
                          ) : (<>
                          <div className="skill-card-heading">
                            <strong>{skill.name}</strong>
                            {skill.proficiency && <span>{skill.proficiency.replace("working", "working knowledge")}</span>}
                          </div>
                          <p>
                            {skill.years !== null && <small>{skill.years} years</small>}
                            {skill.used_at && <small>{skill.used_at}</small>}
                          </p>
                          {skill.detail && <p>{skill.detail}</p>}
                          <button onClick={() => setKnowledgeEdit({ kind: "skill", item: { ...skill } })}>
                            Edit skill
                          </button>{" "}
                          <button className="danger" onClick={() => void deleteProfileSkill(skill)}>
                            Remove skill
                          </button>
                          </>)}
                        </article>
                      ))}
                    </div>
                  </div>
                )}
                {aboutFacts.length > 0 && (
                  <div className="knowledge-group">
                    <h3>About Katy</h3>
                    <div>
                      {aboutFacts.map((fact) => (
                        <article key={fact.id}>
                          {knowledgeEdit?.kind === "about" && knowledgeEdit.item.id === fact.id ? (
                            <div className="knowledge-edit">
                              <label>Title<input value={knowledgeEdit.item.title} onChange={(event) => setKnowledgeEdit({ kind: "about", item: { ...knowledgeEdit.item, title: event.target.value } })} /></label>
                              <label>Statement<textarea value={knowledgeEdit.item.statement} onChange={(event) => setKnowledgeEdit({ kind: "about", item: { ...knowledgeEdit.item, statement: event.target.value } })} /></label>
                              <div><button onClick={() => void saveKnowledgeEdit()}>Save changes</button><button onClick={() => setKnowledgeEdit(null)}>Cancel</button></div>
                            </div>
                          ) : (<>
                          <strong>{fact.title}</strong>
                          <p>{fact.statement}</p>
                          <button onClick={() => setKnowledgeEdit({ kind: "about", item: { ...fact } })}>
                            Edit About Katy item
                          </button>{" "}
                          <button className="danger" onClick={() => void deleteAboutFact(fact)}>
                            Remove About Katy item
                          </button>
                          </>)}
                        </article>
                      ))}
                    </div>
                  </div>
                )}
                {profileFacts.length > 0 && (
                  <div className="knowledge-group">
                    <h3>Other approved knowledge</h3>
                    <div>
                    {profileFacts.map((fact) => (
                      <article key={fact.id}>
                        {knowledgeEdit?.kind === "fact" && knowledgeEdit.item.id === fact.id ? (
                          <div className="knowledge-edit">
                            <label>Question<input value={knowledgeEdit.item.question} onChange={(event) => setKnowledgeEdit({ kind: "fact", item: { ...knowledgeEdit.item, question: event.target.value } })} /></label>
                            <label>Approved answer<textarea value={knowledgeEdit.item.answer} onChange={(event) => setKnowledgeEdit({ kind: "fact", item: { ...knowledgeEdit.item, answer: event.target.value } })} /></label>
                            <div><button onClick={() => void saveKnowledgeEdit()}>Save changes</button><button onClick={() => setKnowledgeEdit(null)}>Cancel</button></div>
                          </div>
                        ) : (<>
                        <strong>{fact.question}</strong>
                        <p>{fact.answer}</p>
                        <button onClick={() => setKnowledgeEdit({ kind: "fact", item: { ...fact } })}>
                          Edit knowledge
                        </button>{" "}
                        <button className="danger" onClick={() => void deleteProfileFact(fact)}>
                          Remove from shared profile
                        </button>
                        </>)}
                      </article>
                    ))}
                    </div>
                  </div>
                )}
                </div>
              </section>
            </>
          )}

          {checkingSession ? (
            <p className="admin-message">Checking your secure session…</p>
          ) : !authenticated ? (
            <form className="admin-form login" onSubmit={login} autoComplete="on">
              <input
                className="password-username"
                name="username"
                value="katy"
                autoComplete="username"
                readOnly
                tabIndex={-1}
                aria-hidden="true"
              />
              <label>
                Admin password
                <input
                  type="password"
                  name="password"
                  autoComplete="current-password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  required
                  minLength={8}
                />
              </label>
              <button>Open studio</button>
            </form>
          ) : (
            <section className="create-section-heading collapsible-admin-section" id="new-application">
              <SectionToggle
                label="Create New Application"
                section="new-application"
                collapsed={collapsedSections["new-application"]}
                onToggle={toggleSection}
              />
              <p className="eyebrow">NEW APPLICATION</p>
              <h2 className="create-heading">Create another application</h2>
              <div id="new-application-content" hidden={collapsedSections["new-application"]}>
            {questions.length === 0 ? (
            <form className="admin-form" onSubmit={analyze}>
              <div className="field-row">
                <label>
                  Company
                  <input
                    value={intake.company}
                    onChange={(event) => field("company", event.target.value)}
                    required
                  />
                </label>
                <label>
                  Job title
                  <input
                    value={intake.role}
                    onChange={(event) => field("role", event.target.value)}
                    required
                  />
                </label>
              </div>
              <label>
                Job description
                <textarea
                  value={intake.job_description}
                  onChange={(event) => field("job_description", event.target.value)}
                  required
                  minLength={100}
                  rows={12}
                />
              </label>
              <label>
                What should Ask Katy know about your interest in this company and role?
                <small>
                  Required. Include what the company does and what genuinely excites
                  you. Rough notes like “I love bringing customers and technology
                  together” are perfect. Ask Katy will turn them into a concise
                  third-person answer without adding reasons you did not give it.
                </small>
                <textarea
                  aria-label="What should Ask Katy know about your interest in this company and role?"
                  placeholder="Example: I love bringing customers and technology together, and this company…"
                  value={intake.company_interest}
                  onChange={(event) => field("company_interest", event.target.value)}
                  required
                  minLength={20}
                  rows={5}
                />
              </label>
              <label>
                Draft your public introduction
                <small>
                  Unique to this application and shown near the top of its public page.
                  Rough wording is fine: Ask Katy will correct grammar and repetition without
                  adding facts, and you will review the result before creating the draft.
                </small>
                <textarea
                  value={intake.notes}
                  onChange={(event) => field("notes", event.target.value)}
                  rows={5}
                />
              </label>
              <label className="file-picker application-resume-upload">
                Use an existing résumé (PDF)
                <input
                  aria-label="Use an existing résumé (PDF)"
                  type="file"
                  accept=".pdf,application/pdf"
                  onChange={(event) => {
                    const file = event.target.files?.[0] ?? null;
                    setUploadedResume(file);
                  }}
                />
                <small>
                  Optional · maximum 5 MB · stored privately for this application only
                </small>
                {uploadedResume && <strong>{uploadedResume.name} selected</strong>}
              </label>
              <button>Compare this job with what Ask Katy knows →</button>
            </form>
          ) : (
            <form className="admin-form" onSubmit={createDraft}>
              <h2>Review what Ask Katy found</h2>
              <label>
                Review public introduction
                <small>
                  AI proofread the wording, but you remain the final editor. Confirm that it is
                  accurate, grammatical, and sounds like you before creating the draft.
                </small>
                <textarea
                  aria-label="Review public introduction"
                  required
                  minLength={3}
                  rows={5}
                  value={intake.notes}
                  onChange={(event) => field("notes", event.target.value)}
                />
              </label>
              <p>
                Ask Katy checked your approved knowledge first. Leave a suggested answer
                as-is to confirm it, or edit it to add job-specific context.
              </p>
              <p>Skip anything you don’t know yet.</p>
              {uploadedResume && (
                <p className="selected-application-resume">
                  Using <strong>{uploadedResume.name}</strong> for this application.{" "}
                  <button type="button" onClick={() => setUploadedResume(null)}>
                    Remove PDF
                  </button>
                </p>
              )}
              {questions.map((question, index) => {
                const item = normalizeIntakeQuestion(question);
                return (
                <div className={`answer-field ${item.status}`} key={`${item.question}-${index}`}>
                  <div className="intake-match-heading">
                    <span>{INTAKE_STATUS_LABELS[item.status]}</span>
                    <p>{item.guidance}</p>
                  </div>
                  <label>
                    {item.question}
                    <textarea
                      rows={4}
                      value={answers[index]}
                      onChange={(event) =>
                        setAnswers(
                          answers.map((answer, answerIndex) =>
                            answerIndex === index ? event.target.value : answer,
                          ),
                        )
                      }
                    />
                  </label>
                  <label className="reuse-answer">
                    <input
                      type="checkbox"
                      checked={reusableAnswers[index] ?? true}
                      onChange={(event) => setReusableAnswers(
                        reusableAnswers.map((value, answerIndex) =>
                          answerIndex === index ? event.target.checked : value,
                        ),
                      )}
                    />
                    {item.suggested_answer
                      ? "Save my edits as new reusable knowledge"
                      : "Reuse this answer for future jobs"}
                  </label>
                </div>
                );
              })}
              <button>Create private draft →</button>
            </form>
          )}
              </div>
            </section>
          )}

          {message && <p className="admin-message">{message}</p>}
          {result && (
            <aside className="draft-result">
              <strong>Your editable URL is ready.</strong>
              <p>Application ID: {result.id}</p>
              <p>Employer URL: <code>{SITE}/for/{result.public_path}</code></p>
              <small>
                You can change it below. The page remains unavailable until you
                publish it.
              </small>
            </aside>
          )}

          {authenticated && (
            <section className="application-review collapsible-admin-section" id="application-control">
              <SectionToggle
                label="Application Control"
                section="application-control"
                collapsed={collapsedSections["application-control"]}
                onToggle={toggleSection}
              />
              <p className="eyebrow">APPLICATION CONTROL</p>
              <h2>URLs, previews, and publishing</h2>
              <div id="application-control-content" hidden={collapsedSections["application-control"]}>
              <p>Published URLs are active. Draft and revoked URLs stay unavailable.</p>
              {applications.length === 0 ? (
                <p>No application drafts yet.</p>
              ) : (
                <div className="application-list">
                  {applications.map((application) => (
                    <article
                      key={application.id}
                      className={editingApplication?.id === application.id ? "editing" : undefined}
                    >
                      <div className="application-details">
                        <span className={`application-status ${application.status}`}>
                          {application.status}
                        </span>
                        <h3>{application.page.role}</h3>
                        <p>{application.page.company}</p>
                        {application.company_interest_ready === false && (
                          <p className="application-readiness-warning">
                            Needs company-interest notes before publishing. Edit this
                            application to add it.
                          </p>
                        )}
                        {editingApplication?.id !== application.id && (<>
                          <label className="url-editor">
                            <span>{SITE}/for/</span>
                            <input
                              aria-label={`URL for ${application.page.role} at ${application.page.company}`}
                              value={urlDrafts[application.id] ?? ""}
                              onChange={(event) => setUrlDrafts({
                                ...urlDrafts,
                                [application.id]: event.target.value.toLowerCase(),
                              })}
                              pattern="[a-z0-9-]+/[a-z0-9-]+"
                            />
                            <button onClick={() => void saveApplicationUrl(application.id)}>
                              Save URL
                            </button>
                          </label>
                          {application.public_path && (
                            <a
                              className="active-url"
                              href={`${SITE}/for/${application.public_path}${
                                application.status === "published" ? "" : "?preview=1"
                              }`}
                              target="_blank"
                              rel="noreferrer"
                            >
                              Open saved URL ↗
                            </a>
                          )}
                        </>)}
                      </div>
                      {editingApplication?.id !== application.id && (
                        <div className="application-actions">
                          <button onClick={() => void beginApplicationEdit(application.id)}>
                            Edit application
                          </button>
                          <button onClick={() => void previewApplication(application.id)}>
                            Preview
                          </button>
                          <button onClick={() => void regenerateApplicationDocuments(application)}>
                            Regenerate documents
                          </button>
                          {application.public_path && <>
                            <a
                              href={application.uploaded_resume_filename
                                ? `${API}/v1/admin/applications/${application.id}/resume`
                                : `${SITE}/for/${application.public_path}?${
                                    application.status === "published" ? "" : "preview=1&"
                                  }document=resume`}
                              target="_blank"
                              rel="noreferrer"
                            >
                              Open résumé ↗
                            </a>
                            <a
                              href={`${SITE}/for/${application.public_path}?${
                                application.status === "published" ? "" : "preview=1&"
                              }document=cover-letter`}
                              target="_blank"
                              rel="noreferrer"
                            >
                              Open cover letter ↗
                            </a>
                          </>}
                          {application.status === "published" ? (
                            <button onClick={() => void updateApplication(application.id, "unpublish")}>
                              Unpublish
                            </button>
                          ) : application.status === "revoked" ? (
                            <button onClick={() => void updateApplication(application.id, "unrevoke")}>
                              Unrevoke
                            </button>
                          ) : (
                            <button onClick={() => void updateApplication(application.id, "publish")}>
                              Publish
                            </button>
                          )}
                          {application.status !== "revoked" && (
                            <button className="danger" onClick={() => void updateApplication(application.id, "revoke")}>
                              Revoke
                            </button>
                          )}
                          <button className="danger" onClick={() => void deleteApplication(application)}>
                            Delete permanently
                          </button>
                        </div>
                      )}
                      {editingApplication?.id === application.id && (
                        <form className="application-editor" onSubmit={saveApplicationContent}>
                          <div className="application-editor-heading">
                            <div>
                              <h4>Edit this application</h4>
                              <p>These changes stay with this job. The saved URL will not change.</p>
                            </div>
                            <button type="button" onClick={() => {
                              setEditingApplication(null);
                              setApplicationSaveError("");
                              setEditingResumeUpload(null);
                              setResumeUploadError("");
                            }}>
                              Cancel
                            </button>
                          </div>
                          <div className="field-row">
                            <label>
                              Company
                              <input
                                aria-label="Edit application company"
                                required
                                value={editingApplication.page.company}
                                onChange={(event) => setEditingApplication({
                                  ...editingApplication,
                                  page: { ...editingApplication.page, company: event.target.value },
                                })}
                              />
                            </label>
                            <label>
                              Job title
                              <input
                                aria-label="Edit application job title"
                                required
                                value={editingApplication.page.role}
                                onChange={(event) => setEditingApplication({
                                  ...editingApplication,
                                  page: { ...editingApplication.page, role: event.target.value },
                                })}
                              />
                            </label>
                          </div>
                          <label>
                            Job description
                            <textarea
                              aria-label="Edit application job description"
                              required
                              minLength={100}
                              rows={9}
                              value={editingApplication.job_description ?? ""}
                              onChange={(event) => setEditingApplication({
                                ...editingApplication,
                                job_description: event.target.value,
                              })}
                            />
                          </label>
                          <label>
                            Public introduction
                            <small>
                              Unique to this application and shown near the top of its public page.
                              Use complete, recruiter-ready sentences.
                            </small>
                            <textarea
                              aria-label="Application introduction"
                              required
                              minLength={3}
                              rows={5}
                              value={editingApplication.page.introduction}
                              onChange={(event) => setEditingApplication({
                                ...editingApplication,
                                page: { ...editingApplication.page, introduction: event.target.value },
                              })}
                            />
                          </label>
                          <label>
                            What should Ask Katy know about your interest in this company and role?
                            <small>
                              Include what the company does and what genuinely excites
                              you. Ask Katy will turn your honest notes into its public
                              third-person answer.
                            </small>
                            <textarea
                              aria-label="Edit why Katy is interested"
                              placeholder="Example: I love bringing customers and technology together, and this company…"
                              required
                              minLength={20}
                              rows={5}
                              value={editingApplication.company_interest ?? ""}
                              onChange={(event) => setEditingApplication({
                                ...editingApplication,
                                company_interest: event.target.value,
                              })}
                            />
                          </label>
                          <section className="application-resume-manager" aria-label="Premade résumé settings">
                            <div>
                              <h4>Résumé file</h4>
                              <p>
                                {editingApplication.uploaded_resume_filename
                                  ? <>Currently using <strong>{editingApplication.uploaded_resume_filename}</strong>. Recruiters will see this PDF.</>
                                  : <>Currently using the generated résumé. Upload a PDF to use a premade version for this application instead.</>}
                              </p>
                            </div>
                            <label className="file-picker application-resume-upload">
                              Choose a premade PDF
                              <input
                                aria-label="Premade résumé PDF"
                                type="file"
                                accept=".pdf,application/pdf"
                                onChange={(event) => {
                                  setEditingResumeUpload(event.target.files?.[0] ?? null);
                                  setResumeUploadError("");
                                }}
                              />
                              <small>Maximum 5 MB · private to this application</small>
                              {editingResumeUpload && <strong>{editingResumeUpload.name} selected</strong>}
                            </label>
                            <div className="application-resume-actions">
                              <button
                                type="button"
                                disabled={!editingResumeUpload || resumeUploadBusy}
                                onClick={() => void uploadPremadeResume()}
                              >
                                {resumeUploadBusy ? "Saving résumé…" : "Upload premade résumé"}
                              </button>
                              {editingApplication.uploaded_resume_filename && <>
                                <a
                                  href={`${API}/v1/admin/applications/${editingApplication.id}/resume`}
                                  target="_blank"
                                  rel="noreferrer"
                                >
                                  Open current PDF ↗
                                </a>
                                <button
                                  type="button"
                                  className="danger"
                                  disabled={resumeUploadBusy}
                                  onClick={() => void removePremadeResume()}
                                >
                                  Remove premade résumé
                                </button>
                              </>}
                            </div>
                            {resumeUploadError && <p className="application-save-error" role="alert">{resumeUploadError}</p>}
                          </section>
                          <section
                            className="application-cover-letter-editor"
                            aria-label="Cover letter quick version"
                          >
                            <div>
                              <h4>Cover letter quick version</h4>
                              <p>
                                Write one or two warm, first-person sentences about what you’re
                                passionate about and what you bring to this role. This text is fully
                                editable for this application; company, role, and URL stay synchronized.
                              </p>
                            </div>
                            <label>
                              What should the quick version say?
                              <textarea
                                aria-label="Application cover letter pitch"
                                required
                                minLength={3}
                                rows={5}
                                value={editingApplication.cover_letter_pitch ?? ""}
                                onChange={(event) => setEditingApplication({
                                  ...editingApplication,
                                  cover_letter_pitch: event.target.value,
                                })}
                              />
                            </label>
                          </section>
                          {editingApplication.resume && <section className="application-document-editor">
                            <div className="application-answer-heading">
                              <div>
                                <h4>Job-specific résumé</h4>
                                <p>
                                  AI selected and rewrote only approved information. Review every
                                  line before publishing; this version belongs only to this job.
                                </p>
                              </div>
                            </div>
                            <label>
                              Professional summary
                              <textarea
                                aria-label="Application resume summary"
                                required
                                minLength={3}
                                rows={4}
                                value={editingApplication.resume.summary}
                                onChange={(event) => setEditingApplication({
                                  ...editingApplication,
                                  resume: {
                                    ...editingApplication.resume!,
                                    summary: event.target.value,
                                  },
                                })}
                              />
                            </label>
                            <label>
                              Relevant skills
                              <small>One ATS-readable skill per line.</small>
                              <textarea
                                aria-label="Application resume skills"
                                rows={6}
                                value={editingApplication.resume.skills.join("\n")}
                                onChange={(event) => setEditingApplication({
                                  ...editingApplication,
                                  resume: {
                                    ...editingApplication.resume!,
                                    skills: event.target.value.split("\n"),
                                  },
                                })}
                              />
                            </label>
                            <div className="application-answer-heading">
                              <div><h4>Recent experience</h4><p>Keep only recent, relevant positions.</p></div>
                              <button type="button" onClick={addResumeExperience}>+ Add job</button>
                            </div>
                            {editingApplication.resume.experience.map((experience, index) => (
                              <article className="resume-edit-card" key={`${index}-${experience.company}`}>
                                <div className="field-row">
                                  <label>
                                    Company
                                    <input
                                      aria-label={`Resume company ${index + 1}`}
                                      required
                                      value={experience.company}
                                      onChange={(event) => updateResumeExperience(index, "company", event.target.value)}
                                    />
                                  </label>
                                  <label>
                                    Job title
                                    <input
                                      aria-label={`Resume job title ${index + 1}`}
                                      required
                                      value={experience.role}
                                      onChange={(event) => updateResumeExperience(index, "role", event.target.value)}
                                    />
                                  </label>
                                </div>
                                <label>
                                  Dates
                                  <input
                                    aria-label={`Resume dates ${index + 1}`}
                                    placeholder="Only include dates Katy has confirmed"
                                    value={experience.dates}
                                    onChange={(event) => updateResumeExperience(index, "dates", event.target.value)}
                                  />
                                </label>
                                <label>
                                  Accomplishments and responsibilities
                                  <small>One bullet per line. Do not add unverified metrics.</small>
                                  <textarea
                                    aria-label={`Resume bullets ${index + 1}`}
                                    rows={6}
                                    value={experience.bullets.join("\n")}
                                    onChange={(event) => updateResumeExperience(index, "bullets", event.target.value)}
                                  />
                                </label>
                                <button type="button" className="danger" onClick={() => removeResumeExperience(index)}>
                                  Remove job
                                </button>
                              </article>
                            ))}
                            <div className="application-answer-heading">
                              <div><h4>Education</h4><p>Shown only when the saved information supports it.</p></div>
                              <button type="button" onClick={addResumeEducation}>+ Add education</button>
                            </div>
                            {editingApplication.resume.education.map((education, index) => (
                              <article className="resume-edit-card" key={`${index}-${education.school}`}>
                                <label>
                                  School
                                  <input
                                    aria-label={`Resume school ${index + 1}`}
                                    required
                                    value={education.school}
                                    onChange={(event) => updateResumeEducation(index, "school", event.target.value)}
                                  />
                                </label>
                                <label>
                                  Credential
                                  <input
                                    aria-label={`Resume credential ${index + 1}`}
                                    required
                                    value={education.credential}
                                    onChange={(event) => updateResumeEducation(index, "credential", event.target.value)}
                                  />
                                </label>
                                <label>
                                  Dates
                                  <input
                                    aria-label={`Resume education dates ${index + 1}`}
                                    value={education.dates}
                                    onChange={(event) => updateResumeEducation(index, "dates", event.target.value)}
                                  />
                                </label>
                                <button type="button" className="danger" onClick={() => removeResumeEducation(index)}>
                                  Remove education
                                </button>
                              </article>
                            ))}
                          </section>}
                          <div className="application-answer-heading">
                            <div>
                              <h4>Approved Q&amp;A</h4>
                              <p>Application-specific. Edit Katy Knowledge separately to teach every bot.</p>
                            </div>
                            <button type="button" onClick={addApplicationAnswer}>+ Add answer</button>
                          </div>
                          {(editingApplication.profile_answers ?? []).map((answer, index) => (
                            <div className="application-answer-edit" key={`${index}-${answer.question}`}>
                              <label>
                                Question
                                <input
                                  aria-label={`Edit application question ${index + 1}`}
                                  required
                                  minLength={3}
                                  value={answer.question}
                                  onChange={(event) => updateApplicationAnswer(index, "question", event.target.value)}
                                />
                              </label>
                              <label>
                                Answer
                                <textarea
                                  aria-label={`Edit application answer ${index + 1}`}
                                  required
                                  minLength={3}
                                  rows={3}
                                  value={answer.answer}
                                  onChange={(event) => updateApplicationAnswer(index, "answer", event.target.value)}
                                />
                              </label>
                              <button type="button" className="danger" onClick={() => removeApplicationAnswer(index)}>
                                Remove answer
                              </button>
                            </div>
                          ))}
                          {applicationSaveError && (
                            <p className="application-save-error" role="alert">
                              {applicationSaveError}
                            </p>
                          )}
                          <button className="save-application" type="submit" disabled={applicationSaving}>
                            {applicationSaving ? "Saving changes…" : "Save application changes"}
                          </button>
                        </form>
                      )}
                      {preview?.id === application.id && (
                        <section className="admin-preview">
                          <div className="preview-heading">
                            <div>
                              <p className="eyebrow">PRIVATE PREVIEW · {preview.status}</p>
                              <h2>{preview.page.role} at {preview.page.company}</h2>
                            </div>
                            <div className="preview-actions">
                              <button onClick={() => void beginApplicationEdit(preview.id)}>
                                Edit application
                              </button>
                              <button onClick={() => setPreview(null)}>Close</button>
                            </div>
                          </div>
                          <p className="preview-intro">{preview.page.introduction}</p>
                          <h3>Approved answers</h3>
                          {preview.profile_answers?.length ? (
                            preview.profile_answers.map((item) => (
                              <article key={item.question}>
                                <strong>{item.question}</strong>
                                <p>{item.answer}</p>
                              </article>
                            ))
                          ) : (
                            <p>No approved answers have been added yet.</p>
                          )}
                        </section>
                      )}
                    </article>
                  ))}
                  </div>
                )}
              </div>
            </section>
          )}

          {authenticated && (
            <section className="rate-limit-settings collapsible-admin-section" id="settings">
              <SectionToggle
                label="AI Question Limits"
                section="settings"
                collapsed={collapsedSections.settings}
                onToggle={toggleSection}
              />
              <p className="eyebrow">COST &amp; TRAFFIC CONTROLS</p>
              <h2>How many questions can people ask?</h2>
              <div id="settings-content" hidden={collapsedSections.settings}>
                <p>
                  Only professional questions that reach OpenAI count. Off-topic questions and
                  attempts to manipulate the bot are answered locally without using your AI allowance.
                </p>
                <form className="rate-limit-form" onSubmit={saveRateLimits}>
                  <div className="rate-limit-grid">
                    <label>
                      Questions per visitor
                      <span>
                        <input
                          aria-label="Questions per visitor"
                          type="number"
                          min="1"
                          max="100"
                          required
                          value={rateLimits.visitor_limit}
                          onChange={(event) => setRateLimits({
                            ...rateLimits,
                            visitor_limit: Number(event.target.value),
                          })}
                        />
                        <small>every {rateLimits.visitor_window_seconds / 60} minutes</small>
                      </span>
                    </label>
                    <label>
                      Total questions across the site
                      <span>
                        <input
                          aria-label="Total questions across the site"
                          type="number"
                          min="1"
                          max="1000"
                          required
                          value={rateLimits.global_limit}
                          onChange={(event) => setRateLimits({
                            ...rateLimits,
                            global_limit: Number(event.target.value),
                          })}
                        />
                        <small>every {rateLimits.global_window_seconds / 60} minutes</small>
                      </span>
                    </label>
                  </div>
                  <aside className="rate-limit-note">
                    <strong>What happens at the limit?</strong>
                    The visitor sees a friendly “please try again later” message, and OpenAI is
                    not called—so the blocked question does not add to your API bill.
                  </aside>
                  {rateLimitMessage && <p className="rate-limit-message" aria-live="polite">{rateLimitMessage}</p>}
                  <button type="submit">Save question limits</button>
                </form>
              </div>
            </section>
          )}

          {authenticated && (
            <section className="question-review collapsible-admin-section" id="questions">
              <SectionToggle
                label="Question Log"
                section="questions"
                collapsed={collapsedSections.questions}
                onToggle={toggleSection}
              />
              <div className="question-review-heading">
                <div>
                  <p className="eyebrow">RECRUITER QUESTION LOG</p>
                  <h2>What people are asking</h2>
                </div>
                <div className="question-review-actions">
                  <button
                    type="button"
                    className="refresh-questions"
                    disabled={questionLogLoading}
                    onClick={() => void loadQuestionLog()}
                  >
                    {questionLogLoading ? "Refreshing…" : "Refresh questions"}
                  </button>
                  <button
                    type="button"
                    className="clear-questions"
                    disabled={questionLogLoading || questionLogTotal === 0}
                    onClick={() => void clearQuestionLog()}
                  >
                    Clear question log
                  </button>
                </div>
              </div>
              <div id="questions-content" hidden={collapsedSections.questions}>
              <p>
                If an answer is missing or wrong, choose <strong>Correct answer</strong>. You decide whether
                the correction belongs to every application or only this job.
              </p>
              {questionLogTotal > 0 && (
                <p className="question-page-count" aria-live="polite">
                  Page {questionLogPage} of {questionLogTotalPages} · {questionLogTotal} {questionLogTotal === 1 ? "question" : "questions"}
                </p>
              )}
              {questionLog.length === 0 ? (
                <p>No recruiter questions yet.</p>
              ) : (
                <div className="question-list">
                  {questionLog.map((entry, index) => (
                    <article
                      className={entry.outcome}
                      key={`${entry.timestamp}-${index}`}
                    >
                      <span>{entry.outcome.replace("_", " ")}</span>
                      <h3>{entry.question}</h3>
                      <p>{entry.answer}</p>
                      <small>
                        {entry.application_id} · {new Date(entry.timestamp).toLocaleString()}
                      </small>
                      {questionEditId === entry.id ? (
                        <div className="question-correction">
                          <label>
                            Correct answer
                            <textarea
                              aria-label={`Correct answer for ${entry.question}`}
                              rows={4}
                              value={questionAnswer}
                              onChange={(event) => setQuestionAnswer(event.target.value)}
                            />
                          </label>
                          <label className="reuse-answer">
                            <input
                              type="checkbox"
                              checked={questionReusable}
                              onChange={(event) => setQuestionReusable(event.target.checked)}
                            />
                            Use this answer for every application bot
                          </label>
                          <div>
                            <button disabled={questionAnswer.trim().length < 3} onClick={() => void saveQuestionCorrection(entry)}>Save corrected answer</button>
                            <button onClick={() => setQuestionEditId(null)}>Cancel</button>
                          </div>
                        </div>
                      ) : (
                        <button className="correct-answer" onClick={() => beginQuestionCorrection(entry)}>
                          Correct answer
                        </button>
                      )}
                    </article>
                  ))}
                </div>
              )}
              {questionLogTotalPages > 1 && (
                <nav className="question-pagination" aria-label="Recruiter question pages">
                  <button
                    type="button"
                    aria-label="Previous question page"
                    disabled={questionLogLoading || questionLogPage === 1}
                    onClick={() => void showQuestionPage(questionLogPage - 1)}
                  >
                    ← Previous
                  </button>
                  <span>{questionLogPage} / {questionLogTotalPages}</span>
                  <button
                    type="button"
                    aria-label="Next question page"
                    disabled={questionLogLoading || questionLogPage === questionLogTotalPages}
                    onClick={() => void showQuestionPage(questionLogPage + 1)}
                  >
                    Next →
                  </button>
                </nav>
              )}
              </div>
            </section>
          )}
        </div>
      </section>
    </main>
  );
}
