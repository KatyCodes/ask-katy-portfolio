# Ask Katy

> **Text-only cover letters and résumés are boring—and a little outdated. So I upgraded mine.**

Ask Katy is part cover letter, part portfolio, and part recruiter Q&A. Instead of
asking a hiring manager to dig through another static document, each application
gets a private, job-specific page where they can explore my experience and ask an
AI assistant professional questions about my fit for the role.

The result is a more useful introduction to both my work and how I think: curious,
technical, people-centered, and always looking for a better way to build something.

Each application also gets its own tailored résumé and private cover-letter draft.
Recruiters can open the role-specific résumé in the same tab, then use the browser Back
button to return to the interactive cover letter. A focused contact panel shows my email,
copies it with one click, or prepares a role-specific email draft that includes their
latest chat question when available.

## What this project demonstrates

- **Grounded AI product design:** Each assistant uses approved evidence, stays inside one employer context, and admits when information is missing instead of inventing experience.
- **OpenAI API implementation:** The backend uses the Responses API with bounded history, `store: false`, Pydantic structured outputs, and server-validated source references.
- **AI safety and evaluation:** Prompt-injection defenses, off-topic handling, unsupported-claim checks, rate limits, private error logging, and regression tests protect both accuracy and cost.
- **AI-assisted problem solving:** I collaborated iteratively with ChatGPT and Codex while owning the product decisions—defining requirements, challenging weak behavior, reproducing failures, and guiding tested improvements.
- **Grounded document generation:** AI selects and rewrites only approved professional sources for each job-specific résumé and cover-letter pitch. Every proposed phrase carries source IDs, unsupported numbers are rejected, and drafts require admin review before use.
- **Full-stack, test-driven delivery:** React, TypeScript, Python, FastAPI, SQLite, Pytest, Vitest, and React Testing Library support a private admin workflow and responsive recruiter experience.

This application keeps real application content out of Git, isolates each employer with a scoped application session, and uses the OpenAI Responses API with bounded history and `store: false`.

## Public source, private data

This repository is designed to show the complete engineering work without publishing
Katy's production data. The backend source is intentionally reviewable; security does
not depend on hiding endpoint names or Python code. Credentials and personal content
remain private through server-side authorization, signed cookies, exact CORS origins,
rate limits, private filesystem paths, and a deliberately narrow Git boundary.

Only fictional companies belong in source fixtures. Real job descriptions, application
copy, recruiter questions, uploaded résumés, SQLite files, logs, server identifiers,
and environment values stay out of the repository. Before preparing a public snapshot,
run:

```bash
python scripts/public_release_audit.py
python scripts/public_release_audit.py --history
```

The first command checks today's tracked snapshot. The second checks every reachable Git
commit and is required before publishing a repository's history. The same snapshot audit
runs in GitHub Actions with the full backend and frontend test suites. Dependabot watches
Python, npm, and GitHub Actions dependencies. Security reports and the exact public/private
boundary are documented in [SECURITY.md](SECURITY.md).

The production repository has historical context that is intentionally private. A
public portfolio repository should therefore begin from a clean, audited snapshot—not
by changing the production repository's visibility and exposing its old history.

Public AI requests are rate-limited in memory before OpenAI is called. The defaults allow 20 paid answers per visitor every 10 minutes and 120 paid answers across the site each hour. Off-topic and prompt-manipulation responses are handled locally and do not consume that allowance. Katy can edit both question ceilings in the private admin dashboard; approved values are stored in the private SQLite database and take effect immediately. Environment values provide the initial defaults until dashboard settings are saved.

## Error handling

Expected problems return a plain-language message to the browser. Unexpected server failures receive a short error reference, while their technical traceback is written to the private rotating log at `backend/private_content/logs/ask-katy.errors.log`. The log is restricted to the server account, rotates at 1 MB, keeps five backups, and never deliberately records request bodies, cookies, API keys, recruiter questions, or résumé content. In production, `ASK_KATY_ERROR_LOG_PATH` should point to a private absolute path outside the public web directory.

## Local development

Backend:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
uvicorn app.main:app --reload --port 8000
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Open a published page such as `http://localhost:5173/for/test-company/int-consultant`.

