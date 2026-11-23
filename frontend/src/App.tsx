import { FormEvent, KeyboardEvent, useEffect, useRef, useState } from "react";

type Page = {
  company: string;
  role: string;
  eyebrow: string;
  headline: string;
  introduction: string;
  accomplishments: { title: string; detail: string }[];
  suggested_questions?: string[];
  resume: {
    summary: string;
    skills: string[];
    experience: { company: string; role: string; dates: string; bullets: string[] }[];
    education: { school: string; credential: string; dates: string }[];
  };
  resume_source?: "generated" | "uploaded";
  cover_letter_pitch: string;
};

type Message = { role: "user" | "assistant"; content: string };
const API = import.meta.env.VITE_API_URL ?? `${window.location.protocol}//${window.location.hostname}:8000`;
const CHAT_TIMEOUT_MS = 45_000;
const TECHNICAL_DIFFICULTIES_MESSAGE = "Ask Katy is experiencing some technical difficulties. Please refresh the page and try again, or contact Katy at katyannhenning@gmail.com.";
const KATY_EMAIL = "katyannhenning@gmail.com";
const LINKEDIN_URL = "https://www.linkedin.com/in/katyhenning/";
const GITHUB_URL = "https://github.com/KatyCodes/";

// Extracts the private application path from a recruiter-facing URL.
function applicationPath() {
  const parts = window.location.pathname.split("/").filter(Boolean);
  const forIndex = parts.indexOf("for");
  return forIndex < 0 ? "" : parts.slice(forIndex + 1, forIndex + 3).join("/");
}

// Identifies a job-specific document route while keeping one application path.
function documentView() {
  const document = new URLSearchParams(window.location.search).get("document");
  return document === "resume" || document === "cover-letter"
    ? document
    : "application";
}

// Builds the canonical recruiter-facing URL without preview or document suffixes.
function applicationUrl() {
  return `${window.location.origin}/for/${applicationPath()}`;
}

// Adds sentence punctuation without doubling an existing mark in the cover letter.
function sentence(value: string) {
  const trimmed = value.trim();
  return /[.!?]$/.test(trimmed) ? trimmed : `${trimmed}.`;
}

// Safely turns simple **bold** chat emphasis into React elements without HTML injection.
function chatText(value: string) {
  return value.split(/(\*\*[^*\n]+\*\*)/g).map((part, index) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={index}>{part.slice(2, -2)}</strong>;
    }
    return part;
  });
}

// Renders a plain, single-column résumé that works for ATS parsing and browser printing.
function ResumeDocument({ page }: { page: Page }) {
  return <main className="application-document resume-document">
    <div className="document-toolbar" aria-label="Document actions">
      <a href={applicationUrl()}>← Interactive cover letter</a>
      <button type="button" onClick={() => window.print()}>Print / save as PDF</button>
    </div>
    <article>
      <header className="resume-header">
        <h1>Katy Henning</h1>
        <p>{page.role}</p>
        <address>
          <a href="mailto:katyannhenning@gmail.com">katyannhenning@gmail.com</a>
          <span aria-hidden="true"> · </span>
          <a href="https://katycodes.com">katycodes.com</a>
          <span aria-hidden="true"> · </span>
          <a href={LINKEDIN_URL}>LinkedIn</a>
          <span aria-hidden="true"> · </span>
          <a href={GITHUB_URL}>GitHub</a>
        </address>
      </header>
      <section className="resume-summary">
        <h2>Professional Summary</h2>
        <p>{page.resume.summary}</p>
      </section>
      {page.resume.skills.length > 0 && <section className="resume-skills-section">
        <h2>Skills</h2>
        <p className="resume-skills">{page.resume.skills.join(" · ")}</p>
      </section>}
      {page.resume.experience.length > 0 && <section>
        <h2>Professional Experience</h2>
        {page.resume.experience.map((experience, index) => <div className="resume-entry" key={`${experience.company}-${experience.role}-${index}`}>
          <header>
            <div><h3>{experience.role}</h3><p>{experience.company}</p></div>
            {experience.dates && <p>{experience.dates}</p>}
          </header>
          <ul>{experience.bullets.map((bullet, bulletIndex) => <li key={bulletIndex}>{bullet}</li>)}</ul>
        </div>)}
      </section>}
      {page.resume.education.length > 0 && <section className="resume-education">
        <h2>Education</h2>
        {page.resume.education.map((education, index) => <div className="resume-entry education-entry" key={`${education.school}-${index}`}>
          <header>
            <div><h3>{education.credential}</h3><p>{education.school}</p></div>
            {education.dates && <p>{education.dates}</p>}
          </header>
        </div>)}
      </section>}
    </article>
  </main>;
}

