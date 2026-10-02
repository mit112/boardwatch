import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { Answers, QueueDetail, QueueRow, RequirementView } from "../api/types";
import { DetailPane } from "../components/DetailPane";
import { queueRow } from "../test/rows";

/*
 * The job workspace: what it says FIRST, what it never says, and which controls it offers.
 *
 * Its hierarchy is the contract. A person opens a job to decide and to prepare, so the order is
 * role and company, then what to check, then the prepared materials and application tools, and
 * only then the description and the assessment behind it. Nothing here asserts a class or a pixel:
 * order is DOM order, and the honesty rules (an unknown requirement is never "missing", opening a
 * page records nothing) are asserted as behaviour.
 */

vi.mock("../api/client", () => ({
  FIXTURE_MODE: false,
  openPdf: vi.fn(),
  revealFolder: vi.fn(),
}));

const ANSWERS: Answers = {
  identity: { full_name: "Example Person", email: "person@example.com", phone: null },
  work_auth: { status: "EAD or similar (work authorization document)", sponsorship: null },
  education: [],
  questions: [],
};

const BODY = "About the team. We build and operate the systems that move every request.";

function detailWith(
  requirements: RequirementView[],
  overrides: Partial<QueueRow> = {},
  body: string | null = BODY,
): QueueDetail {
  return {
    row: queueRow(overrides),
    jd_body: body,
    requirements,
    board_target: "greenhouse:example",
  };
}

function renderPane(
  detail: QueueDetail,
  extra: Partial<React.ComponentProps<typeof DetailPane>> = {},
) {
  return render(
    <DetailPane
      detail={detail}
      loading={false}
      error={null}
      answers={ANSWERS}
      onClose={() => undefined}
      onApplied={() => undefined}
      onSkip={() => undefined}
      onReport={() => undefined}
      onFollowUp={() => undefined}
      onToast={() => undefined}
      {...extra}
    />,
  );
}

const MET: RequirementView = {
  requirement: "A bachelor's degree",
  covered: true,
  rule: "degree_level",
  disposition: "met",
  profile_field: "education.highest_degree",
  quote: "A bachelor's degree in computer science.",
  rationale: "Profile records a completed bachelor's degree.",
};

const UNKNOWN: RequirementView = {
  requirement: "1+ years of professional experience",
  // The wire's `covered` is `disposition == "met"`, so an UNKNOWN arrives as false — the exact
  // shape that used to be listed under "Missing".
  covered: false,
  rule: "experience.min_years",
  disposition: "unknown",
  profile_field: null,
  quote: "1+ years of professional experience",
  rationale: null,
};

const UNMET: RequirementView = {
  requirement: "US citizenship",
  covered: false,
  rule: "work_authorization",
  disposition: "unmet",
  profile_field: "work_auth.status",
  quote: "Must be a US citizen",
  rationale: "Profile records a visa that needs sponsorship.",
};

const KEYWORD_PRESENT: RequirementView = {
  requirement: "python",
  covered: true,
  rule: null,
  disposition: null,
  profile_field: null,
  quote: null,
  rationale: null,
};

const KEYWORD_ABSENT: RequirementView = { ...KEYWORD_PRESENT, requirement: "kubernetes", covered: false };

function headingNames(): string[] {
  return screen.getAllByRole("heading").map((heading) => heading.textContent ?? "");
}

describe("the reading order", () => {
  it("goes role, what to check, prepared materials, description — and the assessment last", () => {
    renderPane(detailWith([MET, UNKNOWN]));
    const names = headingNames();
    const at = (prefix: string) => names.findIndex((name) => name.startsWith(prefix));
    expect(at("Software Engineer")).toBe(0);
    expect(at("What to check")).toBeGreaterThan(at("Software Engineer"));
    expect(at("Prepared materials")).toBeGreaterThan(at("What to check"));
    expect(at("Job description")).toBeGreaterThan(at("Prepared materials"));
    const why = screen.getByText("Why this status?");
    const description = screen.getByRole("heading", { name: "Job description" });
    expect(description.compareDocumentPosition(why) & 4).toBe(4);
  });

  it("puts the résumé and the answers BEFORE the description, so neither is behind a long read", () => {
    renderPane(detailWith([UNKNOWN]));
    const description = screen.getByRole("heading", { name: "Job description" });
    const copy = screen.getByRole("button", { name: "Copy résumé path for upload" });
    const answers = screen.getByRole("button", { name: /Application answers/ });
    expect(copy.compareDocumentPosition(description) & 4).toBe(4);
    expect(answers.compareDocumentPosition(description) & 4).toBe(4);
  });

  it("labels the résumé action by what it is for", () => {
    renderPane(detailWith([MET]));
    // "Copy PDF path" said what the file is; this says what you do with it.
    screen.getByRole("button", { name: "Copy résumé path for upload" });
    expect(screen.queryByRole("button", { name: /copy pdf path/i })).toBeNull();
  });
});

