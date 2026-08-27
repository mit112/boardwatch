/*
 * Queue fixtures. The backend does not exist yet, so the whole UI is demonstrable against these.
 *
 * Shape of the fixture set, chosen to match the measured live store (design §6):
 *   - roughly 540 delivered-and-unapplied entries, because that is what the first sync produces
 *     and every decision about search, sort and the status band follows from that number;
 *   - `applied_ever` starts at 0, because `applications` has never held a row — so an empty
 *     "applied" figure is the honest starting state, not a fixture oversight;
 *   - twelve AUTHORED edge cases up front, each one a rendering that has to be got right: a null
 *     posted date, a closed posting, an unverifiable posting, a thin JD, an off-target veto with
 *     its matched text, a missing PDF, a `javascript:` apply URL, a posting with no current
 *     version, and a posting whose JD yields no recognised requirements.
 * The remainder is generated from a fixed seed so counts and ordering are stable across reloads.
 *
 * Artifact URIs are written `file://~/…` and must stay that way. `~` is not merely a shorter home
 * prefix: an absolute home path is exactly the shape the generalization gate reads as leaked
 * personal data, so an invented account name is indistinguishable from a real one to that gate and
 * to a reader. Keeping the placeholder outside that shape means a fixture that ever does reach a
 * build again fails for being a leak, not for looking like a real person. `pathFromFileUri` strips
 * the scheme, so the pane still shows `~/boardwatch-applications/<date>/…` and the
 * parent-directory line still resolves.
 */
import type { QueueDetail, QueueRow, RequirementView, Verdict } from "../api/types";

