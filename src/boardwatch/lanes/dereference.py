r"""URL -> posting-reference dereferencing (lane groundwork Part 2). No fetching here.

core.board_urls.parse_board_target turns a pasted board URL into (provider, slug) and
throws the rest of the path away. For four of the eight providers that is fine: greenhouse,
lever, ashby and workable all inline every body in the board response, so a link to one
of their postings is a COMPANY DISCOVERY problem — parse_board_target -> upsert_watch ->
run_scan already turns it into that company's whole board with no new code. SmartRecruiters,
Workday, Oracle HCM and Eightfold are different: they are the four providers that define a
`_detail_url` method, because their board list omits the body and a second per-posting request
is needed to get one. Dereferencing a posting LINK is therefore only necessary for those four
— and THREE of the four are dereferenced (see the SmartRecruiters, Workday and Oracle HCM
sections below); EIGHTFOLD IS REFUSED, deliberately, and its own section below says on what
evidence that refusal rests and what would lift it. Seven of the eight providers that reach
the catalog resolve. Across every one that does, a recovered `provider_posting_id` lets a later
aggregator-sourced posting converge with a board scan through
`UNIQUE(company_id, provider_posting_id)` instead of duplicating it. TWO registered providers
resolve nothing here and never reach the catalog — jibe and phenom, each on the employer's own
unbounded hostname, each with its own section below. phenom also needs a second per-posting
request, but it is a POST widget rather than a `_detail_url`, so it is not one of the four above.

THE EVIDENCE BEHIND EACH IS NOT EQUAL, and this paragraph exists so that is never read as
uniform. SmartRecruiters and Workday each cleared a bar of tens of thousands of real URLs
whose extracted reference equalled the stored `provider_posting_id` (the figures are in their
own sections). ORACLE HCM HAS NO SUCH CORPUS — boardwatch watches zero Oracle boards, so there
were none to measure. What its rule rests on instead is narrower and should be read as such:
the list endpoint was probed live on 2026-09-06 across three tenants and returns a bare digit
`Id`, the public URL carrying that `Id` verbatim as its last path segment was fetched and
answered (302, to the tenant's public browsing site), and `providers/oraclehcm.py:posting_url`
constructs exactly the shape this module inverts, pinned by a round-trip test. That is
internal consistency plus one confirmed live shape, NOT the convergence proof the other two
have.

This module supplies the missing half: reading the posting reference a detail fetch would
need back out of a posting URL, reusing parse_board_target for host/slug matching rather
than re-implementing it. There is no network code here (import nothing from
core/politeness.py) — every request contract that would consume a PostingTarget is
deferred to a later client plan whose first step is a live probe.

WHAT THE ROUND-TRIP TESTS ACTUALLY PROVE (read before trusting this rule against a live
URL). greenhouse (`absolute_url`, greenhouse.py:155), lever (`hostedUrl`, lever.py:120),
ashby (`jobUrl`, ashby.py:133) and workable (`url`/`shortlink`, workable.py:137) all read
`RawPosting.url` STRAIGHT OFF a field in the provider's own JSON payload — none of them
construct it. Every one of those providers' pinned fixtures states in its own README that
"All text is synthetic. No real company copy, names, URLs, ... was carried over from any
recorded board." So the round-trip test for those four providers proves this module's
extraction correctly inverts a URL VALUE THE FIXTURE'S AUTHOR CHOSE TO WRITE — evidence
that the code is internally consistent, not proof that a real greenhouse/lever/ashby/
workable URL takes this shape. (In practice these four are simple enough — and match the
public shapes documented by each provider — that this is a reasonable degree of
confidence; the point is narrower than "verified against a live URL", which it is not.)

THE SHAPE RULE IS EXACT, AND WHY IT HAS TO BE. Each of those four providers' posting URL
is one fixed path shape, read off the provider's own board_url host list plus the URL its
parser reports (`_POSTING_PATH_SHAPES` below): greenhouse `{slug}/jobs/{id}` (fixture
`absolute_url`: boards.greenhouse.io/acme/jobs/6000001), lever `{slug}/{id}` (`hostedUrl`:
jobs.lever.co/acme/a1000000-...-000000000001), ashby `{slug}/{id}` (`jobUrl`:
jobs.ashbyhq.com/acme/ashby-0001), workable `{slug}/j/{code}` (`url`:
apply.workable.com/acme/j/AAAA111111). A path LONGER than its provider's shape refuses
instead of reading the last segment, because a trailing chrome segment is not a posting
reference and the same pinned fixtures carry those URLs as siblings of the canonical one:
lever's `applyUrl` is `{id}/apply`, ashby's is `{id}/application`, workable's
`application_url` is `{code}/apply`. Aggregator listings deep-link to exactly those. Read
as a posting reference, `apply` and `application` are CONSTANT per provider, so two
different postings at one employer collide on
`UNIQUE(company_id, provider_posting_id)`: the second is applied as a REVISION of the
first, one real body is overwritten, and no `complete` board scan ever lists `apply`, so
it closes after two misses. That is the same defect class this module already refuses
SmartRecruiters for. An exact shape per provider is a CLOSED rule; a list of chrome
suffixes to exclude would have to grow for every one a provider or an aggregator invents.

SMARTRECRUITERS: RESOLVED as of 2026-09-01, and the evidence bar this paragraph set is the
reason it took this long. It previously refused every SmartRecruiters posting URL, because
the pinned fixture's `postingUrl` was authored to mimic the provider's CONSTRUCTED FALLBACK
(`smartrecruiters.py:213-216`) rather than a real URL, and the real public shape combines
the id and a title slug into ONE segment
(`https://www.smartrecruiters.com/SmartRecruiters/12308096-quality-assurance-manager`), so
the last-segment rule the other four providers use is wrong here. It named a candidate fix
-- the leading digit run `^\d+` -- and required "a live probe pinning at least one real
`postingUrl`, not an inference from documentation plus a synthetic fixture."

What it got instead of one probe: **3,041 real SmartRecruiters posting URLs already in the
live store, every one of them `jobs.smartrecruiters.com/{slug}/{digits}[-title]`, on which
the extracted reference equals the provider's own stored `provider_posting_id` 3,041 times
out of 3,041** -- the convergence proof this dereference exists to produce. A second,
independent system's ledger supplied 363 more, of which 362 conform.

**The 363rd is why the rule shipped here is ANCHORED and not the candidate.** SmartRecruiters
also issues UUID references (`jobs.smartrecruiters.com/servicenow/99c06c61-284f-4c2b-bd4d-
1a7b53bf3fa4`), and `^\d+` reads that as `99` -- a colliding two-character reference of
exactly the kind this module refused SmartRecruiters for in the first place. Requiring the
digit run to END the id (`^(\d+)(?:-|$)`) refuses it instead. Out-of-catalog stays a
failure, never a guess.

WORKDAY: RESOLVED as of 2026-09-01 for IDENTITY, and deliberately not for fetching. The
refusal above was written against the wrong contract. `_detail_url` does need an
`externalPath` path-string that no public URL is proven to map back to — but a
`PostingTarget` is never fetched. Both consumers read it for identity alone
(`lanes/jobapps.py:282` feeds `posting_ref` straight into `RawPosting.provider_posting_id`;
`lanes/hiringcafe.py:317` builds a `HitIdentity` from it), so what has to be recoverable is
`provider_posting_id`, which `providers/workday.py:_posting_id` derives as the final
`_`-delimited token of the externalPath's last segment when it holds a digit. That token is
carried verbatim in the public URL's last segment.

Measured, on the same bar SmartRecruiters had to clear: **93,044 provider-supplied
`externalUrl`s in the live store, on which the extracted reference equals that company's
stored `provider_posting_id` 93,044 out of 93,044**, with ZERO mismatches, counted through this
function rather than through the pattern it uses.

Measured through the same function, the FULL disposition is not all-resolves and should not be
read as one (all figures 2026-09-01; the independent set is live and grows daily). Our store,
93,044 URLs: **87,413 resolve and match the stored id with ZERO mismatches**, 5,472 raise
`UnknownBoardURL` (the `myworkdaysite.com` family), 159 are refused — 157 by the site guard and
2 by the ambiguity rule. The INDEPENDENT set is 4,521 Workday URLs from job-apps' ledger across
606 distinct hosts against our own 117: **4,456 resolve, 48 are refused, 17 raise**. Refusals
are not all board roots; most are the site-guard class below. The reference PATTERN agrees with
`_posting_id` on 4,398 of 4,407 last segments as sampled, which is a narrower claim than
"4,398 identities were produced" and is NOT evidence of coverage — coverage is the 4,456. The
detail-fetch contract remains unproven and nothing here lifts it.

PHENOM: NOT DEREFERENCEABLE BY SHAPE, and it never reaches this module's catalog at all. A
Phenom career site runs on the EMPLOYER's own domain, so `providers/phenom.py` registers neither
a paste host nor a host suffix, and `parse_board_target` raises `UnregisteredBoardHost` for every
Phenom URL before `parse_posting_target` can look at its path. That is the correct outcome and
not a gap to be plugged with a `_POSTING_PATH_SHAPES` row: the posting path VARIES PER SITE
(`{country}/{lang}/job/{jobId}` on the three measured sites, but `applyUrl` — the link an
aggregator actually deep-links to — points at the UNDERLYING ATS on two of them and is empty on
the third, so a Phenom posting is as likely to be seen as a brassring or workday URL as a Phenom
one). Deriving a phenom reference would need a host-to-board mapping this repo does not have,
and guessing one would mint company rows for boards that do not exist. Out-of-catalog stays a
failure, never a guess.

THE SHAPE IS POSITIONAL, NOT A `_POSTING_PATH_SHAPES` ROW, and that is why Workday needs a
branch rather than a catalog entry. Its career site sits INSIDE the composite slug, and the
segments around it vary: `{site}/job/{location}/{ref}`, `en-US/{site}/job/{location}/{ref}`
and `{site}/job/{ref}` all occur. What is invariant across all 97,451 measured URLs is the
position: `job` occurs exactly once, the career site is the segment IMMEDIATELY BEFORE it,
and the reference is the last segment with at most one location segment between. `details`
occurs zero times in either population, and no URL carries a trailing `/apply`; were one to,
`apply` holds no digit and the reference pattern refuses it.

THE SITE GUARD, AND WHY IT OUTLIVED THE DEFECT IT WAS WRITTEN FOR. `parse_board_target`
derives the site through `workday.slug_from_path`. That function USED to take the first
segment not in that provider's `_CHROME_SEGMENTS`, and `jobs` IS in that set, so a tenant
whose career site is literally named `Jobs` had the segment skipped and its LOCATION read as
the site: Red Hat's `redhat.wd5.myworkdayjobs.com/jobs/job/Raleigh/...` derived site
`Raleigh`, minting a company row for a board that does not exist, one per location. Measured
then: 157 live posting URLs here and 38 in the independent set (brandeis, carrier, redhat),
with `redhat/jobs` + `paypal/jobs` real watched rows reachable only through the explicit
`workday:host/tenant/site` form. This guard refused those rather than resolving them, and
deliberately did not repair the cause.

**THE CAUSE IS FIXED AND NO REPAIR IS OWED.** `slug_from_path` is read by GRAMMAR now (the
site is the first non-locale segment), so `Jobs` resolves correctly and none of those URLs
derives a city — including through `posting_identity` tier 2, which reaches the same function.
The store was checked for the rows the old behaviour would have left: of 153 Workday company
rows, ELEVEN tenants hold more than one site and every one is a real distinct career site
(`bmo/External` + `bmo/campus`, `visa/Visa` + `visa/Visa_Early_Careers`, ...). **Zero
city-as-site rows exist**, so the silent minting never actually landed one here and there is
nothing to drain. The guard stays because it is still reachable on a different shape — see the
comment at its own site, which names the surviving case and the check that confirmed one was
left.

JIBE: NOT DEREFERENCEABLE BY SHAPE, and it never reaches the shape catalog at all.

Two independent reasons, and the first one is the whole answer. (1) A Jibe board lives on the
EMPLOYER'S OWN hostname, so `providers/jibe.py` registers no paste host and no host suffix --
`parse_board_target` therefore raises `UnregisteredBoardHost` for every jibe posting URL,
before `_POSTING_PATH_SHAPES` is ever consulted. Registering a host pattern to reach it is not
available: the set of employer careers domains is unbounded and shares nothing but the
`/api/jobs` route, so any pattern wide enough to match them would claim hosts belonging to
every other vendor too. (2) Even given the host, the posting PATH is not one fixed shape. It
varies per tenant -- `/careers-home/jobs/{req_id}`, `/main/jobs/{req_id}` and `/jobs/{req_id}`
were all measured live on 2026-09-06 -- so the exact-shape rule the four inline-body providers
use has nothing to be exact about here, and a "last segment after any prefix" rule is precisely
the guess this module refuses.

Jibe is consequently absent from `_POSTING_PATH_SHAPES` and from `_POSTING_REF_PATTERNS` BY
DECISION, not by omission, and the catalog stays closed. The cost is bounded and is the same
one the four inline-body providers carry: a jibe board response inlines every body
(`description` + `qualifications` + `responsibilities`), so a link to one of its postings is a
COMPANY DISCOVERY problem, and the entry point for that is the explicit `jibe:<careers host>`
form. Nothing in this module has to change to lift it -- what would have to change first is a
measured, tenant-invariant posting path, which does not exist today.

EIGHTFOLD: REFUSED as of 2026-09-06, on the SHAPE catalog's own arithmetic and on the evidence
bar this module already set — not on ignorance of the shape. The shape is known and uniform:
every position row on all four tenants probed carries `positionUrl` as `/careers/job/{digits}`
(40 rows, one shape, zero exceptions), and the detail payload's `publicUrl` is that path under
the tenant host.

TWO SEPARATE THINGS BLOCK A CATALOG ROW, and only the first is mechanical. (1) `_POSTING_PATH_
SHAPES` encodes `{slug}/{*fixed}/{ref}` and its length test is `len(shape) + 2`, which assumes
the SLUG IS THE FIRST PATH SEGMENT. An Eightfold slug is the HOST (`providers/eightfold.py`),
so a posting path is `careers/job/{ref}` — three segments, no slug among them — and any entry
here would either be off by one or quietly redefine what the catalog's rows mean for the five
providers already in it. Eightfold would need its own branch, as Workday and Oracle HCM have.
(2) THE EVIDENCE IS THE WRONG KIND. What is measured is the SHAPE OF A FIELD IN A LIVE PAYLOAD,
sampled once.
SmartRecruiters was refused here for years on exactly that basis and was lifted only by 3,041
real posting URLs whose extracted reference equalled the stored `provider_posting_id` 3,041
times out of 3,041; Workday by 93,044. boardwatch watches ZERO Eightfold boards today, so that
convergence count is necessarily zero and cannot be raised by looking harder at the payload.

WHAT WOULD LIFT IT, stated so the next reader does not re-derive this paragraph: watch some
Eightfold boards, scan them, and check the extracted reference against the stored
`provider_posting_id` on real rows. Until then an Eightfold posting URL raises
`UnresolvablePostingURL` from the "no evidenced way" branch, which is the correct outcome and
not an omission.

**THE REFUSAL IS ALSO NARROWER THAN IT LOOKS, and that is worth knowing before sizing the
work.** Only a `*.eightfold.ai` URL reaches this function at all. An Eightfold tenant on the
employer's own domain (`careers.{employer}.test`) raises `UnregisteredBoardHost` from
`parse_board_target` one step earlier, because nothing distinguishes it from the employer's own
careers site — see the `board_hosts` comment in `providers/eightfold.py`. So lifting this
refusal buys convergence on the vendor-hosted minority only.

TWO KNOWN LIMITS, both measured, neither a guess. (1) `myworkdaysite.com` keeps raising
`UnknownBoardURL` from `parse_board_target`, and adding the host suffix would NOT help: the
same tenant is stored under the other host, so `wd5.myworkdaysite.com/recruiting/chewy/External`
would still not equal the stored `chewy.wd5.myworkdayjobs.com/chewy/External`. (2) Site case
is preserved by `workday.split_slug`, and that costs NOTHING here — a claim this paragraph got
wrong once and is corrected in place rather than quietly dropped. `store/queries.py:stored_slug`
folds case and `upsert_lane_company` calls it for every lane snapshot, so a URL spelling
`Aderant_External_Careers` resolves to the row stored `aderant_external_careers` and converges
against it; `pipeline/runner.py` takes the company id back from the upsert for exactly this
reason. Of 4,456 independent Workday URLs that parse to a reference, **896 converge onto a
posting the board scan already holds**. An earlier reading of 589 with "307 lost to site case"
was an artifact of joining slug strings instead of modelling the resolver, and the 307 were
never lost.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

from boardwatch.core.board_urls import parse_board_target

# Provider -> the FIXED path segments that sit between the board slug and the posting
# reference. A posting URL's path must be exactly `{slug}/{*fixed}/{ref}` — nothing
# shorter, nothing longer. See the module docstring for the evidence behind each shape and
# for why a longer path must refuse rather than read its last segment. A closed catalog:
# any provider absent from it refuses rather than guesses. Workday is deliberately NOT in it
# and is NOT an omission: its shape is POSITIONAL, not a fixed run of segments, so it takes
# its own branch in parse_posting_target — see the module docstring. oraclehcm is absent for the
# same reason: its career site is the second half of its composite slug and sits MID-path, so the
# "{slug}/{*fixed}/{ref}" grammar cannot express it either. The catalog stays closed.
# The last path segment IS the posting reference for every provider above. SmartRecruiters is
# the one provider where it is not: its segment is `{id}-{title-slug}`, so a reference has to be
# read back out of it. Keyed here rather than special-cased in the function so the rule stays a
# CLOSED per-provider fact, and a provider with no entry keeps using the whole segment.
#
# The digit run must END the id -- `(?:-|$)`, never a bare `^\d+`. The module text below records
# `^\d+` as the candidate rule; against real data it is UNSAFE. SmartRecruiters also issues UUID
# references (measured: `jobs.smartrecruiters.com/servicenow/99c06c61-284f-4c2b-bd4d-1a7b53bf3fa4`),
# and `^\d+` reads that as `99` -- a short, colliding reference of exactly the kind this module
# refuses SmartRecruiters for in the first place. Anchored, it matches nothing and the URL refuses.
_POSTING_REF_PATTERNS: dict[str, re.Pattern[str]] = {
    "smartrecruiters": re.compile(r"^(\d+)(?:-|$)"),
    # Workday: the final `_`-delimited token, required to hold a digit. This must stay
    # equivalent to `providers/workday.py:_posting_id`, because convergence is
    # `UNIQUE(company_id, provider_posting_id)` and that function is what writes the stored
    # side -- `test_the_workday_reference_pattern_matches_the_providers_own_id_rule` pins the
    # equivalence rather than trusting the two to drift together. Expressed here rather than
    # imported so this module keeps importing no provider code (see the docstring's no-network
    # rule; `providers/workday` pulls in `core/politeness`). A last segment with no such token
    # -- a board root, or `M_tx` -- matches nothing and the URL refuses.
    "workday": re.compile(r"_([^_]*\d[^_]*)$"),
}

_POSTING_PATH_SHAPES: dict[str, tuple[str, ...]] = {
    "greenhouse": ("jobs",),
    "lever": (),
    "ashby": (),
    "smartrecruiters": (),
    "workable": ("j",),
}

# The one segment a workday posting path is anchored on. Measured over 97,451 real URLs
# (93,044 provider-supplied, 4,407 from an independent ledger): `job` occurs in every posting
# URL and `details` occurs in none, so a second member here would be a guess, not a catalog.
_WORKDAY_VERB = "job"

# Oracle HCM's public career-site path, which is FIXED but carries the career site inside it:
# `hcmUI/CandidateExperience/{locale}/sites/{site}/job/{ref}`. Positional like Workday rather
# than a `_POSTING_PATH_SHAPES` row for the same reason -- the slug's second half IS one of
# these segments -- but unlike Workday nothing here varies except the locale, so the whole
# shape is pinned rather than anchored on a single verb.
_ORACLEHCM_PREFIX = ("hcmui", "candidateexperience")
_ORACLEHCM_SITES = "sites"
_ORACLEHCM_VERB = "job"


class UnresolvablePostingURL(ValueError):
    """A recognized board URL that carries no posting reference this repo can evidence.

    Kept distinct from board_urls.UnknownBoardURL, which means "not a recognized board
    target at all" — that one is left to propagate unchanged from parse_board_target so a
    caller can tell the two conditions apart.
    """


@dataclass(frozen=True)
class PostingTarget:
    provider: str
    slug: str
    posting_ref: str


def _path_segments(url: str) -> list[str]:
    """Path segments, normalized EXACTLY as parse_board_target normalizes.

    parse_board_target deliberately accepts scheme-less input by prefixing `https://`
    (`boards.greenhouse.io/acme` is a valid board target). Without the same prefix here,
    urlparse reads the hostname as the first path segment, so a bare board root would parse
    as a posting whose reference is the slug. Two functions in one call chain must not
    disagree about their input domain.
    """
    url = url.strip()
    parsed = urlparse(url if "://" in url else f"https://{url}")
    return [part for part in parsed.path.split("/") if part]


def parse_posting_target(url: str) -> PostingTarget:
    """(provider, slug, posting_ref) for a posting URL.

    Raises board_urls.UnknownBoardURL, unchanged, when `url` is not a recognized board
    target at all. Raises UnresolvablePostingURL when it IS recognized but this repo has
    no evidenced way to read a posting reference back out of it: any path that is not
    exactly its provider's posting shape — a bare board root, or a canonical posting URL
    with a trailing chrome segment such as lever's `/apply` or ashby's `/application`
    (see the module docstring).

    Workday takes its own branch because its shape is POSITIONAL rather than a fixed run
    of segments between the slug and the reference.
    """
    provider, slug = parse_board_target(url)
    if provider == "workday":
        return _workday_posting_target(url, slug)
    if provider == "oraclehcm":
        return _oraclehcm_posting_target(url, slug)
    shape = _POSTING_PATH_SHAPES.get(provider)
    if shape is None:
        raise UnresolvablePostingURL(
            f"{provider!r} posting URLs carry no posting reference evidenced in this "
            f"repo: {url!r}"
        )
    segments = _path_segments(url)
    if len(segments) != len(shape) + 2 or tuple(segments[1:-1]) != shape:
        expected = "/".join(("{slug}", *shape, "{posting_ref}"))
        raise UnresolvablePostingURL(
            f"{provider!r} posting URLs are {expected}; {url!r} is not that shape"
        )
    pattern = _POSTING_REF_PATTERNS.get(provider)
    if pattern is None:
        return PostingTarget(provider=provider, slug=slug, posting_ref=segments[-1])
    matched = pattern.match(segments[-1])
    if matched is None:
        # An out-of-catalog shape refuses rather than guessing. Guessing here is the specific
        # defect this module exists to prevent: a wrong reference collides on
        # `UNIQUE(company_id, provider_posting_id)` and one real body is overwritten.
        raise UnresolvablePostingURL(
            f"{provider!r} posting reference is not readable from {segments[-1]!r} in {url!r}"
        )
    return PostingTarget(provider=provider, slug=slug, posting_ref=matched.group(1))


def _oraclehcm_posting_target(url: str, slug: str) -> PostingTarget:
    """Oracle HCM's posting URL, read positionally.

    Not expressible as a `_POSTING_PATH_SHAPES` row because the career site is the second
    half of the composite slug and sits mid-path. The shape is otherwise exact and CLOSED:
    `hcmUI/CandidateExperience/{locale}/sites/{site}/job/{ref}` -- seven segments, no optional
    location segment and no trailing chrome admitted. `providers/oraclehcm.py:posting_url`
    constructs exactly this, and a round-trip test pins the two halves together: if they
    disagreed, a lane-sourced posting could not converge with a board scan on
    `UNIQUE(company_id, provider_posting_id)`.

    The reference is the LAST segment verbatim. Oracle requisition ids are bare digit strings
    (`Id: "344533"`) carried unchanged in the URL, with no title slug fused onto them the way
    SmartRecruiters fuses one, so there is nothing to read back out and no pattern is needed.
    A longer path refuses rather than reading its last segment -- the rule the module
    docstring sets out, and the reason a `/job/{ref}/apply` deep link cannot mint `apply` as a
    constant, colliding reference for every posting at one employer.
    """
    segments = _path_segments(url)
    lowered = [segment.lower() for segment in segments]
    site = slug.rsplit("/", 1)[-1]
    if (
        len(segments) != 7
        or tuple(lowered[:2]) != _ORACLEHCM_PREFIX
        or lowered[3] != _ORACLEHCM_SITES
        or lowered[5] != _ORACLEHCM_VERB
    ):
        raise UnresolvablePostingURL(
            "oraclehcm posting URLs are "
            "hcmUI/CandidateExperience/{locale}/sites/{site}/job/{posting_ref}; "
            f"{url!r} is not that shape"
        )
    # The site in the path must be the one the slug names. `parse_board_target` derived the
    # slug from this same path, so the two can only disagree if the normalizer rewrote it --
    # but this is the guard that keeps the pair honest if either side later changes.
    if segments[4] != site:
        raise UnresolvablePostingURL(
            f"oraclehcm career site {site!r} is not the segment after "
            f"{_ORACLEHCM_SITES!r} ({segments[4]!r}) in {url!r}"
        )
    return PostingTarget(provider="oraclehcm", slug=slug, posting_ref=segments[-1])


def _workday_posting_target(url: str, slug: str) -> PostingTarget:
    """Workday's posting URL, read positionally. See the module docstring for the evidence.

    Not expressible as a `_POSTING_PATH_SHAPES` row: the career site is part of the
    composite slug, an optional `en-US` locale segment may precede it, and the location
    segment between `job` and the reference is sometimes absent. What is invariant over the
    97,451 measured URLs is that `job` occurs exactly once, the site is the segment
    immediately before it, and the reference is the last segment.
    """
    segments = _path_segments(url)
    lowered = [segment.lower() for segment in segments]
    if lowered.count(_WORKDAY_VERB) != 1:
        raise UnresolvablePostingURL(
            f"a workday posting URL carries exactly one {_WORKDAY_VERB!r} segment; "
            f"{url!r} carries {lowered.count(_WORKDAY_VERB)}"
        )
    verb = lowered.index(_WORKDAY_VERB)
    # The site must precede `job`, and the reference must follow it with at most one
    # location segment between. Anything longer is chrome this repo has not evidenced.
    if verb == 0 or not 1 <= len(segments) - verb - 1 <= 2:
        raise UnresolvablePostingURL(
            f"workday posting URLs are {{site}}/job/[{{location}}/]{{posting_ref}}; "
            f"{url!r} is not that shape"
        )
    # The PREFIX is closed too, not just the suffix. `slug_from_path` skips ANY number of chrome
    # or locale-shaped segments, so without this every one of them is silently tolerated and
    # `login/12-34/AcmeCareers/job/...` resolves as though it were canonical. Measured over
    # 91,871 real URLs the only segments that ever precede the career site are a locale
    # (`en-US`) and a repeat of the site itself (`SemtechCareers/SemtechCareers`,
    # `en-US/wellsfargojobs/wellsfargojobs`); nothing else occurs, so nothing else is admitted.
    # Refusing the rest costs 0 of 91,871.
    if not all(
        (len(s) == 5 and s[2] == "-") or s == segments[verb - 1] for s in segments[: verb - 1]
    ):
        raise UnresolvablePostingURL(
            f"workday posting URLs carry only a locale or a repeated career site before "
            f"{_WORKDAY_VERB!r}; {url!r} carries {segments[: verb - 1]!r}"
        )
    # THE GUARD. Its live case is GONE as of the `slug_from_path` rewrite: that function is read
    # by grammar now, so a career site named `Jobs` (redhat, paypal, brandeis, carrier — 157
    # URLs here, 38 independent) derives correctly and RESOLVES rather than being refused. This
    # stays because it is not unreachable: `slug_from_path` skips at most one leading locale, so
    # a path carrying two derives the second locale as the site while the real one sits before
    # `job`. That was CHECKED, not assumed — the prefix rule above runs first and swallows every
    # other shape that used to arrive here, and had nothing been left this guard would have been
    # deleted rather than kept as decoration.
    if segments[verb - 1] != slug.rsplit("/", 1)[-1]:
        raise UnresolvablePostingURL(
            f"workday career site {slug.rsplit('/', 1)[-1]!r} is not the segment before "
            f"{_WORKDAY_VERB!r} ({segments[verb - 1]!r}) in {url!r}"
        )
    # AMBIGUITY. Two segments after `job` is `{location}/{ref}` in every measured URL, but
    # the shape alone cannot distinguish it from `{ref}/{trailing_chrome}`: given
    # `.../job/Engineer_REQ999/apply_REQ123`, reading the last segment yields REQ123 while the
    # posting is REQ999, and ingesting that overwrites a real REQ123 as a revision. So the
    # reference must be UNAMBIGUOUS -- no earlier post-`job` segment may also look like one.
    # Measured cost of the refusal: 2 of 91,871 real URLs, both Lowe's, whose LOCATION segment
    # (`LWS_USA_LPS---Rancho-Cucamonga-CA-4546`) happens to end in a digit-bearing token. Their
    # last segment does resolve correctly, so those two are given up deliberately -- identity
    # minting fails safe, and 0.002% is the price of not depending on trailing chrome never
    # carrying an underscore.
    if any(_POSTING_REF_PATTERNS["workday"].search(s) for s in segments[verb + 1 : -1]):
        raise UnresolvablePostingURL(
            f"workday posting reference is ambiguous in {url!r}: more than one segment after "
            f"{_WORKDAY_VERB!r} reads as a reference"
        )
    matched = _POSTING_REF_PATTERNS["workday"].search(segments[-1])
    if matched is None:
        raise UnresolvablePostingURL(
            f"workday posting reference is not readable from {segments[-1]!r} in {url!r}"
        )
    return PostingTarget(provider="workday", slug=slug, posting_ref=matched.group(1))