describe("what to check", () => {
  it("lists an unknown requirement as something to check, with its quote — never as missing", () => {
    renderPane(detailWith([UNKNOWN], { verdict: "uncertain", review_reason: "experience_requirement" }));
    const section = within(screen.getByRole("heading", { name: "What to check" }).closest("section") as HTMLElement);
    section.getByText("Check: 1+ years of professional experience");
    section.getByText("“1+ years of professional experience”");
    // The old pane printed this under a "missing" heading, because `covered` was false.
    expect(screen.queryByText(/^missing/i)).toBeNull();
    expect(screen.queryByText("Not met: 1+ years of professional experience")).toBeNull();
  });

  it("lists a confirmed-unmet requirement as 'Not met', and the two differently", () => {
    renderPane(detailWith([UNMET, UNKNOWN], { verdict: "ineligible" }));
    screen.getByText("Not met: US citizenship");
    screen.getByText("Check: 1+ years of professional experience");
  });

  it("says nothing was checked, rather than all clear, when no requirement was extracted", () => {
    renderPane(detailWith([], { verdict: "eligible", judge_verdict: "eligible" }));
    screen.getByText(/nothing was actually checked/);
  });

  it("states the clear case only as far as it goes", () => {
    renderPane(detailWith([MET], { verdict: "eligible", judge_verdict: "eligible" }));
    screen.getByText(
      "Nothing flagged: the rules found no blocker and the independent review found no blocker.",
    );
  });

  it("jumps to the quoted words in the description and marks them", () => {
    renderPane(detailWith([UNKNOWN], {}, `Intro. We need ${UNKNOWN.quote ?? ""} for this role.`));
    fireEvent.click(screen.getAllByRole("button", { name: "Show in description" })[0] as HTMLElement);
    const mark = document.querySelector("mark");
    expect(mark?.textContent).toBe("1+ years of professional experience");
  });

  it("offers no jump for a quote that is not in the description", () => {
    renderPane(detailWith([UNKNOWN], {}, "A description that does not contain the quoted words."));
    expect(screen.queryByRole("button", { name: "Show in description" })).toBeNull();
  });
});

describe("why this status", () => {
  it("keeps the four requirement states in four separate groups", () => {
    const notAssessed: RequirementView = { ...MET, requirement: "Odd", disposition: null, covered: true };
    renderPane(detailWith([MET, UNMET, UNKNOWN, notAssessed]));
    screen.getByRole("heading", { name: "Not met (1)" });
    screen.getByRole("heading", { name: "Not confirmed (1)" });
    screen.getByRole("heading", { name: "Confirmed satisfied (1)" });
    screen.getByRole("heading", { name: "Not assessed (1)" });
  });

  it("prints the rules' reading and the independent review's side by side when they differ", () => {
    renderPane(detailWith([MET], { verdict: "eligible", judge_verdict: "uncertain" }));
    const why = within(screen.getByText("Why this status?").closest("details") as HTMLElement);
    why.getByText("Rules found no blocker");
    why.getByText("Independent review is unsure");
    why.getByText(/read this job differently/);
  });

  it("does not turn a review nobody ran into a clear one", () => {
    renderPane(detailWith([MET], { verdict: "eligible", judge_verdict: null }));
    const why = within(screen.getByText("Why this status?").closest("details") as HTMLElement);
    why.getByText("No independent review yet");
    expect(why.queryByText("Independent review found no blocker")).toBeNull();
  });

  it("keeps résumé keywords apart from requirements and says what they do not show", () => {
    renderPane(detailWith([MET, KEYWORD_PRESENT, KEYWORD_ABSENT], { coverage: 0.5 }));
    const why = within(screen.getByText("Why this status?").closest("details") as HTMLElement);
    why.getByRole("heading", { name: "Résumé keywords" });
    why.getByText(/1 of 2 keywords from the posting appear in your résumé/);
    why.getByText(/it does not show you meet a requirement/);
    // A keyword missing from the résumé is not an unmet requirement of the job.
    expect(why.queryByRole("heading", { name: /Not met/ })).toBeNull();
    why.getByText("kubernetes", { exact: false });
  });

  it("labels the score as an ordering and not as a chance of anything", () => {
    renderPane(detailWith([MET], { score: 0.9, why: "target company (+0.30)" }));
    screen.getByText(/Ranking score 0.90/);
    screen.getByText(/it only orders the list/);
    screen.getByText(/target company \(\+0.30\)/);
  });
});

