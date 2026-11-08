import { describe, expect, it } from "vitest";

import { applicationSite } from "../lib/applicationSite";

// Expected labels name the service in each URL, never a posting's discovery provider.
describe("application sites", () => {
  it.each([
    ["https://example.wd5.myworkdayjobs.com/jobs/1", "workday"],
    ["https://example.wd1.myworkdaysite.com/recruiting/jobs/1", "workday"],
    ["https://job-boards.eu.greenhouse.io/example/jobs/1", "greenhouse"],
    ["https://jobs.ashbyhq.com/example/1", "ashby"],
    ["https://jobs.lever.co/example/1", "lever"],
    ["https://www.linkedin.com/jobs/view/1", "linkedin"],
    ["https://uk.indeed.com/viewjob?jk=1", "indeed"],
    ["https://jobright.ai/jobs/1", "jobright"],
    ["https://WWW.Example.COM/jobs/1", "example.com"],
    ["https://careers.example.co.uk/jobs/1", "careers.example.co.uk"],
    ["https://grnh.se/abc", "grnh.se"],
    ["https://example.com/?gh_jid=1", "example.com"],
    ["https://boards.greenhouse.io.evil.example/1", "boards.greenhouse.io.evil.example"],
    ["https://notlinkedin.com/jobs/1", "notlinkedin.com"],
    ["https://linkedin.com@example.com/jobs/1", "example.com"],
    ["https://example.com/jobs/linkedin.com", "example.com"],
  ])("labels %s as %s", (url, expected) => {
    expect(applicationSite(url)).toBe(expected);
  });

  it.each([null, undefined, "", "/jobs/1", "not a url", "javascript:alert(1)", "file:///jobs/1"])(
    "does not invent a site for %s",
    (url) => { expect(applicationSite(url)).toBeNull(); },
  );
});