const AUTHORED: QueueRow[] = [
  {
    posting_id: 41207,
    job_id: 30881,
    title: "Software Engineer, EDA Tools",
    company: "Intel",
    location: "Santa Clara, CA",
    remote_policy: "hybrid",
    posted_days: 3,
    first_seen: "2026-08-23T14:02:11Z",
    status: "open",
    verdict: "eligible",
    apply_url: "https://jobs.intel.com/en/job/-/41207",
    delivered_run_id: 114,
    tex_uri: "file://~/boardwatch-applications/2026-08-23/tailored-41207.tex",
    pdf_uri: "file://~/boardwatch-applications/2026-08-23/tailored-41207.pdf",
    target_flag: true,
    thin_jd: false,
    off_target: false,
    pdf_available: true,
    score: 87.4,
    coverage: 0.72,
    off_target_reason: null,
  },
  {
    posting_id: 39820,
    job_id: 29744,
    title: "Backend Engineer (New Grad)",
    company: "Ramp",
    location: "New York, NY",
    remote_policy: "onsite",
    // The board publishes no date. This row exists so the `—` rendering is always on screen.
    posted_days: null,
    first_seen: "2026-08-21T09:41:00Z",
    status: "open",
    verdict: "eligible",
    apply_url: "https://jobs.ashbyhq.com/ramp/39820",
    delivered_run_id: 114,
    tex_uri: "file://~/boardwatch-applications/2026-08-21/tailored-39820.tex",
    pdf_uri: "file://~/boardwatch-applications/2026-08-21/tailored-39820.pdf",
    target_flag: true,
    thin_jd: false,
    off_target: false,
    pdf_available: true,
    score: 84.1,
    coverage: 0.64,
    off_target_reason: null,
  },
  {
    posting_id: 38115,
    job_id: 28402,
    title: "Software Engineer II, Platform",
    company: "Datadog",
    location: "Boston, MA",
    remote_policy: "remote",
    posted_days: 22,
    first_seen: "2026-08-04T12:00:00Z",
    // 35 postings with a tailored PDF are already closed on the live store.
    status: "closed",
    verdict: "eligible",
    apply_url: "https://careers.datadoghq.com/detail/38115/",
    delivered_run_id: 108,
    tex_uri: "file://~/boardwatch-applications/2026-08-04/tailored-38115.tex",
    pdf_uri: "file://~/boardwatch-applications/2026-08-04/tailored-38115.pdf",
    target_flag: false,
    thin_jd: false,
    off_target: false,
    pdf_available: true,
    score: 79.8,
    coverage: 0.58,
    off_target_reason: null,
  },
  {
    posting_id: 40551,
    job_id: 30122,
    title: "Data Analyst, Growth",
    company: "Instacart",
    location: "San Francisco, CA",
    remote_policy: null,
    posted_days: 6,
    first_seen: "2026-08-20T18:20:00Z",
    // A lane-acquired lead: nothing enumerates the board it came from, so no scan can ever mark
    // it missing. 722 open postings on the live store are in this state (D-324).
    status: "unverifiable",
    verdict: "uncertain",
    apply_url: "https://boards.greenhouse.io/instacart/jobs/40551",
    delivered_run_id: 113,
    tex_uri: "file://~/boardwatch-applications/2026-08-20/tailored-40551.tex",
    pdf_uri: "file://~/boardwatch-applications/2026-08-20/tailored-40551.pdf",
    target_flag: null,
    thin_jd: false,
    // The reason carries the text the shipped role gate matched. The UI displays it verbatim.
    off_target: true,
    pdf_available: true,
    score: 61.2,
    coverage: 0.41,
    off_target_reason: 'role gate: title family "analyst" is denied (matched "Data Analyst")',
  },
  {
    posting_id: 40990,
    job_id: 30510,
    title: "Software Engineer",
    company: "Cerebras Systems",
    location: "Sunnyvale, CA",
    remote_policy: "onsite",
    posted_days: 1,
    first_seen: "2026-08-25T22:15:00Z",
    status: "open",
    verdict: "uncertain",
    apply_url: "https://cerebras.net/careers/40990",
    delivered_run_id: 114,
    tex_uri: "file://~/boardwatch-applications/2026-08-25/tailored-40990.tex",
    pdf_uri: null,
    target_flag: true,
    // Coverage could not be computed, so the JD is thin. `coverage` is null exactly here.
    thin_jd: true,
    off_target: false,
    pdf_available: false,
    score: 70.0,
    coverage: null,
    off_target_reason: null,
  },
  {
    posting_id: 40012,
    job_id: 29901,
    title: "Member of Technical Staff, Inference",
    company: "Anthropic",
    location: "Seattle, WA",
    remote_policy: "hybrid",
    posted_days: 9,
    first_seen: "2026-08-17T11:05:00Z",
    status: "open",
    verdict: "uncertain",
    // Not http(s). Must render as inert text, never as a link.
    apply_url: "javascript:alert('apply')",
    delivered_run_id: 112,
    tex_uri: "file://~/boardwatch-applications/2026-08-17/tailored-40012.tex",
    pdf_uri: "file://~/boardwatch-applications/2026-08-17/tailored-40012.pdf",
    target_flag: true,
    thin_jd: false,
    off_target: false,
    pdf_available: true,
    score: 82.6,
    coverage: 0.55,
    off_target_reason: null,
  },
  {
    posting_id: 37440,
    job_id: 27810,
    title: "Engineering Manager, Payments",
    company: "Block",
    location: "Oakland, CA",
    remote_policy: "remote",
    posted_days: 31,
    first_seen: "2026-07-26T08:00:00Z",
    status: "open",
    verdict: "ineligible",
    apply_url: "https://block.xyz/careers/37440",
    delivered_run_id: 101,
    tex_uri: "file://~/boardwatch-applications/2026-07-26/tailored-37440.tex",
    pdf_uri: "file://~/boardwatch-applications/2026-07-26/tailored-37440.pdf",
    target_flag: false,
    thin_jd: false,
    off_target: true,
    pdf_available: true,
    score: 44.3,
    coverage: 0.29,
    off_target_reason:
      'seniority gate: band "manager" is above target_seniority_band=entry (matched "Engineering Manager")',
  },
  {
    posting_id: 41300,
    job_id: 30950,
    title: "Systems Engineer, Compilers",
    company: "Modular",
    location: "Palo Alto, CA",
    remote_policy: null,
    posted_days: 2,
    first_seen: "2026-08-24T16:44:00Z",
    status: "open",
    // No verdict recorded at all. Distinct from `uncertain`.
    verdict: null,
    apply_url: null,
    delivered_run_id: 114,
    tex_uri: "file://~/boardwatch-applications/2026-08-24/tailored-41300.tex",
    pdf_uri: "file://~/boardwatch-applications/2026-08-24/tailored-41300.pdf",
    target_flag: null,
    thin_jd: false,
    off_target: false,
    pdf_available: true,
    score: null,
    coverage: 0.47,
    off_target_reason: null,
  },
  {
    posting_id: 40777,
    job_id: 30388,
    title: "Software Engineer, Distributed Storage",
    company: "Vast Data",
    location: "New York, NY",
    remote_policy: "hybrid",
    posted_days: 4,
    first_seen: "2026-08-22T13:30:00Z",
    status: "open",
    verdict: "eligible",
    apply_url: "https://vastdata.com/careers/40777",
    delivered_run_id: 114,
    tex_uri: "file://~/boardwatch-applications/2026-08-22/tailored-40777.tex",
    pdf_uri: "file://~/boardwatch-applications/2026-08-22/tailored-40777.pdf",
    target_flag: true,
    thin_jd: false,
    off_target: false,
    pdf_available: true,
    score: 88.9,
    coverage: 0.81,
    off_target_reason: null,
  },
  {
    posting_id: 40778,
    job_id: 30388,
    title: "Software Engineer, Distributed Storage",
    company: "Vast Data",
    location: "Austin, TX",
    remote_policy: "hybrid",
    posted_days: 4,
    first_seen: "2026-08-22T13:31:00Z",
    status: "open",
    verdict: "eligible",
    apply_url: "https://vastdata.com/careers/40778",
    delivered_run_id: 114,
    tex_uri: "file://~/boardwatch-applications/2026-08-22/tailored-40778.tex",
    pdf_uri: "file://~/boardwatch-applications/2026-08-22/tailored-40778.pdf",
    target_flag: true,
    thin_jd: false,
    off_target: false,
    pdf_available: true,
    score: 88.1,
    coverage: 0.8,
    off_target_reason: null,
  },
  {
    posting_id: 39001,
    job_id: 29010,
    title: "Firmware Engineer, Storage Controllers",
    company: "Micron",
    location: "Boise, ID",
    remote_policy: "onsite",
    posted_days: 17,
    first_seen: "2026-08-09T07:12:00Z",
    status: "open",
    verdict: "ineligible",
    apply_url: "https://micron.eightfold.ai/careers/job/39001",
    delivered_run_id: 106,
    tex_uri: "file://~/boardwatch-applications/2026-08-09/tailored-39001.tex",
    pdf_uri: "file://~/boardwatch-applications/2026-08-09/tailored-39001.pdf",
    target_flag: false,
    thin_jd: false,
    off_target: false,
    pdf_available: true,
    score: 52.7,
    coverage: 0.33,
    off_target_reason: null,
  },
  {
    posting_id: 41415,
    job_id: 31002,
    title: "Software Engineer, Developer Experience",
    company: "Sentry",
    location: "Remote, United States",
    remote_policy: "remote",
    posted_days: 0,
    first_seen: "2026-08-26T06:02:00Z",
    status: "open",
    verdict: "eligible",
    apply_url: "http://sentry.io/careers/41415",
    delivered_run_id: 114,
    tex_uri: "file://~/boardwatch-applications/2026-08-26/tailored-41415.tex",
    pdf_uri: "file://~/boardwatch-applications/2026-08-26/tailored-41415.pdf",
    target_flag: true,
    thin_jd: false,
    off_target: false,
    pdf_available: true,
    score: 91.2,
    coverage: 0.77,
    off_target_reason: null,
  },
];

