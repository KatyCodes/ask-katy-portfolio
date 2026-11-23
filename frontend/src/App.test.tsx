import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { App } from "./App";


const page = {
  company: "Test Company",
  role: "Implementation Specialist",
  eyebrow: "A NOTE FOR TEST COMPANY",
  headline: "Technical depth, translated into customer results.",
  introduction: "Katy's tailored introduction.",
  suggested_questions: [
    "Why is Katy interested in Test Company?",
    "How does Ask Katy work?",
    "Can you tell me more about Katy’s experience with APIs and integrations?",
  ],
  accomplishments: [
    { title: "APIs and integrations", detail: "Built approved API integrations." },
  ],
  resume: {
    summary: "Customer-focused implementation specialist with API experience.",
    skills: ["API integrations", "SaaS implementation"],
    experience: [{
      company: "CD Baby",
      role: "Software Engineer",
      dates: "Recent",
      bullets: ["Built approved customer-facing API integrations."],
    }],
    education: [],
  },
  cover_letter_pitch: "I bring customer-focused implementation and API experience",
};


// Starts every public-page test on one realistic employer application route.
beforeEach(() => {
  window.history.replaceState({}, "", "/for/test-company/implementation-specialist");
});


// Restores browser functions after each isolated recruiter-chat test.
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  Reflect.deleteProperty(Element.prototype, "scrollIntoView");
  Reflect.deleteProperty(HTMLElement.prototype, "scrollTo");
  Reflect.deleteProperty(navigator, "clipboard");
});


// Confirms the hero describes the application as a chatbot recruiters can interact with.
test("invites recruiters to chat with the interactive cover letter", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify(page), { status: 200 }),
  );

  render(<App />);

  expect(await screen.findByText("chat with.")).toBeVisible();
  expect(screen.queryByText("talk to.")).not.toBeInTheDocument();
});


// Confirms the browser cannot show or navigate its saved-question autocomplete menu.
test("disables browser history suggestions in the recruiter chat input", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify(page), { status: 200 }),
  );

  render(<App />);
  const input = await screen.findByPlaceholderText("ask anything about Katy’s work…");
  const form = input.closest("form");

  expect(form).toHaveAttribute("autocomplete", "off");
  expect(input).toHaveAttribute("autocomplete", "off");
  expect(input).toHaveAttribute("aria-autocomplete", "none");
  expect(fireEvent.keyDown(input, { key: "ArrowUp" })).toBe(false);
  expect(fireEvent.keyDown(input, { key: "ArrowDown" })).toBe(false);
});


// Confirms the visible terminal cursor is the input caret that follows typed text.
test("uses the moving input caret instead of a detached decorative cursor", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify(page), { status: 200 }),
  );

  render(<App />);
  const input = await screen.findByPlaceholderText("ask anything about Katy’s work…");
  const form = input.closest("form");

  expect(input).toHaveClass("terminal-question-input");
  expect(form?.querySelector("i[aria-hidden='true']")).not.toBeInTheDocument();
  fireEvent.change(input, { target: { value: "Does Katy like coffee?" } });
  expect(input).toHaveValue("Does Katy like coffee?");
});


// Confirms recruiters can open the résumé while the cover letter stays private.
test("shows the job-specific resume without a recruiter-facing cover letter link", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify(page), { status: 200 }),
  );

  render(<App />);

  const viewResume = await screen.findByRole("link", { name: "01 résumé" });
  expect(viewResume).not.toHaveAttribute("target");
  expect(viewResume).not.toHaveAttribute("rel");
  expect(viewResume).toHaveAttribute(
    "href",
    "/for/test-company/implementation-specialist?document=resume",
  );
  expect(screen.queryByRole("link", { name: /cover letter/i })).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "02 contact Katy" })).toBeVisible();
  expect(screen.getByRole("link", { name: "03 portfolio ↗" })).toBeVisible();
  expect(screen.getByRole("link", { name: "04 LinkedIn ↗" })).toHaveAttribute(
    "href",
    "https://www.linkedin.com/in/katyhenning/",
  );
  expect(screen.getByRole("link", { name: "05 GitHub ↗" })).toHaveAttribute(
    "href",
    "https://github.com/KatyCodes/",
  );
});


