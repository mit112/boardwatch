r"""URL -> posting-reference dereferencing (lane groundwork Part 2). No fetching here.

core.board_urls.parse_board_target turns a pasted board URL into (provider, slug) and
throws the rest of the path away. For four of the six providers that is fine: greenhouse,
lever, ashby and workable all inline every body in the board response, so a link to one
of their postings is a COMPANY DISCOVERY problem — parse_board_target -> upsert_watch ->
run_scan already turns it into that company's whole board with no new code. SmartRecruiters
and Workday are different: they are the only two providers that define a `_detail_url`
method, because their board list omits the body and a second per-posting request is
needed to get one. Dereferencing a posting LINK is therefore only necessary for those two
— and BOTH are now dereferenced, each on measured evidence rather than a live probe (see the
SmartRecruiters and Workday sections below). All six providers resolve. Across every one, a
recovered `provider_posting_id` lets a later aggregator-sourced posting converge with a board
scan through `UNIQUE(company_id, provider_posting_id)` instead of duplicating it.

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

THE SHAPE IS POSITIONAL, NOT A `_POSTING_PATH_SHAPES` ROW, and that is why Workday needs a
branch rather than a catalog entry. Its career site sits INSIDE the composite slug, and the
segments around it vary: `{site}/job/{location}/{ref}`, `en-US/{site}/job/{location}/{ref}`
and `{site}/job/{ref}` all occur. What is invariant across all 97,451 measured URLs is the
position: `job` occurs exactly once, the career site is the segment IMMEDIATELY BEFORE it,
and the reference is the last segment with at most one location segment between. `details`
occurs zero times in either population, and no URL carries a trailing `/apply`; were one to,
`apply` holds no digit and the reference pattern refuses it.

THE SITE GUARD IS THE LOAD-BEARING PART. `parse_board_target` derives the site through
`workday.slug_from_path`, which takes the first segment that is not in that provider's
`_CHROME_SEGMENTS` — and `jobs` IS in that set. So a tenant whose career site is literally
named `Jobs` has the segment skipped and its LOCATION read as the site: Red Hat's
`redhat.wd5.myworkdayjobs.com/jobs/job/Raleigh/...` derives site `Raleigh`. That mints a
company row for a board that does not exist, silently, one per location. Measured: 38 URLs
in the independent set (brandeis, carrier, redhat), and `redhat/jobs` + `paypal/jobs` are
real watched rows reachable only through the explicit `workday:host/tenant/site` form.
Requiring the derived site to EQUAL the segment before `job` refuses those instead.
**That guard does not repair the underlying defect** — a refused URL still falls through to
`posting_identity`'s tier 2, which calls `parse_board_target` directly and still mints the
wrong slug. Fixing `slug_from_path` changes board IMPORT behaviour and is a separate change.

TWO KNOWN LIMITS, both measured, neither a guess. (1) `myworkdaysite.com` keeps raising
`UnknownBoardURL` from `parse_board_target`, and adding the host suffix would NOT help: the
same tenant is stored under the other host, so `wd5.myworkdaysite.com/recruiting/chewy/External`
would still not equal the stored `chewy.wd5.myworkdayjobs.com/chewy/External`. (2) Site case
is preserved by `workday.split_slug` on purpose, so a URL spelling `Aderant_External_Careers`
does not converge with a row stored `aderant_external_careers`. Of 4,456 independent Workday
URLs that parse to a reference, **589 converge onto a posting the board scan already holds,
and 307 more are lost to site case alone** — sized here, not fixed, because normalizing it
re-keys 54 stored slugs and their cache keys and reverses a deliberate decision.
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
# its own branch in parse_posting_target — see the module docstring. The catalog stays closed.
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
    # THE GUARD, and the reason this is not a two-line change. `slug_from_path` skips any
    # segment in workday's `_CHROME_SEGMENTS` — `wday`, `cxs`, `job`, `jobs`, `login`,
    # `details` — and any locale-shaped one, so a tenant whose career site is named any of
    # those has its LOCATION read as the site and mints a company row for a board that does
    # not exist. `jobs` is the case with live evidence (redhat, paypal, brandeis, carrier;
    # 157 URLs in the store, 38 independent), but a site named `Login` or `ab-cd` fails the
    # same way and `split_slug` permits all of them. Refusing on the mismatch keeps an unknown
    # shape raising instead of converging onto a fiction; it is a refusal, NOT a repair, and
    # `posting_identity` tier 2 still mints the wrong slug for these.
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
