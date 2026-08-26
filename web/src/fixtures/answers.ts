/*
 * Answers-panel fixtures. Placeholders only — `answers.yaml` itself is never committed, never
 * copied into an output folder and never logged. The `note` field is shown and never copied,
 * because its most important use is a warning against reusing the answer as written.
 *
 * "Placeholder" is stricter here than "not Mit's". The identity block must not even have the SHAPE
 * of contact details: no dialable digit run, no `linkedin.com/in/…` profile path, no absolute home
 * path. Those are the shapes the repository's generalization gate reads as leaked personal data,
 * and a plausible-looking placeholder is indistinguishable from a real leak both to that gate and
 * to a reader. Reserved `example.com` names are used for the same reason.
 */
import type { Answers } from "../api/types";

export const ANSWERS: Answers = {
  identity: {
    full_name: "Example Owner",
    email: "owner@example.com",
    phone: "+1-XXX-XXX-XXXX",
    city_state: "Boston, MA",
    linkedin: "https://profile.example.com/example-owner",
    github: "https://github.com/example-owner",
    portfolio: null,
  },
  work_auth: {
    status: "F-1 OPT",
    needs_sponsorship: "yes, after 2028",
    authorized_now: "yes",
    requires_h1b_transfer: "no",
  },
  education: [
    {
      institution: "Example University",
      degree: "MS, Computer Science",
      graduation: "2026-05",
      gpa: "3.8",
    },
    {
      institution: "Example Institute of Technology",
      degree: "BE, Information Technology",
      graduation: "2023-06",
      gpa: "3.6",
    },
  ],
  questions: [
    {
      q: "Notice period",
      a: "Two weeks.",
      note: null,
    },
    {
      q: "Salary expectation",
      a: "Open, and calibrated to the level and location once we have talked about scope.",
      note: "Do not paste a number into a required field without checking the posted band first. Two earlier versions of this answer quoted a figure that was below the band published on the same posting.",
    },
    {
      q: "Why this company",
      a: "Placeholder. Rewrite per application; a reused paragraph is worse than a short specific one.",
      note: "Never submit as-is.",
    },
    {
      q: "Are you legally authorized to work in the United States?",
      a: "Yes.",
      note: null,
    },
    {
      q: "Will you now or in the future require sponsorship?",
      a: "Yes.",
      note: "Answer honestly. Several postings that ask this also refuse sponsorship in the body; the eligibility rule quotes that span.",
    },
  ],
};
