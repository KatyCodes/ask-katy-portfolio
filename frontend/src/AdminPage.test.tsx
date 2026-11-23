import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { AdminPage, normalizeIntakeQuestion } from "./AdminPage";


// Restores the real fetch function after each isolated admin-page test.
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});


// Confirms an in-progress pre-update question remains editable during hot reload.
test("normalizes an older plain intake question without losing it", () => {
  expect(normalizeIntakeQuestion("What SaaS experience do you have?")).toEqual({
    question: "What SaaS experience do you have?",
    status: "new",
    suggested_answer: "",
    guidance: "Ask Katy has not compared this question with saved knowledge yet.",
    source_ids: [],
  });
});


// Confirms password managers can identify Katy's fixed username and current password.
test("marks the admin login for browser password managers", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify({ detail: "Admin sign-in required" }), {
      status: 401,
      headers: { "Content-Type": "application/json" },
    }),
  );

  render(<AdminPage />);

  const password = await screen.findByLabelText("Admin password");
  const username = screen.getByDisplayValue("katy");
  expect(password).toHaveAttribute("name", "password");
  expect(password).toHaveAttribute("autocomplete", "current-password");
  expect(username).toHaveAttribute("name", "username");
  expect(username).toHaveAttribute("autocomplete", "username");
});


// Confirms logout ends the backend session and returns the studio to its login screen.
test("logs out of the private admin studio", async () => {
  let logoutRequest: RequestInit | undefined;
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    if (url.endsWith("/v1/admin/logout")) {
      logoutRequest = init;
      return new Response(JSON.stringify({ authenticated: false }), { status: 200 });
    }
    if (url.endsWith("/v1/admin/session")) {
      return new Response(JSON.stringify({ authenticated: true }), { status: 200 });
    }
    if (url.endsWith("/v1/admin/questions")) {
      return new Response(JSON.stringify({ questions: [] }), { status: 200 });
    }
    if (url.endsWith("/v1/admin/profile")) {
      return new Response(JSON.stringify({ facts: [], skills: [], about: [] }), { status: 200 });
    }
    if (url.endsWith("/v1/admin/settings/rate-limits")) {
      return new Response(JSON.stringify({
        visitor_limit: 20,
        visitor_window_seconds: 600,
        global_limit: 120,
        global_window_seconds: 3600,
      }), { status: 200 });
    }
    return new Response(JSON.stringify({ applications: [] }), { status: 200 });
  });

  render(<AdminPage />);
  fireEvent.click(await screen.findByRole("button", { name: "Log out" }));

  expect(await screen.findByLabelText("Admin password")).toBeVisible();
  expect(screen.getByText("You’re signed out.")).toBeVisible();
  expect(logoutRequest).toMatchObject({ method: "POST", credentials: "include" });
  expect(screen.queryByRole("heading", { name: "Your application dashboard." }))
    .not.toBeInTheDocument();
});


// Confirms Katy can edit both public AI question ceilings without touching code.
test("edits and saves the public question limits", async () => {
  let savedLimits: Record<string, number> | null = null;
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    if (url.endsWith("/v1/admin/session")) {
      return new Response(JSON.stringify({ authenticated: true }), { status: 200 });
    }
    if (url.endsWith("/v1/admin/questions")) {
      return new Response(JSON.stringify({ questions: [] }), { status: 200 });
    }
    if (url.endsWith("/v1/admin/profile")) {
      return new Response(JSON.stringify({ facts: [], skills: [], about: [] }), { status: 200 });
    }
    if (url.endsWith("/v1/admin/settings/rate-limits") && init?.method === "PUT") {
      savedLimits = JSON.parse(String(init.body));
      return new Response(JSON.stringify({
        ...savedLimits,
        visitor_window_seconds: 600,
        global_window_seconds: 3600,
      }), { status: 200 });
    }
    if (url.endsWith("/v1/admin/settings/rate-limits")) {
      return new Response(JSON.stringify({
        visitor_limit: 20,
        visitor_window_seconds: 600,
        global_limit: 120,
        global_window_seconds: 3600,
      }), { status: 200 });
    }
    return new Response(JSON.stringify({ applications: [] }), { status: 200 });
  });

  render(<AdminPage />);
  fireEvent.click(await screen.findByRole("button", { name: "Expand AI Question Limits" }));
  fireEvent.change(screen.getByLabelText("Questions per visitor"), {
    target: { value: "8" },
  });
  fireEvent.change(screen.getByLabelText("Total questions across the site"), {
    target: { value: "75" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save question limits" }));

  await waitFor(() => expect(savedLimits).toEqual({
    visitor_limit: 8,
    global_limit: 75,
  }));
  expect(screen.getByText("Question limits saved.")).toBeVisible();
});


// Confirms a saved draft path stays editable and opens as an admin-only preview.
test("shows an editable and clickable saved application URL", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = String(input);
    if (url.endsWith("/v1/admin/session")) {
      return new Response(JSON.stringify({ authenticated: true }), { status: 200 });
    }
    if (url.endsWith("/v1/admin/questions")) {
      return new Response(JSON.stringify({ questions: [] }), { status: 200 });
    }
    if (url.endsWith("/v1/admin/profile")) {
      return new Response(JSON.stringify({ facts: [] }), { status: 200 });
    }
    return new Response(JSON.stringify({
      applications: [{
        id: "test-company-one",
        status: "draft",
        public_path: "test-company/int-consultant",
        company_interest_ready: false,
        uploaded_resume_filename: "Katy-Henning-Resume.pdf",
        page: { company: "Test Company", role: "Integration Consultant" },
      }],
    }), { status: 200 });
  });

  render(<AdminPage />);

  const urlInput = await screen.findByLabelText(
    "URL for Integration Consultant at Test Company",
  );
  expect(urlInput).toHaveValue("test-company/int-consultant");
  const link = screen.getByRole("link", { name: "Open saved URL ↗" });
  expect(link).toHaveAttribute(
    "href",
    "http://localhost:3000/for/test-company/int-consultant?preview=1",
  );
  expect(screen.getByRole("link", { name: "Open résumé ↗" })).toHaveAttribute(
    "href",
    "http://localhost:8000/v1/admin/applications/test-company-one/resume",
  );
  expect(screen.getByRole("button", { name: "Delete permanently" })).toBeVisible();
  expect(screen.getByRole("link", { name: "Application control" })).toHaveAttribute(
    "href",
    "#application-control",
  );
  expect(screen.queryByText("Your application pages")).not.toBeInTheDocument();
  expect(screen.getByText(
    "Needs company-interest notes before publishing. Edit this application to add it.",
  )).toBeVisible();
});