// Confirms an application with Katy's existing PDF opens its private API document.
test("uses an uploaded application resume when one is available", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify({ ...page, resume_source: "uploaded" }), { status: 200 }),
  );

  render(<App />);

  const viewResume = await screen.findByRole("link", { name: "01 résumé" });
  expect(viewResume).toHaveAttribute("href", "http://localhost:8000/v1/resume");
  expect(viewResume).not.toHaveAttribute("target");
});


// Confirms the tailored résumé uses a semantic, ATS-safe single-document view.
test("renders the job-specific resume on its own printable route", async () => {
  window.history.replaceState(
    {},
    "",
    "/for/test-company/implementation-specialist?document=resume",
  );
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify(page), { status: 200 }),
  );

  render(<App />);

  expect(await screen.findByRole("heading", { name: "Katy Henning" })).toBeVisible();
  expect(screen.getByText("Implementation Specialist")).toBeVisible();
  expect(screen.getByRole("heading", { name: "Professional Summary" })).toBeVisible();
  expect(screen.getByText("Software Engineer")).toBeVisible();
  expect(screen.getByText("Built approved customer-facing API integrations.")).toBeVisible();
  expect(screen.getByRole("link", { name: "← Interactive cover letter" })).toHaveAttribute(
    "href",
    "http://localhost:3000/for/test-company/implementation-specialist",
  );
  expect(screen.getByRole("button", { name: "Print / save as PDF" })).toBeVisible();
  expect(screen.getByRole("link", { name: "LinkedIn" })).toHaveAttribute(
    "href",
    "https://www.linkedin.com/in/katyhenning/",
  );
  expect(screen.getByRole("link", { name: "GitHub" })).toHaveAttribute(
    "href",
    "https://github.com/KatyCodes/",
  );
  expect(screen.queryByText("What would you like to know?")).not.toBeInTheDocument();
});


// Confirms the cover letter follows Katy's requested chatbot-first structure and live URL.
test("renders the tailored cover letter with the current application URL", async () => {
  window.history.replaceState(
    {},
    "",
    "/for/test-company/implementation-specialist?document=cover-letter",
  );
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify(page), { status: 200 }),
  );

  render(<App />);

  expect(await screen.findByRole("article", {
    name: "Cover letter for Implementation Specialist at Test Company",
  })).toBeVisible();
  expect(await screen.findByText("Hello Test Company team,")).toBeVisible();
  expect(screen.getByText("Test Company Hiring Team")).toBeVisible();
  expect(screen.getByText("Re: Implementation Specialist")).toBeVisible();
  expect(screen.queryByText("INTERACTIVE VERSION")).not.toBeInTheDocument();
  expect(screen.getByText(/Rather than cram them all into a cover letter/i)).toBeVisible();
  expect(screen.getByText(
    /If chatbots aren’t your thing, no worries\. I bring customer-focused implementation and API experience\./i,
  )).toBeVisible();
  expect(screen.queryByText(/The quick version:/i)).not.toBeInTheDocument();
  expect(screen.getByText("I’d love the chance to talk with you and learn more about the role.")).toBeVisible();
  expect(screen.getByText(
    "http://localhost:3000/for/test-company/implementation-specialist",
  )).toBeVisible();
  expect(screen.getByRole("link", { name: "← Interactive cover letter" })).toBeVisible();
  expect(screen.getByRole("link", { name: "katyannhenning@gmail.com" })).toHaveAttribute(
    "href",
    "mailto:katyannhenning@gmail.com",
  );
  expect(screen.getByRole("link", { name: "LinkedIn" })).toHaveAttribute(
    "href",
    "https://www.linkedin.com/in/katyhenning/",
  );
  expect(screen.getByRole("link", { name: "GitHub" })).toHaveAttribute(
    "href",
    "https://github.com/KatyCodes/",
  );
  expect(screen.getByText(/I bring customer-focused implementation and API experience/i)).toBeVisible();
});