// Renders Katy's standard interactive-application cover letter with live job details.
function CoverLetterDocument({ page }: { page: Page }) {
  return <main className="application-document cover-letter-document">
    <div className="document-toolbar" aria-label="Document actions">
      <a href={applicationUrl()}>← Interactive cover letter</a>
      <button type="button" onClick={() => window.print()}>Print / save as PDF</button>
    </div>
    <article aria-label={`Cover letter for ${page.role} at ${page.company}`}>
      <header className="cover-letter-header">
        <h1>Katy Henning</h1>
        <address>
          <a href="mailto:katyannhenning@gmail.com">katyannhenning@gmail.com</a>
          <span aria-hidden="true"> · </span>
          <a href="https://katycodes.com">katycodes.com</a>
          <span aria-hidden="true"> · </span>
          <a href={LINKEDIN_URL}>LinkedIn</a>
          <span aria-hidden="true"> · </span>
          <a href={GITHUB_URL}>GitHub</a>
        </address>
      </header>
      <section className="cover-letter-recipient" aria-label="Application details">
        <p><strong>{page.company} Hiring Team</strong></p>
        <p>Re: {page.role}</p>
      </section>
      <div className="cover-letter-body">
        <p className="cover-letter-greeting">Hello {page.company} team,</p>
        <p>I’m applying for the {page.role} role, and I have a lot of thoughts about why I’d be a great fit. Rather than cram them all into a cover letter, I did something a little different: I built a chatbot.</p>
        <p className="cover-letter-invitation">You can ask it about my experience, the way I work, or why I’m interested in {page.company}:</p>
        <p className="cover-letter-link">
          <a className="cover-letter-url" href={applicationUrl()}>{applicationUrl()}</a>
        </p>
        <p>If chatbots aren’t your thing, no worries. {sentence(page.cover_letter_pitch)}</p>
        <p>I’d love the chance to talk with you and learn more about the role.</p>
        <div className="cover-letter-signature">
          <p>Thanks for taking a look!</p>
          <p>Katy Henning</p>
        </div>
      </div>
    </article>
  </main>;
}

// Uses only server-approved conversation starters that have saved evidence behind them.
function suggestedQuestions(page: Page) {
  return (page.suggested_questions ?? []).slice(0, 4);
}