// Confirms a revoked application can return to a safe unpublished draft.
test("offers an unrevoke control for revoked applications", async () => {
  let requestedAction = "";
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    if (url.endsWith("/v1/admin/session")) {
      return new Response(JSON.stringify({ authenticated: true }), { status: 200 });
    }
    if (url.endsWith("/v1/admin/questions")) {
      return new Response(JSON.stringify({ questions: [] }), { status: 200 });
    }
    if (url.endsWith("/v1/admin/profile")) {
      return new Response(JSON.stringify({ facts: [], skills: [], about: [] }), { status: 200 });
    }
    if (url.endsWith("/v1/admin/applications/revoked-one/unrevoke") && init?.method === "POST") {
      requestedAction = url;
      return new Response(JSON.stringify({ id: "revoked-one", status: "draft" }), { status: 200 });
    }
    return new Response(JSON.stringify({
      applications: [{
        id: "revoked-one",
        status: "revoked",
        public_path: "example-company/example-role",
        page: { company: "Example Company", role: "Example Role" },
      }],
    }), { status: 200 });
  });

  render(<AdminPage />);
  fireEvent.click(await screen.findByRole("button", { name: "Unrevoke" }));

  await waitFor(() => expect(requestedAction).toContain("/unrevoke"));
  expect(await screen.findByText("Restored as a draft. Publish it when the link should be active again.")).toBeVisible();
});


// Confirms only one preview opens and it stays inside the application being reviewed.
test("shows each application preview directly inside its application card", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = String(input);
    if (url.endsWith("/v1/admin/session")) {
      return new Response(JSON.stringify({ authenticated: true }), { status: 200 });
    }
    if (url.endsWith("/v1/admin/questions")) {
      return new Response(JSON.stringify({ questions: [] }), { status: 200 });
    }
    if (url.endsWith("/v1/admin/profile")) {
      return new Response(JSON.stringify({ facts: [], skills: [], about: [] }), { status: 200 });
    }
    if (url.endsWith("/v1/admin/applications/first")) {
      return new Response(JSON.stringify({
        id: "first",
        status: "draft",
        public_path: "first-company/first-role",
        page: {
          company: "First Company",
          role: "First Role",
          introduction: "First preview copy",
          accomplishments: [],
        },
        profile_answers: [],
      }), { status: 200 });
    }
    if (url.endsWith("/v1/admin/applications/second")) {
      return new Response(JSON.stringify({
        id: "second",
        status: "draft",
        public_path: "second-company/second-role",
        page: {
          company: "Second Company",
          role: "Second Role",
          introduction: "Second preview copy",
          accomplishments: [],
        },
        profile_answers: [],
      }), { status: 200 });
    }
    return new Response(JSON.stringify({
      applications: [
        {
          id: "first",
          status: "draft",
          public_path: "first-company/first-role",
          page: { company: "First Company", role: "First Role" },
        },
        {
          id: "second",
          status: "draft",
          public_path: "second-company/second-role",
          page: { company: "Second Company", role: "Second Role" },
        },
      ],
    }), { status: 200 });
  });

  render(<AdminPage />);
  const firstCard = (await screen.findByRole("heading", { name: "First Role" })).closest("article");
  const secondCard = screen.getByRole("heading", { name: "Second Role" }).closest("article");
  expect(firstCard).not.toBeNull();
  expect(secondCard).not.toBeNull();

  fireEvent.click(within(firstCard!).getByRole("button", { name: "Preview" }));
  expect(await within(firstCard!).findByText("First preview copy")).toBeVisible();

  fireEvent.click(within(secondCard!).getByRole("button", { name: "Preview" }));
  expect(await within(secondCard!).findByText("Second preview copy")).toBeVisible();
  expect(within(firstCard!).queryByText("First preview copy")).not.toBeInTheDocument();
  expect(screen.getAllByText(/PRIVATE PREVIEW/)).toHaveLength(1);
});


