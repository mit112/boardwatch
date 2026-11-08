import { isSafeHttpUrl } from "./format";

// Group tenant subdomains by the application service. Other sites keep their actual hostname;
// discovery provenance and guesses about redirects never determine a link's label.
const SITES: readonly [string, string][] = [
  ["greenhouse.io", "greenhouse"],
  ["lever.co", "lever"],
  ["ashbyhq.com", "ashby"],
  ["myworkdayjobs.com", "workday"],
  ["myworkdaysite.com", "workday"],
  ["workday.com", "workday"],
  ["smartrecruiters.com", "smartrecruiters"],
  ["icims.com", "icims"],
  ["taleo.net", "taleo"],
  ["successfactors.com", "successfactors"],
  ["bamboohr.com", "bamboohr"],
  ["breezy.hr", "breezy"],
  ["workable.com", "workable"],
  ["jobvite.com", "jobvite"],
  ["recruitee.com", "recruitee"],
  ["teamtailor.com", "teamtailor"],
  ["rippling.com", "rippling"],
  ["paylocity.com", "paylocity"],
  ["applytojob.com", "jazzhr"],
  ["ultipro.com", "ultipro"],
  ["oraclecloud.com", "oracle"],
  ["adp.com", "adp"],
  ["linkedin.com", "linkedin"],
  ["indeed.com", "indeed"],
  ["jobright.ai", "jobright"],
];

/** The site opened by this application link, shared by labels, filters and sorting. */
export function applicationSite(url: string | null | undefined): string | null {
  if (url == null || !isSafeHttpUrl(url)) return null;
  const host = new URL(url).hostname.toLowerCase().replace(/\.$/, "");
  const known = SITES.find(([domain]) => host === domain || host.endsWith(`.${domain}`));
  return known?.[1] ?? host.replace(/^www\./, "");
}