describe("the application actions", () => {
  it("opens the employer's page without recording anything", () => {
    const onApplied = vi.fn();
    const onApplyOpened = vi.fn();
    renderPane(detailWith([MET]), { onApplied, onApplyOpened });
    const open = screen.getByRole("link", { name: /Open application/ });
    expect(open.getAttribute("href")).toBe("https://boards.example.invalid/apply");
    expect(open.getAttribute("rel")).toContain("noopener");
    // Cancel the navigation jsdom would attempt; the point is what the click CAUSES.
    open.addEventListener("click", (event) => {
      event.preventDefault();
    });
    fireEvent.click(open);
    expect(onApplyOpened).toHaveBeenCalledTimes(1);
    expect(onApplied).not.toHaveBeenCalled();
  });

  it("records only through its own button, which is a different control from opening", () => {
    const onApplied = vi.fn();
    renderPane(detailWith([MET]), { onApplied });
    fireEvent.click(screen.getByRole("button", { name: "Record application" }));
    expect(onApplied).toHaveBeenCalledTimes(1);
  });

  it("refuses a held key on the record button", () => {
    renderPane(detailWith([MET]));
    const record = screen.getByRole("button", { name: "Record application" });
    // A held Enter repeats `click` on a focused button; the repeat must be stopped at the key.
    const repeating = fireEvent.keyDown(record, { key: "Enter", repeat: true });
    expect(repeating).toBe(false);
    const first = fireEvent.keyDown(record, { key: "Enter", repeat: false });
    expect(first).toBe(true);
  });

  it("explains a missing résumé and what to do, instead of showing empty controls", () => {
    renderPane(detailWith([MET], { pdf_uri: null, pdf_available: false }));
    screen.getByText(/No résumé file was built for this job/);
    expect(screen.queryByRole("button", { name: "Copy résumé path for upload" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Preview résumé" })).toBeNull();
    // The application itself is still one click away.
    screen.getByRole("link", { name: /Open application/ });
  });

  it("says plainly when the board supplied no application link", () => {
    renderPane(detailWith([MET], { apply_url: null }));
    screen.getByText("No application link");
    expect(screen.queryByRole("link", { name: /Open application/ })).toBeNull();
  });

  it("puts reporting a problem behind More, away from the primary actions", () => {
    renderPane(detailWith([MET]));
    const report = screen.getByRole("button", { name: "Report a problem with this job" });
    expect(report.closest("details")).not.toBeNull();
  });
});

describe("the reveal button", () => {
  it("is omitted where the platform has no file-manager handler", () => {
    renderPane(detailWith([MET]), { revealSupported: false });
    expect(screen.queryByRole("button", { name: "Reveal folder" })).toBeNull();
  });

  it("renders by default, so an older server that omits the flag loses nothing", () => {
    renderPane(detailWith([MET]));
    screen.getByRole("button", { name: "Reveal folder" });
  });
});

describe("the application answers", () => {
  it("start folded, open on a click, and are remembered for the next job", () => {
    const first = renderPane(detailWith([MET]));
    const toggle = screen.getByRole("button", { name: /Application answers/ });
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(toggle);
    expect(screen.getByRole("button", { name: /Application answers/ }).getAttribute("aria-expanded")).toBe("true");
    first.unmount();

    renderPane(detailWith([MET]));
    expect(screen.getByRole("button", { name: /Application answers/ }).getAttribute("aria-expanded")).toBe("true");
  });
});

describe("the description", () => {
  it("is shown whole, with no fold and no box to scroll, when it is short", () => {
    renderPane(detailWith([MET]));
    screen.getByText(BODY);
    expect(screen.queryByRole("button", { name: /full description/i })).toBeNull();
  });

  it("folds a long one to a readable height and says so in its control's state", () => {
    renderPane(detailWith([MET], {}, `${"A long sentence about the work. ".repeat(120)}`));
    const toggle = screen.getByRole("button", { name: "Show the full description" });
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(toggle);
    expect(screen.getByRole("button", { name: "Show less" }).getAttribute("aria-expanded")).toBe("true");
  });

  it("opens the fold itself when an evidence jump needs the words inside it", () => {
    const filler = "Padding sentence. ".repeat(200);
    renderPane(detailWith([UNKNOWN], {}, `${filler}${UNKNOWN.quote ?? ""} is required.`));
    fireEvent.click(screen.getAllByRole("button", { name: "Show in description" })[0] as HTMLElement);
    expect(screen.getByRole("button", { name: "Show less" })).toBeTruthy();
    expect(document.querySelector("mark")?.textContent).toBe(UNKNOWN.quote);
  });

  it("says the description is unavailable, and that nothing above was read from it", () => {
    renderPane(detailWith([], {}, null));
    screen.getByText(/description isn’t available/);
  });
});

describe("follow-up", () => {
  it("is folded away until used, and names its date in the summary when one is pinned", () => {
    renderPane(detailWith([MET], { follow_up: "2026-10-20" }));
    const summary = screen.getByText("Follow up later");
    expect(summary.closest("summary")?.textContent).toContain("on 2026-10-20");
    expect(summary.closest("details")?.open).toBe(true);
  });

  it("stays shut when no date is pinned", () => {
    renderPane(detailWith([MET], { follow_up: null }));
    expect(screen.getByText("Follow up later").closest("details")?.open).toBe(false);
  });
});

describe("related postings and moving through the list", () => {
  it("names each folded posting with its place and opens it, so none is lost", () => {
    const onOpenRelated = vi.fn();
    const sibling = queueRow({ location: "Boston, MA", remote_policy: "hybrid", provider: "greenhouse" });
    renderPane(detailWith([MET]), { related: [sibling], onOpenRelated });
    screen.getByRole("heading", { name: "Related postings (1)" });
    fireEvent.click(screen.getByRole("button", { name: /Boston, MA/ }));
    expect(onOpenRelated).toHaveBeenCalledWith(sibling);
  });

  it("shows its position and steps through the list in the order it is given", () => {
    const onNext = vi.fn();
    const onPrevious = vi.fn();
    renderPane(detailWith([MET]), { position: "3 of 120", onNext, onPrevious });
    screen.getByText("3 of 120");
    fireEvent.click(screen.getByRole("button", { name: "Next job" }));
    fireEvent.click(screen.getByRole("button", { name: "Previous job" }));
    expect(onNext).toHaveBeenCalledTimes(1);
    expect(onPrevious).toHaveBeenCalledTimes(1);
  });

  it("offers no stepping where the job is not in a list it can step through", () => {
    renderPane(detailWith([MET]));
    expect(screen.queryByRole("button", { name: "Next job" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Previous job" })).toBeNull();
  });
});

describe("loading and failure", () => {
  it("holds the layout while it loads, and announces it", () => {
    render(
      <DetailPane
        detail={null}
        loading
        error={null}
        answers={null}
        onClose={() => undefined}
        onApplied={() => undefined}
        onSkip={() => undefined}
        onReport={() => undefined}
        onFollowUp={() => undefined}
        onToast={() => undefined}
      />,
    );
    screen.getByRole("status", { name: "Loading the job" });
  });

  it("states a load failure as an alert, in words", () => {
    render(
      <DetailPane
        detail={null}
        loading={false}
        error="Could not load this lead."
        answers={null}
        onClose={() => undefined}
        onApplied={() => undefined}
        onSkip={() => undefined}
        onReport={() => undefined}
        onFollowUp={() => undefined}
        onToast={() => undefined}
      />,
    );
    screen.getByRole("alert");
  });
});