// Confirms a preview mistake can be corrected from Application Control.
test("edits saved application content without changing its URL", async () => {
  let savedBody = "";
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    if (url.endsWith("/v1/admin/session")) {
      return new Response(JSON.stringify({ authenticated: true }), { status: 200 });
    }
    if (url.endsWith("/v1/admin/questions")) {
      return new Response(JSON.stringify({ questions: [] }), { status: 200 });
    }
    if (url.endsWith("/v1/admin/profile")) {
      return new Response(JSON.stringify({ facts: [], skills: [], about: [] }), { status: 200 });
    }
    if (url.endsWith("/v1/admin/applications/test-company-one") && init?.method === "PUT") {
      savedBody = String(init.body);
      return new Response(JSON.stringify({ id: "test-company-one" }), { status: 200 });
    }
    if (url.endsWith("/v1/admin/applications/test-company-one")) {
      return new Response(JSON.stringify({
        id: "test-company-one",
        status: "draft",
        public_path: "test-company/int-consultant",
        job_description: "Detailed requirements ".repeat(10),
        company_interest: "Test Company's DAM platform solves complex content problems.",
        page: {
          company: "Test Company",
          role: "Integration Consultant",
          eyebrow: "A NOTE FOR TEST COMPANY",
          headline: "Technical depth",
          introduction: "Old introduction",
          accomplishments: [],
        },
        resume: {
          summary: "Old resume summary",
          skills: ["API integrations"],
          experience: [{
            company: "CD Baby",
            role: "Software Engineer",
            dates: "",
            bullets: ["Built API integrations."],
          }],
          education: [],
        },
        cover_letter_pitch: "I bring technical implementation experience",
        profile_answers: [{ question: "Why this role?", answer: "Old answer" }],
      }), { status: 200 });
    }
    return new Response(JSON.stringify({
      applications: [{
        id: "test-company-one",
        status: "draft",
        public_path: "test-company/int-consultant",
        page: { company: "Test Company", role: "Integration Consultant" },
      }],
    }), { status: 200 });
  });

  render(<AdminPage />);
  fireEvent.click(await screen.findByRole("button", { name: "Edit application" }));
  expect(screen.getByText(
    /Unique to this application and shown near the top of its public page/i,
  )).toBeInTheDocument();
  const coverLetterEditor = await screen.findByRole("region", { name: "Cover letter quick version" });
  expect(coverLetterEditor).toHaveTextContent(/one or two warm, first-person sentences/i);
  expect(within(coverLetterEditor).getByLabelText("Application cover letter pitch")).toBeVisible();
  fireEvent.change(await screen.findByLabelText("Application introduction"), {
    target: { value: "Corrected introduction" },
  });
  fireEvent.change(screen.getByLabelText("Edit why Katy is interested"), {
    target: { value: "Test Company combines complex technology with customer impact." },
  });
  fireEvent.change(screen.getByLabelText("Application resume summary"), {
    target: { value: "Corrected resume summary" },
  });
  fireEvent.change(within(coverLetterEditor).getByLabelText("Application cover letter pitch"), {
    target: { value: "I bring corrected implementation experience" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save application changes" }));

  await waitFor(() => expect(savedBody).not.toBe(""));
  expect(JSON.parse(savedBody)).toMatchObject({
    company: "Test Company",
    role: "Integration Consultant",
    introduction: "Corrected introduction",
    company_interest: "Test Company combines complex technology with customer impact.",
    answers: [{ question: "Why this role?", answer: "Old answer" }],
    resume: { summary: "Corrected resume summary" },
    cover_letter_pitch: "I bring corrected implementation experience",
  });
  expect(screen.getByLabelText("URL for Integration Consultant at Test Company")).toHaveValue(
    "test-company/int-consultant",
  );
});


// Confirms a saved application can switch between a premade PDF and its generated résumé.
test("uploads and removes a premade resume from an existing application", async () => {
  let uploadedBody = "";
  let removed = false;
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    if (url.endsWith("/v1/admin/session")) {
      return new Response(JSON.stringify({ authenticated: true }), { status: 200 });
    }
    if (url.endsWith("/v1/admin/questions")) {
      return new Response(JSON.stringify({ questions: [] }), { status: 200 });
    }
    if (url.endsWith("/v1/admin/profile")) {
      return new Response(JSON.stringify({ facts: [], skills: [], about: [] }), { status: 200 });
    }
    if (url.endsWith("/v1/admin/applications/test-company-one/resume") && init?.method === "PUT") {
      uploadedBody = String(init.body);
      return new Response(JSON.stringify({
        id: "test-company-one",
        status: "published",
        public_path: "test-company/int-consultant",
        uploaded_resume_filename: "Katy-Henning-Premade.pdf",
        page: {
          company: "Test Company",
          role: "Integration Consultant",
          introduction: "Approved introduction",
          accomplishments: [],
        },
        resume: { summary: "Generated fallback", skills: [], experience: [], education: [] },
        profile_answers: [],
      }), { status: 200 });
    }
    if (url.endsWith("/v1/admin/applications/test-company-one/resume") && init?.method === "DELETE") {
      removed = true;
      return new Response(JSON.stringify({
        id: "test-company-one",
        status: "published",
        public_path: "test-company/int-consultant",
        uploaded_resume_filename: "",
        page: {
          company: "Test Company",
          role: "Integration Consultant",
          introduction: "Approved introduction",
          accomplishments: [],
        },
        resume: { summary: "Generated fallback", skills: [], experience: [], education: [] },
        profile_answers: [],
      }), { status: 200 });
    }
    if (url.endsWith("/v1/admin/applications/test-company-one")) {
      return new Response(JSON.stringify({
        id: "test-company-one",
        status: "published",
        public_path: "test-company/int-consultant",
        job_description: "Detailed requirements ".repeat(10),
        company_interest: "Test Company combines technical work with customer impact.",
        uploaded_resume_filename: "",
        page: {
          company: "Test Company",
          role: "Integration Consultant",
          eyebrow: "A NOTE FOR TEST COMPANY",
          headline: "Technical depth",
          introduction: "Approved introduction",
          accomplishments: [],
        },
        resume: { summary: "Generated fallback", skills: [], experience: [], education: [] },
        cover_letter_pitch: "I bring technical implementation experience",
        profile_answers: [],
      }), { status: 200 });
    }
    return new Response(JSON.stringify({
      applications: [{
        id: "test-company-one",
        status: "published",
        public_path: "test-company/int-consultant",
        uploaded_resume_filename: "",
        page: { company: "Test Company", role: "Integration Consultant" },
      }],
    }), { status: 200 });
  });

  render(<AdminPage />);
  fireEvent.click(await screen.findByRole("button", { name: "Edit application" }));
  const premadeResume = new File(
    ["%PDF-1.7\n% premade resume"],
    "Katy-Henning-Premade.pdf",
    { type: "application/pdf" },
  );
  fireEvent.change(await screen.findByLabelText("Premade résumé PDF"), {
    target: { files: [premadeResume] },
  });
  fireEvent.click(screen.getByRole("button", { name: "Upload premade résumé" }));

  await waitFor(() => expect(uploadedBody).not.toBe(""));
  expect(JSON.parse(uploadedBody).filename).toBe("Katy-Henning-Premade.pdf");
  expect(JSON.parse(uploadedBody).file_base64).toMatch(/^JVBERi/);
  expect(await screen.findByRole("region", { name: "Premade résumé settings" })).toHaveTextContent(
    "Currently using Katy-Henning-Premade.pdf",
  );

  fireEvent.click(screen.getByRole("button", { name: "Remove premade résumé" }));
  await waitFor(() => expect(removed).toBe(true));
  expect(screen.getByRole("region", { name: "Premade résumé settings" })).toHaveTextContent(
    "Currently using the generated résumé",
  );
});