The private application studio is available at `http://localhost:5173/admin`. It requires `ASK_KATY_ADMIN_PASSWORD`, asks AI to identify missing job-specific evidence, and saves new applications as unpublished drafts in a gitignored SQLite database. Intake questions are optional. Answers marked reusable become part of Katy's private master profile and are available as approved evidence to every application assistant; job-specific answers can opt out.

Each application also requires an editable explanation of what the company does and why that genuinely interests Katy. Questions such as “Why does Katy want to work for this company?” are bounded by that approved answer. Public conversation starters come only from this answer, the built-in Ask Katy explainer, and completed accomplishment cards; intake follow-up questions never become automatic recruiter suggestions. AI may phrase a starter's answer conversationally, but the backend returns its paired approved content if AI cannot produce a faithful answer.

The same intake review proofreads each application's public introduction into concise, first-person sentences. Its prompt may correct grammar, punctuation, and repetition but forbids adding skills, achievements, tools, results, or motivations. Katy sees and can edit the proofread copy before the private draft is created, so AI never publishes the wording on its own.

Creating an application also creates private résumé and cover-letter drafts tailored to
that role. The job description is selection criteria, never evidence about Katy. Only
approved reusable knowledge and reviewed intake answers may support document claims;
company-interest copy and aspirational introduction text cannot become résumé experience.
Katy may instead attach an existing PDF résumé for one application. The PDF is validated,
stored as a private SQLite BLOB, and served only after a valid application-link exchange;
uploading it does not silently add facts to the chatbot's reusable knowledge.
The admin editor can correct every section, preview both documents in new tabs, or
deliberately regenerate them after approved knowledge changes. Regeneration warns before
replacing manual document edits.

## DreamHost deployment

The React build is served from the existing DreamHost web directory. FastAPI runs as a persistent Uvicorn service on the Managed VPS and is exposed through DreamHost's proxy at `api.katycodes.com`; see `DEPLOYMENT.md`.

Code and design updates use a guarded one-command deployment:

```bash
./deploy.sh
```

The command requires a clean Git worktree, runs every backend and frontend test, builds the production frontend, packages only deployable files, uploads through a dedicated SSH key, creates a private server backup, restarts the API, and checks both the health endpoint and admin route. A failed post-install check automatically restores the prior backend and frontend. Use `./deploy.sh --prepare-only` to test the complete local build and packaging boundary without contacting DreamHost.

The gitignored `.deploy.env` holds non-secret server identifiers and the local SSH-key path. API keys, passwords, the production `.env`, SQLite data, recruiter logs, and application content are never included in a release archive. Content changes made through the production admin page are already live and do not require deployment.

The production SQLite database is backed up nightly with SQLite's online backup
API, so the snapshot remains consistent while the site is running. The one-time
`scripts/install-production-backup.sh` setup creates an immediate verified backup,
then installs an idempotent 2:17 a.m. server-time cron entry. Backups live outside
the web root in `private/ask-katy/database-backups/`, use owner-only permissions,
and retain the newest 30 snapshots. Its short private log is
`private/ask-katy/logs/ask-katy.backup.log`.

## Privacy boundary

Real job descriptions, tailored copy, optional uploaded résumé PDFs, approved reusable knowledge, vanity paths, and recruiter-question logs are stored in `backend/private_content/ask-katy.private.db`, which is gitignored and restricted to the local account. Reusable knowledge is separated into structured skills (with optional proficiency, years, job, and details), About Katy statements, and legacy professional facts. Missing skill details remain unknown instead of being inferred. This is private application data—not model training—and can be reviewed or removed in the admin dashboard. The recruiter-question log is displayed in counted pages of 10 entries. Its guarded clear control deletes only question history; it does not remove applications or approved reusable knowledge. Public paths use the editable `/for/company/job-title` format; they are unlisted rather than secret. Pages, PDF responses, and API responses use no-index, no-referrer, and no-store protections. Legacy JSON files remain in `backend/private_content/applications/` as migration backups and are also gitignored. Never force-add private data. API keys and admin credentials belong only in `backend/.env`; copy `backend/.env.example` to see the required variable names.

Application intake compares each new job with Katy's approved reusable knowledge before asking follow-up questions. OpenAI returns a structured `confirm`, `expand`, or `new` classification plus approved source IDs; the server—not the model—constructs any suggested answer from those saved sources. Katy reviews and edits every suggestion before creating a draft, and only explicitly approved edits become new reusable knowledge.