// Builds a useful email draft from the current application and latest recruiter question.
function contactDraftHref(page: Page, messages: Message[]) {
  const latestQuestion = messages.slice().reverse().find((message) => message.role === "user");
  const subject = `Question about Katy Henning — ${page.role} at ${page.company}`;
  const body = [
    "Hi Katy,",
    "",
    `I was reviewing your interactive application for the ${page.role} role at ${page.company} and wanted to follow up.`,
    ...(latestQuestion ? ["", `My question: ${latestQuestion.content}`] : []),
    "",
    "Best,",
  ].join("\n");
  return `mailto:${KATY_EMAIL}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
}

export function App() {
  const [page, setPage] = useState<Page | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [chatError, setChatError] = useState("");
  const [contactOpen, setContactOpen] = useState(false);
  const [copyStatus, setCopyStatus] = useState<"" | "copied" | "failed">("");
  const [status, setStatus] = useState<"loading" | "ready" | "sending" | "missing" | "error">("loading");
  const conversationPanel = useRef<HTMLDivElement | null>(null);
  const contactButton = useRef<HTMLButtonElement | null>(null);
  const contactCloseButton = useRef<HTMLButtonElement | null>(null);
  const shouldFollowConversation = useRef(false);

  useEffect(() => {
    fetch(`${API}/v1/access/exchange`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        access_path: applicationPath(),
        preview: new URLSearchParams(window.location.search).get("preview") === "1",
      }),
    }).then(async (response) => {
      if (response.status === 404) { setStatus("missing"); return; }
      if (!response.ok) throw new Error("exchange failed");
      setPage(await response.json());
      setStatus("ready");
    }).catch(() => setStatus("error"));
  }, []);

  // Focuses the contact panel, closes it with Escape, and prevents background scrolling.
  useEffect(() => {
    if (!contactOpen) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    contactCloseButton.current?.focus();
    const closeOnEscape = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") closeContact();
    };
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [contactOpen]);

  // Follows a submitted question through its loading state to the final answer or error.
  useEffect(() => {
    if (!shouldFollowConversation.current || !conversationPanel.current) return;
    conversationPanel.current.scrollTo?.({
      behavior: "smooth",
      top: conversationPanel.current.scrollHeight,
    });
    const finishedAnswer = messages[messages.length - 1]?.role === "assistant";
    if (status === "ready" && (finishedAnswer || chatError)) {
      shouldFollowConversation.current = false;
    }
  }, [messages, status, chatError]);

  // Sends one chat request and stops waiting if the service does not respond.
  async function requestAnswer(message: string, history: Message[]) {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), CHAT_TIMEOUT_MS);
    try {
      return await fetch(`${API}/v1/chat`, {
        method: "POST", credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message, history }),
        signal: controller.signal,
      });
    } finally {
      window.clearTimeout(timeout);
    }
  }

  // Adds the recruiter's question, displays progress, and records the AI answer.
  async function ask(question: string) {
    const trimmed = question.trim();
    if (!trimmed || status === "sending") return;
    shouldFollowConversation.current = true;
    const next = [...messages, { role: "user" as const, content: trimmed }];
    setMessages(next); setInput(""); setChatError(""); setStatus("sending");
    try {
      const response = await requestAnswer(trimmed, messages.slice(-6));
      if (!response.ok) {
        const data = await response.json().catch(() => null);
        const detail = typeof data?.detail === "string"
          ? data.detail
          : TECHNICAL_DIFFICULTIES_MESSAGE;
        const reference = typeof data?.error_id === "string"
          ? ` Reference: ${data.error_id}.`
          : "";
        setChatError(
          `${detail}${reference}`,
        );
        setStatus("ready");
        return;
      }
      const data = await response.json();
      setMessages([...next, { role: "assistant", content: data.answer }]);
      setStatus("ready");
    } catch {
      setChatError(TECHNICAL_DIFFICULTIES_MESSAGE);
      setStatus("ready");
    }
  }

  // Reads the visible field so browser-filled text is submitted even if React missed it.
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const visibleQuestion = new FormData(event.currentTarget).get("question");
    void ask(typeof visibleQuestion === "string" ? visibleQuestion : "");
  }

  // Stops browser form history from treating arrow keys like saved-question navigation.
  function preventSavedQuestionNavigation(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "ArrowUp" || event.key === "ArrowDown") {
      event.preventDefault();
    }
  }

  // Opens Katy's contact choices without navigating away from the application.
  function openContact() {
    setCopyStatus("");
    setContactOpen(true);
  }

  // Closes the contact panel and returns keyboard focus to its opening button.
  function closeContact() {
    setContactOpen(false);
    window.setTimeout(() => contactButton.current?.focus(), 0);
  }

  // Copies Katy's email address and gives the recruiter visible success or failure feedback.
  async function copyEmail() {
    try {
      await navigator.clipboard.writeText(KATY_EMAIL);
      setCopyStatus("copied");
    } catch {
      setCopyStatus("failed");
    }
  }

  if (status === "loading") return <main className="center"><p>Opening Katy’s note…</p></main>;
  if (status === "missing") return <main className="center"><h1>This note is unavailable.</h1><p>The link may be incomplete or no longer active.</p></main>;
  if (!page) return <main className="center"><h1>Chat is taking a breather.</h1><p>You can still visit <a href="https://katycodes.com">KatyCodes.com</a>.</p></main>;
  const view = documentView();
  if (view === "resume") return <ResumeDocument page={page} />;
  if (view === "cover-letter") return <CoverLetterDocument page={page} />;
  const questionIdeas = suggestedQuestions(page);
  const emailDraft = contactDraftHref(page, messages);
  const resumeHref = page.resume_source === "uploaded"
    ? `${API}/v1/resume`
    : `/for/${applicationPath()}?document=resume`;

  return <>
    <a className="skip-link" href="#ai-chat">Skip to AI chat</a>
    <main className="site-shell">
      <div className="ambient ambient-one" aria-hidden="true"></div>
      <div className="ambient ambient-two" aria-hidden="true"></div>
      <section className="terminal" aria-label="Katy's interactive cover letter">
        <header className="terminal-bar">
          <div className="traffic-lights" aria-hidden="true"><span></span><span></span><span></span></div>
          <p>katy@codes — ~/for/{page.company.toLowerCase().replaceAll(" ", "-")}</p>
          <span className="status">online</span>
        </header>
        <div className="terminal-body">
          <section className="intro">
          <p className="eyebrow">{page.eyebrow}</p>
          <h1>A cover letter<br/>you can <span>chat with.</span></h1>
          <p className="dek">{page.introduction}</p>
          <nav className="page-links" aria-label="Application links">
            <a href={resumeHref}>01 résumé</a>
            <button type="button" ref={contactButton} onClick={openContact}>02 contact Katy</button>
            <a href="https://katycodes.com" target="_blank" rel="noopener noreferrer">03 portfolio ↗</a>
            <a href={LINKEDIN_URL} target="_blank" rel="noopener noreferrer">04 LinkedIn ↗</a>
            <a href={GITHUB_URL} target="_blank" rel="noopener noreferrer">05 GitHub ↗</a>
          </nav>
          </section>

          <section className="ai-console" id="ai-chat" aria-labelledby="chat-title">
            <header className="console-bar"><div aria-hidden="true"><span></span><span></span><span></span></div><b>ask-katy — ai</b><em>professional context only</em></header>
            <div className="conversation" aria-live="polite" ref={conversationPanel}>
              {messages.length === 0 && <div className="assistant welcome"><p className="prompt"><span>ask-katy</span>:~$ ready</p><h2 id="chat-title">What would you like to know?</h2><p>Ask about Katy’s experience, approach, or fit for this role. I’ll answer using only information Katy has approved.</p></div>}
              {messages.map((m, i) => <div className={m.role} key={i}><p className="prompt"><span>{m.role === "user" ? "recruiter" : "ask-katy"}</span>:~$</p><p>{chatText(m.content)}</p></div>)}
              {status === "sending" && <div className="assistant pending"><p className="prompt"><span>ask-katy</span>:~$</p><p>Ask Katy is thinking…</p></div>}
              {chatError && <div className="assistant chat-error"><p className="prompt"><span>ask-katy</span>:~$</p><p>{chatError}</p></div>}
            </div>
            {questionIdeas.length > 0 && <div className="question-starters" aria-label="Suggested questions">
              <p>Not sure where to start? Try one:</p>
              <div>
                {questionIdeas.map((question) => (
                  <button
                    type="button"
                    key={question}
                    disabled={status === "sending"}
                    onClick={() => void ask(question)}
                  >
                    {question}
                  </button>
                ))}
              </div>
            </div>}
            <form className="command-line" onSubmit={submit} autoComplete="off">
              <label htmlFor="question"><span>recruiter@{page.company.toLowerCase().replaceAll(" ", "-")}</span>:~$</label>
              <input
                autoFocus
                className="terminal-question-input"
                id="question"
                name="question"
                aria-autocomplete="none"
                autoComplete="off"
                maxLength={600}
                value={input}
                onChange={(event) => setInput(event.target.value)}
                onKeyDown={preventSavedQuestionNavigation}
                placeholder="ask anything about Katy’s work…"
              />
              <button type="submit" aria-label="Ask question" disabled={status === "sending"}>
                {status === "sending" ? "…" : "↵"}
              </button>
            </form>
            <small>AI-generated responses may make mistakes. Questions and responses are privately logged for Katy to review and improve accuracy; this browser conversation clears when you leave.</small>
          </section>

          {page.accomplishments.length > 0 && <section className="evidence" aria-labelledby="evidence-title">
            <p className="eyebrow">WHY THIS FITS</p><h2 id="evidence-title">Katy’s experience that maps to {page.role} at {page.company}</h2>
            <div className="cards">{page.accomplishments.map((item, index) => <article key={item.title}><span>0{index + 1}</span><h3>{item.title}</h3><p>{item.detail}</p></article>)}</div>
          </section>}
        </div>
      </section>
      <footer><span>© {new Date().getFullYear()} Katy</span><span>built with curiosity + caffeine</span></footer>
    </main>
    {contactOpen && (
      <div
        className="contact-overlay"
        onMouseDown={(event) => {
          if (event.target === event.currentTarget) closeContact();
        }}
      >
        <section
          className="contact-card"
          role="dialog"
          aria-modal="true"
          aria-labelledby="contact-title"
        >
          <button
            type="button"
            className="contact-close"
            aria-label="Close contact options"
            ref={contactCloseButton}
            onClick={closeContact}
          >
            ×
          </button>
          <p className="eyebrow">CONTACT KATY</p>
          <h2 id="contact-title">Continue the conversation.</h2>
          <p>Have a question Ask Katy couldn’t answer? Reach Katy directly:</p>
          <a className="contact-email" href={`mailto:${KATY_EMAIL}`}>{KATY_EMAIL}</a>
          <div className="contact-actions">
            <a href={emailDraft}>Draft an email</a>
            <button
              type="button"
              aria-label={copyStatus === "copied" ? "Email copied" : "Copy email"}
              onClick={() => void copyEmail()}
            >
              {copyStatus === "copied" ? "Copied!" : "Copy email"}
            </button>
          </div>
          {copyStatus === "failed" && (
            <p className="copy-error" role="status">Copy didn’t work. Select the email address above instead.</p>
          )}
          <small>The draft opens in your email app and includes this role—and your latest question, if you asked one.</small>
        </section>
      </div>
    )}
  </>;
}