// Confirms a deliberate AI regeneration replaces only the selected job documents.
test("regenerates and opens job-specific documents for review", async () => {
  vi.spyOn(window, "confirm").mockReturnValue(true);
  const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = String(input);
    if (url.endsWith("/v1/admin/session")) {
      return new Response(JSON.stringify({ authenticated: true }), { status: 200 });
    }
    if (url.endsWith("/v1/admin/questions")) {
      return new Response(JSON.stringify({ questions: [] }), { status: 200 });
    }
    if (url.endsWith("/v1/admin/profile")) {
      return new Response(JSON.stringify({ facts: [], skills: [], about: [] }), { status: 200 });
    }
    if (url.endsWith("/documents/regenerate")) {
      return new Response(JSON.stringify({
        id: "test-company-one",
        status: "draft",
        public_path: "test-company/int-consultant",
        job_description: "Detailed requirements ".repeat(10),
        company_interest: "Test Company makes customer work easier.",
        page: {
          company: "Test Company",
          role: "Integration Consultant",
          eyebrow: "A NOTE FOR TEST COMPANY",
          headline: "Technical depth",
          introduction: "Tailored introduction",
          accomplishments: [],
        },
        resume: {
          summary: "New grounded resume summary",
          skills: ["API integrations"],
          experience: [],
          education: [],
        },
        cover_letter_pitch: "I bring grounded integration experience",
        profile_answers: [],
      }), { status: 200 });
    }
    return new Response(JSON.stringify({
      applications: [{
        id: "test-company-one",
        status: "draft",
        public_path: "test-company/int-consultant",
        page: { company: "Test Company", role: "Integration Consultant" },
      }],
    }), { status: 200 });
  });

  render(<AdminPage />);
  fireEvent.click(await screen.findByRole("button", { name: "Regenerate documents" }));

  expect(await screen.findByLabelText("Application resume summary")).toHaveValue(
    "New grounded resume summary",
  );
  expect(screen.getByLabelText("Application cover letter pitch")).toHaveValue(
    "I bring grounded integration experience",
  );
  expect(fetchMock).toHaveBeenCalledWith(
    expect.stringContaining("/documents/regenerate"),
    expect.objectContaining({ method: "POST" }),
  );
});


// Confirms a stale or unavailable backend explains the failed save beside the button.
test("shows an application save error inside the editor", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    if (url.endsWith("/v1/admin/session")) {
      return new Response(JSON.stringify({ authenticated: true }), { status: 200 });
    }
    if (url.endsWith("/v1/admin/questions")) {
      return new Response(JSON.stringify({ questions: [] }), { status: 200 });
    }
    if (url.endsWith("/v1/admin/profile")) {
      return new Response(JSON.stringify({ facts: [], skills: [], about: [] }), { status: 200 });
    }
    if (url.endsWith("/v1/admin/applications/test-company-one") && init?.method === "PUT") {
      return new Response(JSON.stringify({ detail: "The local backend needs to be restarted." }), {
        status: 405,
      });
    }
    if (url.endsWith("/v1/admin/applications/test-company-one")) {
      return new Response(JSON.stringify({
        id: "test-company-one",
        status: "draft",
        public_path: "test-company/int-consultant",
        job_description: "Detailed requirements ".repeat(10),
        company_interest: "Test Company's DAM platform solves complex content problems.",
        page: {
          company: "Test Company",
          role: "Integration Consultant",
          eyebrow: "A NOTE FOR TEST COMPANY",
          headline: "Technical depth",
          introduction: "Old introduction",
          accomplishments: [],
        },
        profile_answers: [],
      }), { status: 200 });
    }
    return new Response(JSON.stringify({
      applications: [{
        id: "test-company-one",
        status: "draft",
        public_path: "test-company/int-consultant",
        page: { company: "Test Company", role: "Integration Consultant" },
      }],
    }), { status: 200 });
  });

  render(<AdminPage />);
  fireEvent.click(await screen.findByRole("button", { name: "Edit application" }));
  fireEvent.click(await screen.findByRole("button", { name: "Save application changes" }));

  expect(await screen.findByRole("alert")).toHaveTextContent(
    "The local backend needs to be restarted.",
  );
  expect(screen.getByRole("button", { name: "Save application changes" })).toBeVisible();
});