// Confirms contact details are visible and the recruiter can copy or draft a contextual email.
test("shows contact options and prepares an email draft", async () => {
  const writeText = vi.fn().mockResolvedValue(undefined);
  Object.defineProperty(navigator, "clipboard", {
    configurable: true,
    value: { writeText },
  });
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    if (String(input).endsWith("/v1/access/exchange")) {
      return new Response(JSON.stringify(page), { status: 200 });
    }
    return new Response(JSON.stringify({ answer: "Katy hasn’t provided that information yet." }), {
      status: 200,
    });
  });

  render(<App />);
  const input = await screen.findByPlaceholderText("ask anything about Katy’s work…");
  fireEvent.change(input, { target: { value: "Does Katy speak French?" } });
  fireEvent.click(screen.getByRole("button", { name: "Ask question" }));
  expect(await screen.findByText("Katy hasn’t provided that information yet.")).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "02 contact Katy" }));

  expect(screen.getByRole("dialog", { name: "Continue the conversation." })).toBeVisible();
  expect(screen.getByRole("link", { name: "katyannhenning@gmail.com" })).toHaveAttribute(
    "href",
    "mailto:katyannhenning@gmail.com",
  );
  const draft = screen.getByRole("link", { name: "Draft an email" });
  const decodedDraft = decodeURIComponent(draft.getAttribute("href") ?? "");
  expect(decodedDraft).toContain("mailto:katyannhenning@gmail.com?subject=");
  expect(decodedDraft).toContain("Implementation Specialist at Test Company");
  expect(decodedDraft).toContain("My question: Does Katy speak French?");

  fireEvent.click(screen.getByRole("button", { name: "Copy email" }));
  await waitFor(() => expect(writeText).toHaveBeenCalledWith("katyannhenning@gmail.com"));
  expect(screen.getByRole("button", { name: "Email copied" })).toBeVisible();
});


// Confirms the Enter button submits text the browser placed in the visible field.
test("submits the visible question even when browser input bypasses React state", async () => {
  const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (request) => {
    const url = String(request);
    if (url.endsWith("/v1/access/exchange")) {
      return new Response(JSON.stringify(page), { status: 200 });
    }
    return new Response(JSON.stringify({
      answer: "You can explore Katy's portfolio at https://katycodes.com.",
    }), { status: 200 });
  });

  render(<App />);
  const input = await screen.findByPlaceholderText("ask anything about Katy’s work…");
  const question = "Where can I find Katy's portfolio?";
  (input as HTMLInputElement).value = question;

  fireEvent.click(screen.getByRole("button", { name: "Ask question" }));

  expect(await screen.findByText(question)).toBeVisible();
  expect(await screen.findByText(/explore Katy's portfolio/i)).toBeVisible();
  expect(fetchMock).toHaveBeenCalledTimes(2);
});


// Confirms a slow follow-up visibly shows progress and eventually restores the chat.
test("shows that Ask Katy is thinking during a slow follow-up", async () => {
  let finishFollowUp: ((response: Response) => void) | undefined;
  const followUp = new Promise<Response>((resolve) => {
    finishFollowUp = resolve;
  });
  let chatCalls = 0;
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = String(input);
    if (url.endsWith("/v1/access/exchange")) {
      return new Response(JSON.stringify(page), { status: 200 });
    }
    chatCalls += 1;
    if (chatCalls === 1) {
      return new Response(JSON.stringify({ answer: "Katy has built REST APIs." }), {
        status: 200,
      });
    }
    return followUp;
  });

  render(<App />);
  const input = await screen.findByPlaceholderText("ask anything about Katy’s work…");
  fireEvent.change(input, { target: { value: "What API work has Katy done?" } });
  fireEvent.click(screen.getByRole("button", { name: "Ask question" }));
  expect(await screen.findByText("Katy has built REST APIs.")).toBeVisible();

  fireEvent.change(input, { target: { value: "How did that help customers?" } });
  fireEvent.click(screen.getByRole("button", { name: "Ask question" }));
  expect(screen.getByText("Ask Katy is thinking…")).toBeVisible();
  expect(screen.getByRole("button", { name: "Ask question" })).toBeDisabled();

  finishFollowUp?.(
    new Response(JSON.stringify({ answer: "It gave customers faster answers." }), {
      status: 200,
    }),
  );
  expect(await screen.findByText("It gave customers faster answers.")).toBeVisible();
  expect(screen.getByRole("button", { name: "Ask question" })).toBeEnabled();
});