const COMPANIES = [
  "Stripe", "Databricks", "Snowflake", "Cloudflare", "Figma", "Notion", "Airtable", "Asana",
  "Atlassian", "Twilio", "Okta", "HashiCorp", "MongoDB", "Elastic", "Confluent", "Redis",
  "Grafana Labs", "Netlify", "Vercel", "Linear", "Retool", "Rippling", "Gusto", "Brex",
  "Plaid", "Affirm", "Chime", "Robinhood", "Coinbase", "Nvidia", "AMD", "Qualcomm",
  "Broadcom", "Marvell", "Analog Devices", "Texas Instruments", "Applied Materials", "Lam Research",
  "KLA", "Synopsys", "Cadence", "Arm", "SiFive", "Groq", "Lambda", "Together AI",
];

const TITLES: { title: string; offTarget: string | null }[] = [
  { title: "Software Engineer, Backend", offTarget: null },
  { title: "Software Engineer, Frontend", offTarget: null },
  { title: "Software Engineer, Infrastructure", offTarget: null },
  { title: "Software Engineer, New Grad", offTarget: null },
  { title: "Software Development Engineer I", offTarget: null },
  { title: "Platform Engineer", offTarget: null },
  { title: "Compiler Engineer", offTarget: null },
  { title: "Machine Learning Engineer", offTarget: null },
  { title: "Site Reliability Engineer", offTarget: null },
  { title: "Full Stack Engineer", offTarget: null },
  { title: "Embedded Software Engineer", offTarget: null },
  { title: "Test Engineer, Silicon", offTarget: null },
  {
    title: "Technical Program Manager, Infrastructure",
    offTarget: 'role gate: title family "program manager" is denied (matched "Program Manager")',
  },
  {
    title: "Solutions Architect, Data Platform",
    offTarget: 'role gate: title family "architect" is denied (matched "Solutions Architect")',
  },
  {
    title: "Systems Administrator, Build Infrastructure",
    offTarget: 'role gate: title family "administrator" is denied (matched "Administrator")',
  },
];