// Confirms a network outage produces a visible admin notification instead of silence.
test("shows a dismissible admin connection error when the backend cannot be reached", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    if (url.endsWith("/v1/admin/session")) {
      return new Response(JSON.stringify({ authenticated: true }), { status: 200 });
    }
    if (url.endsWith("/v1/admin/questions")) {
      return new Response(JSON.stringify({ questions: [] }), { status: 200 });
    }
    if (url.endsWith("/v1/admin/profile")) {
      return new Response(JSON.stringify({ facts: [], skills: [], about: [] }), { status: 200 });
    }
    if (url.endsWith("/v1/admin/applications/example-one/publish") && init?.method === "POST") {
      throw new Error("backend offline");
    }
    return new Response(JSON.stringify({
      applications: [{
        id: "example-one",
        status: "draft",
        public_path: "example-company/example-role",
        page: { company: "Example Company", role: "Example Role" },
      }],
    }), { status: 200 });
  });

  render(<AdminPage />);
  fireEvent.click(await screen.findByRole("button", { name: "Publish" }));

  const alert = await screen.findByRole("alert");
  expect(alert).toHaveTextContent("could not reach the backend");
  fireEvent.click(within(alert).getByRole("button", { name: "Dismiss" }));
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});


// Confirms a server failure shows its safe reference without exposing technical details.
test("shows an admin server error reference", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    if (url.endsWith("/v1/admin/session")) {
      return new Response(JSON.stringify({ authenticated: true }), { status: 200 });
    }
    if (url.endsWith("/v1/admin/questions")) {
      return new Response(JSON.stringify({ questions: [] }), { status: 200 });
    }
    if (url.endsWith("/v1/admin/profile")) {
      return new Response(JSON.stringify({ facts: [], skills: [], about: [] }), { status: 200 });
    }
    if (url.endsWith("/v1/admin/applications/example-one/publish") && init?.method === "POST") {
      return new Response(JSON.stringify({
        detail: "Ask Katy hit a temporary problem. Please try again.",
        error_id: "e4f5a6b7",
      }), { status: 500 });
    }
    return new Response(JSON.stringify({
      applications: [{
        id: "example-one",
        status: "draft",
        public_path: "example-company/example-role",
        page: { company: "Example Company", role: "Example Role" },
      }],
    }), { status: 200 });
  });

  render(<AdminPage />);
  fireEvent.click(await screen.findByRole("button", { name: "Publish" }));

  const alert = await screen.findByRole("alert");
  expect(alert).toHaveTextContent("Reference: e4f5a6b7");
  expect(alert).not.toHaveTextContent("stack trace");
});