// Confirms typing leaves the page still while an answer scrolls only inside the chat panel.
test("scrolls the chat panel to a new answer without moving while typing", async () => {
  const panelScrollTo = vi.fn();
  Object.defineProperty(HTMLElement.prototype, "scrollTo", {
    configurable: true,
    value: panelScrollTo,
  });
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = String(input);
    if (url.endsWith("/v1/access/exchange")) {
      return new Response(JSON.stringify(page), { status: 200 });
    }
    return new Response(JSON.stringify({ answer: "Katy has built grounded AI workflows." }), {
      status: 200,
    });
  });

  render(<App />);
  const input = await screen.findByPlaceholderText("ask anything about Katy’s work…");
  fireEvent.change(input, { target: { value: "What AI work has Katy done?" } });
  expect(panelScrollTo).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Ask question" }));

  expect(await screen.findByText("Katy has built grounded AI workflows.")).toBeVisible();
  expect(panelScrollTo).toHaveBeenLastCalledWith({ behavior: "smooth", top: 0 });
});


// Confirms a failed AI request explains the problem without leaving the chat locked.
test("unlocks the chat and offers a retry when an answer fails", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = String(input);
    if (url.endsWith("/v1/access/exchange")) {
      return new Response(JSON.stringify(page), { status: 200 });
    }
    throw new Error("temporary failure");
  });

  render(<App />);
  const input = await screen.findByPlaceholderText("ask anything about Katy’s work…");
  fireEvent.change(input, { target: { value: "Tell me about Katy." } });
  fireEvent.click(screen.getByRole("button", { name: "Ask question" }));

  expect(await screen.findByText(
    /experiencing some technical difficulties.*refresh.*katyannhenning@gmail.com/i,
  )).toBeVisible();
  expect(screen.getByRole("button", { name: "Ask question" })).toBeEnabled();
});


// Confirms a rate-limited visitor sees the server's useful wait message.
test("explains when the chat rate limit has been reached", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = String(input);
    if (url.endsWith("/v1/access/exchange")) {
      return new Response(JSON.stringify(page), { status: 200 });
    }
    return new Response(
      JSON.stringify({
        detail: "Ask Katy has answered several questions recently. Please wait a few minutes and try again.",
      }),
      { status: 429 },
    );
  });

  render(<App />);
  const input = await screen.findByPlaceholderText("ask anything about Katy’s work…");
  fireEvent.change(input, { target: { value: "Tell me about Katy." } });
  fireEvent.click(screen.getByRole("button", { name: "Ask question" }));

  expect(await screen.findByText(/answered several questions recently/i)).toBeVisible();
  expect(screen.getByRole("button", { name: "Ask question" })).toBeEnabled();
});