const LOCATIONS = [
  "San Francisco, CA", "New York, NY", "Seattle, WA", "Austin, TX", "Boston, MA",
  "Denver, CO", "Chicago, IL", "Remote, United States", "San Jose, CA", "Atlanta, GA",
  "Portland, OR", "Raleigh, NC", "Pittsburgh, PA", "Madison, WI", "Bellevue, WA",
];

const REMOTE: (string | null)[] = ["remote", "hybrid", "onsite", null, null, null];

/** A tiny deterministic PRNG so the fixture set is identical on every reload. */
function makeRandom(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (state * 1664525 + 1013904223) >>> 0;
    return state / 0x100000000;
  };
}

function pick<T>(random: () => number, pool: readonly T[]): T {
  // `pool` is never empty in this file; the non-null assertion keeps the call sites readable
  // under `noUncheckedIndexedAccess`.
  return pool[Math.floor(random() * pool.length)]!;
}

function generate(count: number, seed: number, idBase: number): QueueRow[] {
  const random = makeRandom(seed);
  const rows: QueueRow[] = [];
  for (let index = 0; index < count; index += 1) {
    const postingId = idBase + index * 7;
    const spec = pick(random, TITLES);
    const roll = random();
    // 41% eligible / 47% uncertain / 12% ineligible. About half of the uncertain rows are real
    // engineering roles the taxonomy did not recognise, so `uncertain` is a large, ordinary bucket.
    const verdict: Verdict = roll < 0.41 ? "eligible" : roll < 0.88 ? "uncertain" : "ineligible";
    const hasDate = random() > 0.05;
    const thin = random() < 0.11;
    rows.push({
      posting_id: postingId,
      job_id: 15000 + index * 5,
      title: spec.title,
      company: pick(random, COMPANIES),
      location: pick(random, LOCATIONS),
      remote_policy: pick(random, REMOTE),
      posted_days: hasDate ? Math.floor(random() * 45) : null,
      first_seen: new Date(Date.UTC(2026, 7, 1 + Math.floor(random() * 25), 9, 0, 0)).toISOString(),
      status: random() < 0.06 ? "closed" : "open",
      verdict,
      apply_url: `https://boards.example.com/jobs/${String(postingId)}`,
      delivered_run_id: 100 + Math.floor(random() * 15),
      tex_uri: `file://~/boardwatch-applications/2026-08-18/tailored-${String(postingId)}.tex`,
      pdf_uri: `file://~/boardwatch-applications/2026-08-18/tailored-${String(postingId)}.pdf`,
      target_flag: random() < 0.3 ? true : random() < 0.5 ? false : null,
      thin_jd: thin,
      off_target: spec.offTarget !== null,
      pdf_available: true,
      score: Math.round((35 + random() * 60) * 10) / 10,
      coverage: thin ? null : Math.round(random() * 100) / 100,
      off_target_reason: spec.offTarget,
    });
  }
  return rows;
}

/** Ranked, as the contract promises: score descending, unscored last. */
export function byRank(a: QueueRow, b: QueueRow): number {
  if (a.score === null) return b.score === null ? 0 : 1;
  if (b.score === null) return -1;
  return b.score - a.score;
}

export const QUEUE_ROWS: QueueRow[] = [...AUTHORED, ...generate(524, 0x51ed, 20000)].sort(byRank);