// Confirms intake prefills approved knowledge, explains gaps, and keeps answers optional.
test("reviews existing answers before asking Katy for repeated information", async () => {
  let createdBody = "";
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    if (url.endsWith("/v1/admin/session")) {
      return new Response(JSON.stringify({ authenticated: true }), { status: 200 });
    }
    if (url.endsWith("/v1/admin/questions")) {
      return new Response(JSON.stringify({ questions: [] }), { status: 200 });
    }
    if (url.endsWith("/v1/admin/profile")) {
      return new Response(JSON.stringify({ facts: [] }), { status: 200 });
    }
    if (url.endsWith("/v1/admin/applications") && init?.method === "POST") {
      createdBody = String(init.body);
      return new Response(JSON.stringify({ id: "one", public_path: "one/role" }), { status: 200 });
    }
    if (url.endsWith("/v1/admin/intake/questions")) {
      return new Response(JSON.stringify({
        introduction: "I want to connect customer goals with thoughtful technical solutions.",
        questions: [{
          question: "How have you used AI in your work?",
          status: "expand",
          suggested_answer: "Katy built Ask Katy using the OpenAI API.",
          guidance: "This is close, but it does not include experience with Claude.",
          source_ids: ["fact:1"],
        }, {
          question: "What measurable result came from the project?",
          status: "new",
          suggested_answer: "",
          guidance: "No approved knowledge answers this yet.",
          source_ids: [],
        }],
      }), { status: 200 });
    }
    return new Response(JSON.stringify({ applications: [] }), { status: 200 });
  });
  render(<AdminPage />);
  fireEvent.click(await screen.findByRole("link", { name: "Create new" }));
  expect(screen.getByLabelText("Company").closest("section")).toHaveAttribute(
    "id",
    "new-application",
  );
  fireEvent.change(await screen.findByLabelText("Company"), {
    target: { value: "Test Company" },
  });
  fireEvent.change(screen.getByLabelText("Job title"), {
    target: { value: "Consultant" },
  });
  fireEvent.change(screen.getByLabelText("Job description"), {
    target: { value: "Detailed requirements ".repeat(10) },
  });
  const companyInterest = screen.getByLabelText(
    "What should Ask Katy know about your interest in this company and role?",
  );
  fireEvent.change(companyInterest, {
    target: {
      value: "Test Company solves complex content problems, which combines customer impact with technical problem-solving.",
    },
  });
  expect(companyInterest).toBeRequired();
  expect(screen.getByText(/Rough notes like/)).toBeVisible();
  expect(companyInterest).toHaveAttribute(
    "placeholder",
    "Example: I love bringing customers and technology together, and this company…",
  );
  const existingResume = new File(
    ["%PDF-1.7\n% existing resume"],
    "Katy-Henning-Resume.pdf",
    { type: "application/pdf" },
  );
  fireEvent.change(screen.getByLabelText("Use an existing résumé (PDF)"), {
    target: { files: [existingResume] },
  });
  expect(screen.getByText("Katy-Henning-Resume.pdf selected")).toBeVisible();
  fireEvent.click(screen.getByRole("button", {
    name: "Compare this job with what Ask Katy knows →",
  }));

  const knownAnswer = await screen.findByLabelText("How have you used AI in your work?");
  const newAnswer = screen.getByLabelText("What measurable result came from the project?");
  expect(screen.getByLabelText("Review public introduction")).toHaveValue(
    "I want to connect customer goals with thoughtful technical solutions.",
  );
  expect(knownAnswer).toHaveValue("Katy built Ask Katy using the OpenAI API.");
  expect(knownAnswer).not.toBeRequired();
  expect(newAnswer).not.toBeRequired();
  expect(screen.getByText("Close match")).toBeVisible();
  expect(screen.getByText(/does not include experience with Claude/)).toBeVisible();
  expect(within(knownAnswer.closest(".answer-field")!).getByRole("checkbox")).not.toBeChecked();
  expect(within(newAnswer.closest(".answer-field")!).getByRole("checkbox")).toBeChecked();
  expect(screen.getByText("Skip anything you don’t know yet.")).toBeVisible();
  fireEvent.change(screen.getByLabelText("Review public introduction"), {
    target: { value: "I want to connect customer goals with carefully designed solutions." },
  });
  fireEvent.click(screen.getByRole("button", { name: "Create private draft →" }));
  await waitFor(() => expect(createdBody).not.toBe(""));
  expect(JSON.parse(createdBody).notes).toBe(
    "I want to connect customer goals with carefully designed solutions.",
  );
  expect(JSON.parse(createdBody).uploaded_resume.filename).toBe(
    "Katy-Henning-Resume.pdf",
  );
  expect(JSON.parse(createdBody).uploaded_resume.file_base64).toMatch(/^JVBERi/);
});


// Confirms Teach Ask Katy requires review and approval before reusable facts appear.
test("previews editable career facts before teaching Ask Katy", async () => {
  let approvedBody = "";
  let profileLoads = 0;
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    if (url.endsWith("/v1/admin/session")) {
      return new Response(JSON.stringify({ authenticated: true }), { status: 200 });
    }
    if (url.endsWith("/v1/admin/questions")) {
      return new Response(JSON.stringify({ questions: [] }), { status: 200 });
    }
    if (url.endsWith("/v1/admin/profile/import/preview")) {
      return new Response(JSON.stringify({ facts: [{
        question: "What SaaS experience does Katy have?",
        answer: "Katy implemented SaaS workflows.",
        evidence_quote: "implemented enterprise SaaS workflows for customers",
      }] }), { status: 200 });
    }
    if (url.endsWith("/v1/admin/profile/import/approve")) {
      approvedBody = String(init?.body);
      return new Response(JSON.stringify({ saved: 1 }), { status: 200 });
    }
    if (url.endsWith("/v1/admin/profile")) {
      profileLoads += 1;
      return new Response(JSON.stringify({ facts: profileLoads > 1 ? [{
        id: 1,
        question: "What SaaS experience does Katy have?",
        answer: "Katy led enterprise SaaS implementations.",
      }] : [] }), { status: 200 });
    }
    return new Response(JSON.stringify({ applications: [] }), { status: 200 });
  });

  render(<AdminPage />);
  fireEvent.click(await screen.findByRole("link", { name: "Teach Ask Katy" }));
  const source = await screen.findByLabelText("Paste professional information");
  fireEvent.change(source, {
    target: { value: "Katy implemented enterprise SaaS workflows for customers." },
  });
  fireEvent.click(screen.getByRole("button", { name: "Let AI organize this →" }));

  const answer = await screen.findByLabelText("Draft answer 1");
  fireEvent.change(answer, {
    target: { value: "Katy led enterprise SaaS implementations." },
  });
  expect(screen.getByText("Nothing is saved until you approve it.")).toBeVisible();
  expect(screen.getByText(/Based on: “implemented enterprise SaaS/)).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Approve 1 item" }));

  await waitFor(() => {
    expect(document.querySelector(".profile-knowledge")?.textContent).toContain(
      "Katy led enterprise SaaS implementations.",
    );
  });
  expect(JSON.parse(approvedBody).facts[0].answer).toBe(
    "Katy led enterprise SaaS implementations.",
  );
});