// Confirms a safe server error and its reference are shown instead of a generic retry.
test("shows the safe server message and error reference", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = String(input);
    if (url.endsWith("/v1/access/exchange")) {
      return new Response(JSON.stringify(page), { status: 200 });
    }
    return new Response(
      JSON.stringify({
        detail: "Ask Katy is experiencing some technical difficulties. Please refresh the page and try again, or contact Katy at katyannhenning@gmail.com.",
        error_id: "a1b2c3d4",
      }),
      { status: 500 },
    );
  });

  render(<App />);
  const input = await screen.findByPlaceholderText("ask anything about Katy’s work…");
  fireEvent.change(input, { target: { value: "Tell me about Katy." } });
  fireEvent.click(screen.getByRole("button", { name: "Ask question" }));

  expect(await screen.findByText(
    /technical difficulties.*katyannhenning@gmail.com.*Reference: a1b2c3d4/i,
  )).toBeVisible();
  expect(screen.getByRole("button", { name: "Ask question" })).toBeEnabled();
});


// Confirms a suggested question submits with one click instead of only filling the field.
test("submits a suggested question immediately", async () => {
  const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (request) => {
    if (String(request).endsWith("/v1/access/exchange")) {
      return new Response(JSON.stringify(page), { status: 200 });
    }
    return new Response(JSON.stringify({
      answer: "Ask Katy answers from professional information Katy has approved.",
    }), { status: 200 });
  });

  render(<App />);

  const suggestion = await screen.findByRole("button", {
    name: "How does Ask Katy work?",
  });
  expect(screen.queryByRole("button", {
    name: "Why is Katy a strong fit for Implementation Specialist?",
  })).not.toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: "How Ask Katy works" })).not.toBeInTheDocument();
  expect(screen.queryByText("Recruiters can’t train it")).not.toBeInTheDocument();
  fireEvent.click(suggestion);

  expect(await screen.findByText(
    "Ask Katy answers from professional information Katy has approved.",
  )).toBeVisible();
  expect(screen.getAllByText("How does Ask Katy work?").some(
    (element) => element.tagName === "P",
  )).toBe(true);
  expect(screen.getByPlaceholderText("ask anything about Katy’s work…")).toHaveValue("");
  expect(fetchMock).toHaveBeenCalledTimes(2);
});


// Confirms safe Markdown-style emphasis appears as bold text without raw asterisks.
test("renders bold emphasis in a chat answer", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (request) => {
    if (String(request).endsWith("/v1/access/exchange")) {
      return new Response(JSON.stringify(page), { status: 200 });
    }
    return new Response(JSON.stringify({
      answer: "**At CD Baby,** Katy built customer-facing API integrations.",
    }), { status: 200 });
  });

  render(<App />);
  const input = await screen.findByPlaceholderText("ask anything about Katy’s work…");
  fireEvent.change(input, { target: { value: "What did Katy build?" } });
  fireEvent.click(screen.getByRole("button", { name: "Ask question" }));

  const emphasis = await screen.findByText("At CD Baby,");
  expect(emphasis.tagName).toBe("STRONG");
  expect(screen.queryByText(/\*\*At CD Baby/)).not.toBeInTheDocument();
});


// Confirms the page never ends with an empty Why This Fits heading.
test("hides Why This Fits when no approved evidence cards exist", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify({ ...page, accomplishments: [] }), { status: 200 }),
  );

  render(<App />);

  expect(await screen.findByRole("heading", { name: "What would you like to know?" })).toBeVisible();
  expect(screen.queryByText("WHY THIS FITS")).not.toBeInTheDocument();
  expect(screen.queryByRole("heading", {
    name: "Katy’s experience that maps to Implementation Specialist at Test Company",
  })).not.toBeInTheDocument();
});


// Confirms an older application never displays an empty or unsupported suggestion area.
test("hides suggested questions when the application has no answer-backed ideas", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify({ ...page, suggested_questions: [] }), { status: 200 }),
  );

  render(<App />);

  expect(await screen.findByRole("heading", { name: "What would you like to know?" })).toBeVisible();
  expect(screen.queryByLabelText("Suggested questions")).not.toBeInTheDocument();
  expect(screen.queryByText("Not sure where to start? Try one:")).not.toBeInTheDocument();
});