/*
 * Four leads that "arrive" thirty seconds after load, so the quiet "N new — refresh" line is
 * demonstrable. They are a SEPARATE batch rather than a slice off the tail of `QUEUE_ROWS`: a tail
 * slice held back whichever rows happened to rank last, which silently hid the authored
 * no-current-version case for the first half minute.
 */
export const LATE_ROWS: QueueRow[] = generate(4, 0x9a3f, 50000).sort(byRank);

const JD_PARAGRAPHS = [
  "About the team. We build and operate the systems that move every request through the product, from the edge to the storage layer. The team owns its services end to end: design, implementation, rollout, on-call and the eventual deprecation.",
  "What you will do. Design and ship services in a typed language. Instrument what you build so a regression is visible before a customer reports it. Review your colleagues' changes with the same care you want applied to your own. Take part in an on-call rotation with a documented escalation path.",
  "What we look for. A bachelor's degree in computer science or equivalent practical experience. Fluency in at least one of Python, Go, Rust, Java or TypeScript. Working knowledge of relational databases and of the failure modes of distributed systems. Written communication that a reader outside your team can follow.",
  "Nice to have. Experience with Kubernetes, Terraform or a comparable declarative infrastructure toolchain. Exposure to a compiled systems language. Prior work on a service with a published availability target.",
  "Compensation and process. Our interview loop is one recruiter conversation, one technical screen, and a virtual on-site of three sessions. We give a decision within five business days of the on-site. We are unable to sponsor an employment visa for this position at this time.",
];

function requirementsFor(postingId: number, covered: number, missing: number): RequirementView[] {
  const coveredTerms = ["python", "distributed systems", "sql", "code review", "testing", "go"];
  const missingTerms = ["kubernetes", "terraform", "rust", "on-call", "grpc"];
  const out: RequirementView[] = [];
  for (let index = 0; index < covered; index += 1) {
    out.push({
      requirement: coveredTerms[index % coveredTerms.length]!,
      covered: true,
      rule: index === 0 ? "degree_level" : null,
      disposition: index === 0 ? "eligible" : null,
      profile_field: index === 0 ? "education.highest_degree" : null,
      quote:
        index === 0
          ? "A bachelor's degree in computer science or equivalent practical experience."
          : null,
      rationale: index === 0 ? "Profile records a completed bachelor's degree." : null,
    });
  }
  for (let index = 0; index < missing; index += 1) {
    out.push({
      requirement: missingTerms[index % missingTerms.length]!,
      covered: false,
      rule: index === 0 ? "work_authorization" : null,
      disposition: index === 0 ? (postingId % 3 === 0 ? "ineligible" : "abstain") : null,
      profile_field: index === 0 ? "work_auth.needs_sponsorship" : null,
      quote:
        index === 0
          ? "We are unable to sponsor an employment visa for this position at this time."
          : null,
      rationale:
        index === 0
          ? postingId % 3 === 0
            ? "Profile requires sponsorship and the posting refuses it."
            : "No profile value resolved for needs_sponsorship, so the rule abstains."
          : null,
    });
  }
  return out;
}

/** Details the generic builder cannot express, keyed by posting id. */
const AUTHORED_DETAILS: Record<number, Partial<QueueDetail>> = {
  // No current posting version: the JD is unavailable, and the pane says so rather than showing
  // an empty panel that reads as "the job has no description".
  41300: { jd_body: null, requirements: [] },
  // A JD the extractor recognised nothing in. Two empty lists would read as "nothing missing",
  // which is the most dangerous possible rendering, so the pane states it explicitly.
  40990: { jd_body: "Software Engineer. Apply through the link. Reqs on request.", requirements: [] },
};

export function detailFor(row: QueueRow): QueueDetail {
  const authored = AUTHORED_DETAILS[row.posting_id];
  const covered = row.coverage === null ? 0 : Math.max(1, Math.round(row.coverage * 6));
  const missing = row.coverage === null ? 0 : Math.max(1, 6 - covered);
  return {
    row,
    jd_body: JD_PARAGRAPHS.join("\n\n"),
    requirements: requirementsFor(row.posting_id, covered, missing),
    board_target: `greenhouse:${row.company.toLowerCase().replace(/[^a-z0-9]+/g, "")}`,
    ...authored,
  };
}