// Confirms skills and About Katy items can be saved without forcing optional metadata.
test("saves a structured skill and a separate About Katy quality", async () => {
  let approvedBody = "";
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    if (url.endsWith("/v1/admin/session")) {
      return new Response(JSON.stringify({ authenticated: true }), { status: 200 });
    }
    if (url.endsWith("/v1/admin/questions")) {
      return new Response(JSON.stringify({ questions: [] }), { status: 200 });
    }
    if (url.endsWith("/v1/admin/profile/import/approve")) {
      approvedBody = String(init?.body);
      return new Response(JSON.stringify({ saved: 2 }), { status: 200 });
    }
    if (url.endsWith("/v1/admin/profile")) {
      return new Response(JSON.stringify({ facts: [], skills: [], about: [] }), { status: 200 });
    }
    return new Response(JSON.stringify({ applications: [] }), { status: 200 });
  });

  render(<AdminPage />);
  fireEvent.click(await screen.findByRole("link", { name: "Teach Ask Katy" }));
  fireEvent.click(await screen.findByRole("button", { name: "+ Add a skill" }));
  fireEvent.change(screen.getByLabelText("Skill name 1"), { target: { value: "JavaScript" } });
  fireEvent.change(screen.getByLabelText("Skill proficiency 1"), { target: { value: "proficient" } });
  fireEvent.change(screen.getByLabelText("Skill years 1"), { target: { value: "5.5" } });
  fireEvent.change(screen.getByLabelText("Skill job 1"), { target: { value: "CD Baby — Software Engineer" } });
  fireEvent.click(screen.getByRole("button", { name: "+ Add About Katy" }));
  fireEvent.change(screen.getByLabelText("About title 1"), { target: { value: "People skills" } });
  fireEvent.change(screen.getByLabelText("About statement 1"), {
    target: { value: "Katy makes technical ideas understandable and treats people with empathy." },
  });
  fireEvent.click(screen.getByRole("button", { name: "Approve 2 items" }));

  await waitFor(() => expect(approvedBody).not.toBe(""));
  const approved = JSON.parse(approvedBody);
  expect(approved.skills[0]).toMatchObject({
    name: "JavaScript",
    proficiency: "proficient",
    years: 5.5,
    used_at: "CD Baby — Software Engineer",
  });
  expect(approved.about[0].title).toBe("People skills");
  expect(approved.about[0]).not.toHaveProperty("years");
});


// Confirms each dashboard area can minimize without erasing in-progress form text.
test("minimizes admin sections and opens the selected navigation section", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = String(input);
    if (url.endsWith("/v1/admin/session")) {
      return new Response(JSON.stringify({ authenticated: true }), { status: 200 });
    }
    if (url.endsWith("/v1/admin/questions")) {
      return new Response(JSON.stringify({ questions: [] }), { status: 200 });
    }
    if (url.endsWith("/v1/admin/profile")) {
      return new Response(JSON.stringify({ facts: [], skills: [], about: [] }), { status: 200 });
    }
    return new Response(JSON.stringify({ applications: [] }), { status: 200 });
  });

  render(<AdminPage />);

  expect(await screen.findByRole("button", { name: "Minimize Application Control" })).toBeVisible();
  expect(screen.getByRole("button", { name: "Expand Teach Ask Katy" })).toBeVisible();
  expect(screen.queryByText("Your application pages")).not.toBeInTheDocument();

  fireEvent.click(screen.getByRole("link", { name: "Teach Ask Katy" }));
  expect(screen.getByRole("button", { name: "Expand Application Control" })).toBeVisible();
  expect(screen.getByRole("button", { name: "Minimize Teach Ask Katy" })).toBeVisible();

  const source = screen.getByLabelText("Paste professional information");
  fireEvent.change(source, { target: { value: "Unsaved career notes" } });
  fireEvent.click(screen.getByRole("button", { name: "Minimize Teach Ask Katy" }));
  expect(source).not.toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Expand Teach Ask Katy" }));
  expect(screen.getByLabelText("Paste professional information")).toHaveValue(
    "Unsaved career notes",
  );
});


// Confirms questions asked in another tab appear when Katy opens or refreshes the log.
test("refreshes the recruiter question log while the admin page stays open", async () => {
  let questionLoads = 0;
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = String(input);
    if (url.endsWith("/v1/admin/session")) {
      return new Response(JSON.stringify({ authenticated: true }), { status: 200 });
    }
    if (url.endsWith("/v1/admin/questions")) {
      questionLoads += 1;
      const questions = questionLoads === 1 ? [] : [{
        id: 8,
        timestamp: "2026-11-20T13:00:00Z",
        application_id: "test-company-one",
        question: "What did Katy build with AI?",
        answer: "Katy built Ask Katy.",
        outcome: "answered",
      }, ...(questionLoads >= 3 ? [{
        id: 9,
        timestamp: "2026-11-20T13:01:00Z",
        application_id: "test-company-one",
        question: "Does Katy work with APIs?",
        answer: "Yes.",
        outcome: "answered",
      }] : []), ...(questionLoads >= 4 ? [{
        id: 10,
        timestamp: "2026-11-20T13:02:00Z",
        application_id: "test-company-one",
        question: "How does Katy work with customers?",
        answer: "With empathy and clear communication.",
        outcome: "answered",
      }] : [])];
      return new Response(JSON.stringify({ questions }), { status: 200 });
    }
    if (url.endsWith("/v1/admin/profile")) {
      return new Response(JSON.stringify({ facts: [], skills: [], about: [] }), { status: 200 });
    }
    return new Response(JSON.stringify({ applications: [] }), { status: 200 });
  });

  render(<AdminPage />);
  await waitFor(() => expect(questionLoads).toBe(1));
  fireEvent.click(screen.getByRole("link", { name: "Question log" }));

  expect(await screen.findByText("What did Katy build with AI?")).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Refresh questions" }));
  expect(await screen.findByText("Does Katy work with APIs?")).toBeVisible();
  fireEvent.focus(window);
  expect(await screen.findByText("How does Katy work with customers?")).toBeVisible();
});


// Confirms long recruiter history is paginated and clearing it requires confirmation.
test("paginates and clears the recruiter question log", async () => {
  let cleared = false;
  const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    if (url.endsWith("/v1/admin/session")) {
      return new Response(JSON.stringify({ authenticated: true }), { status: 200 });
    }
    if (url.includes("/v1/admin/questions") && init?.method === "DELETE") {
      cleared = true;
      return new Response(JSON.stringify({ deleted: 11 }), { status: 200 });
    }
    if (url.includes("/v1/admin/questions")) {
      if (cleared) {
        return new Response(JSON.stringify({
          questions: [], page: 1, page_size: 10, total: 0, total_pages: 1,
        }), { status: 200 });
      }
      const secondPage = url.includes("page=2");
      return new Response(JSON.stringify({
        questions: [{
          id: secondPage ? 1 : 11,
          timestamp: secondPage ? "2026-11-20T12:00:00Z" : "2026-11-20T13:00:00Z",
          application_id: "test-company-one",
          question: secondPage ? "Oldest question" : "Newest question",
          answer: "Answer.",
          outcome: "answered",
        }],
        page: secondPage ? 2 : 1,
        page_size: 10,
        total: 11,
        total_pages: 2,
      }), { status: 200 });
    }
    if (url.endsWith("/v1/admin/profile")) {
      return new Response(JSON.stringify({ facts: [], skills: [], about: [] }), { status: 200 });
    }
    return new Response(JSON.stringify({ applications: [] }), { status: 200 });
  });

  render(<AdminPage />);
  fireEvent.click(await screen.findByRole("link", { name: "Question log" }));
  expect(await screen.findByText("Newest question")).toBeVisible();
  expect(screen.getByText("Page 1 of 2 · 11 questions")).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Next question page" }));
  expect(await screen.findByText("Oldest question")).toBeVisible();
  expect(screen.getByText("Page 2 of 2 · 11 questions")).toBeVisible();

  fireEvent.click(screen.getByRole("button", { name: "Clear question log" }));
  expect(confirm).toHaveBeenCalled();
  expect(await screen.findByText("No recruiter questions yet.")).toBeVisible();
});


// Confirms Katy can correct both reusable knowledge and a recruiter-log answer.
test("edits saved knowledge and teaches a corrected recruiter answer", async () => {
  const updates: { url: string; body: string }[] = [];
  const scrollTo = vi.spyOn(window, "scrollTo").mockImplementation(() => undefined);
  vi.spyOn(window, "scrollX", "get").mockReturnValue(14);
  vi.spyOn(window, "scrollY", "get").mockReturnValue(860);
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    if (init?.method === "PUT") {
      updates.push({ url, body: String(init.body) });
      return new Response(JSON.stringify({ outcome: "answered" }), { status: 200 });
    }
    if (url.endsWith("/v1/admin/session")) {
      return new Response(JSON.stringify({ authenticated: true }), { status: 200 });
    }
    if (url.endsWith("/v1/admin/questions")) {
      return new Response(JSON.stringify({ questions: [{
        id: 7,
        timestamp: "2026-11-20T12:00:00Z",
        application_id: "test-company-one",
        question: "Has Katy used webhooks?",
        answer: "I’m not sure.",
        outcome: "unanswered",
      }] }), { status: 200 });
    }
    if (url.endsWith("/v1/admin/profile")) {
      return new Response(JSON.stringify({
        skills: [],
        about: [],
        facts: [{ id: 3, question: "Does Katy know APIs?", answer: "Old answer" }],
      }), { status: 200 });
    }
    return new Response(JSON.stringify({ applications: [] }), { status: 200 });
  });

  render(<AdminPage />);
  fireEvent.click(await screen.findByRole("link", { name: "Katy knowledge" }));
  fireEvent.click(await screen.findByRole("button", { name: "Edit knowledge" }));
  fireEvent.change(screen.getByLabelText("Approved answer"), {
    target: { value: "Katy builds API integrations." },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save changes" }));

  await waitFor(() => expect(updates.some((update) => update.url.endsWith("/v1/admin/profile/3"))).toBe(true));
  await waitFor(() => expect(scrollTo).toHaveBeenCalledWith(14, 860));
  fireEvent.click(screen.getByRole("link", { name: "Question log" }));
  fireEvent.click(await screen.findByRole("button", { name: "Correct answer" }));
  fireEvent.change(screen.getByLabelText("Correct answer for Has Katy used webhooks?"), {
    target: { value: "Katy has implemented webhook integrations." },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save corrected answer" }));

  await waitFor(() => expect(updates.some((update) => update.url.endsWith("/v1/admin/questions/7"))).toBe(true));
  const correction = updates.find((update) => update.url.endsWith("/v1/admin/questions/7"));
  expect(JSON.parse(correction?.body ?? "{}")).toEqual({
    answer: "Katy has implemented webhook integrations.",
    reusable: true,
  });
});
