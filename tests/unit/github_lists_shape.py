"""AUTHORED GitHub new-grad list payloads, generated from the recorded contract.

NOT A CAPTURE. The four real files are 24 MB of a third party's job listings, and the larger of
the two in-scope repos ships no licence at all, so R7 could only admit them with a `provenance`
that obliges a `license` that does not exist. `synthetic` would be a lie. Nothing captured is
committed, here or anywhere -- and R8 independently refuses a second `company_enumeration` at any
path, so the *emitted* candidate file cannot be committed either.

THE OPPOSITE TRAP. An authored fixture proves only what our own code constructs: that is how five
of six providers passed a dereference rule that was wrong. The guard is that nothing below is a
guess. Every key set, every closed vocabulary and every malformed shape traces to a table in
`docs/superpowers/research/2026-08-24-github-lists-contract.md`, and the tests assert the results
against literals written independently in the test file.

WHAT THIS FIXTURE DELIBERATELY DOES NOT PIN: the live record counts. The contract records
18,813 + 1,142 records and 3,776 active, and it also records that the SAME rule read 3,778 active
a few hours earlier while every all-records number reproduced to the digit. An `active` count is a
live quantity; pinning one here would red the gate on somebody else's merge. The counts live in the
contract, behind `REVIEW_BY`.

RECORDED TRAPS THIS FIXTURE DELIBERATELY DOES NOT MODEL, because `discover` reads exactly three
fields -- `active`, `url`, `company_name` -- so everything else is inert with respect to today's code
and a case for it would assert nothing: padded/tabbed `title`, the 37-character `id` with an embedded
backtick, `locations` at its recorded max of 55, `category`'s open vocabulary, and the 19 records that
are inactive AND hidden. **A change that starts reading any of those owes its case here first.**

FOUR CHECKS TODAY'S CORPUS CANNOT EXERCISE, which is the whole reason they are authored here: a
missing `url` key (0 live records), a non-string `url` (0), an empty-host URL (7, all in one source
that could stop carrying them tomorrow), and `active` disagreeing with `is_visible` (1). "0 today"
means inert, not safe.
"""

from __future__ import annotations

# The probe session. Contract and fixture are dated the same day.
from datetime import date
from typing import Any

PROBED = date(2026, 8, 24)
# PROBED + 90, the window `tools/generalization/fixtures.py` uses for the six ATS captures.
REVIEW_BY = date(2026, 11, 22)

# Contract §3. Both are read; neither is written anywhere.
S1_REPO = "SimplifyJobs/New-Grad-Positions"
S2_REPO = "vanshb03/New-Grad-2027"

# Contract §3, verbatim: the two in-scope record shapes. S2 has NO `category` and NO `degrees`,
# and carries a vestigial `season` on a tiny minority. A fixture that models one shape is wrong.
S1_KEYS: frozenset[str] = frozenset({
    "source", "category", "company_name", "id", "title", "active", "date_updated",
    "date_posted", "url", "locations", "company_url", "is_visible", "sponsorship", "degrees",
})
S2_KEYS: frozenset[str] = frozenset({
    "source", "company_name", "id", "title", "active", "date_updated", "date_posted",
    "url", "locations", "company_url", "is_visible", "sponsorship",
})

# Contract §3: closed at exactly four values across all 34,958 records, 98.4% of them `Other`.
SPONSORSHIP_VALUES: tuple[str, ...] = (
    "Other",
    "U.S. Citizenship is Required",
    "Does Not Offer Sponsorship",
    "Offers Sponsorship",
)

# Contract §3: exactly 14 distinct values, the same set in both sources that carry the field.
# The list may REPEAT a value -- recorded max length is 21 against this 14-value vocabulary.
DEGREE_VALUES: tuple[str, ...] = (
    "Bachelor's", "Master's", "PhD", "Associate's", "Certificate", "MBA", "Bootcamp",
    "MD", "JD", "PharmD", "Incomplete", "DO", "DDS", "DVM",
)

# Contract §5 trap 1: exactly 7 records, all in S2, all active, one defect -- a single slash after
# `https:`, so the host is empty. `trexquant` appears twice, differing only by a trailing slash.
# Employer segments are the recorded ones; they are board slugs, not content.
MALFORMED_URLS: tuple[str, ...] = (
    "https:/.workable.com/trexquant/j/A634E0E3F4/",
    "https:/.workable.com/trexquant/j/A634E0E3F4",
    "https:/.workable.com/scitec/j/45B1B9BA15/",
    "https:/.workable.com/qodeworld/j/5718A36818/",
    "https:/.workable.com/qodeworld/j/5E96914ADB",
    "https:/.workable.com/eluvio/j/A349A0D2AF",
    "https:/.workable.com/thorlabs/j/E79FA34ED4",
)

# Contract §5 trap 2. Parses to the slug `embed`, which is ATS chrome and not a board. The board is
# named by the `token` query parameter, which identifies a JOB. Kept because a fixture of only
# well-formed URLs cannot fail the test that a candidate carries the evidence a reviewer needs.
EMBED_URL = "https://boards.greenhouse.io/embed/job_app?token=6099883"

# Contract §5 trap 5: real hosts on providers we serve, lost to a hostname gap. Both are
# `UnknownBoardURL` today and both are provider host-map changes, so neither is this change's.
EU_GREENHOUSE_URL = "https://job-boards.eu.greenhouse.io/eucompany/jobs/4012345"
MYWORKDAYSITE_URL = "https://acme90.wd5.myworkdaysite.com/en-US/Careers/job/Engineer_R1"

# Contract §5 trap 3: percent-encoded, and whether ashby's API takes the encoded or the decoded
# form is NOT something the probe established. Unresolved on purpose.
ENCODED_ASHBY_URL = "https://jobs.ashbyhq.com/Flock%20Safety/44ae4912-89d9-4e83-840d-e22250d669"

# Contract §5 trap 6: there is no CJK in any of the 34,958 records. The recorded non-ASCII is
# U+2013 EN DASH, curly quotes, one U+2011 non-breaking hyphen, and one accented employer name.
EN_DASH = "–"
ACCENTED_NAME = "AtkinsRéalis"

_EPOCH = 1767841111  # contract §3: epoch SECONDS, always an int, never a string


# ---------------------------------------------------------------------------------------
# The board plan. One row per board the authored corpus names, in no meaningful order --
# the client is what imposes an order, so a fixture ordered by provider would hide a
# stratification bug by handing the code an already-sorted input.
# ---------------------------------------------------------------------------------------

# (provider, expected slug, employer, url template with one {n}, records, which source)
BOARD_PLAN: tuple[tuple[str, str, str, str, int, str], ...] = (
    ("workday", "acme01.wd1.myworkdayjobs.com/acme01/Careers", "Acme 01",
     "https://acme01.wd1.myworkdayjobs.com/en-US/Careers/job/Austin-TX/Engineer_R{n}", 3, "S1"),
    ("greenhouse", "acme02", "Acme 02",
     "https://job-boards.greenhouse.io/acme02/jobs/40{n}", 2, "S1"),
    ("smartrecruiters", "acme03", "Acme 03",
     "https://jobs.smartrecruiters.com/Acme03/744000000000{n}-software-engineer", 1, "S1"),
    ("ashby", "acme04", "Acme 04",
     "https://jobs.ashbyhq.com/acme04/1ef2b1c4-0000-4000-8000-00000000000{n}/application", 1, "S1"),
    ("lever", "acme05", "Acme 05",
     "https://jobs.lever.co/acme05/1a2b3c4d-0000-4000-8000-00000000000{n}", 2, "S2"),
    ("workable", "acme06", "Acme 06",
     "https://apply.workable.com/acme06/j/ABCDEF123{n}/", 1, "S1"),
    ("greenhouse", "acme07", "Acme 07",
     "https://boards.greenhouse.io/acme07/jobs/40{n}", 1, "S2"),
    ("workday", "acme08.wd3.myworkdayjobs.com/acme08/search", "Acme 08",
     "https://acme08.wd3.myworkdayjobs.com/search/job/Boston-MA/Engineer_R{n}", 1, "S1"),
    ("ashby", "acme09", "Acme 09",
     "https://jobs.ashbyhq.com/acme09/1ef2b1c4-0000-4000-8000-00000000010{n}", 1, "S2"),
    ("greenhouse", "acme10", "Acme 10",
     "https://job-boards.greenhouse.io/acme10/jobs/41{n}", 1, "S1"),
    ("lever", "acme11", "Acme 11",
     "https://jobs.lever.co/acme11/1a2b3c4d-0000-4000-8000-00000000011{n}/apply", 1, "S1"),
    ("smartrecruiters", "acme12", "Acme 12",
     "https://jobs.smartrecruiters.com/acme12/744000000001{n}-engineer", 1, "S2"),
    ("workday", "acme13.wd5.myworkdayjobs.com/acme13/External", "Acme 13",
     "https://acme13.wd5.myworkdayjobs.com/en-US/External/job/Remote/Engineer_R{n}", 2, "S1"),
    ("workable", "acme14", "Acme 14",
     "https://apply.workable.com/acme14/j/ABCDEF124{n}", 1, "S2"),
    ("ashby", "acme15", "Acme 15",
     "https://jobs.ashbyhq.com/acme15/1ef2b1c4-0000-4000-8000-00000000015{n}/application", 1, "S1"),
    ("greenhouse", "acme16", "Acme 16",
     "https://job-boards.greenhouse.io/acme16/jobs/42{n}", 1, "S1"),
    ("lever", "acme17", "Acme 17",
     "https://jobs.lever.co/acme17/1a2b3c4d-0000-4000-8000-00000000017{n}", 1, "S2"),
    ("workday", "acme18.wd1.myworkdayjobs.com/acme18/Careers", "Acme 18",
     "https://acme18.wd1.myworkdayjobs.com/Careers/job/Denver-CO/Engineer_R{n}", 1, "S1"),
    ("smartrecruiters", "acme19", "Acme 19",
     "https://jobs.smartrecruiters.com/Acme19/744000000002{n}-engineer", 1, "S1"),
    ("workable", "acme20", "Acme 20",
     "https://apply.workable.com/acme20/j/ABCDEF125{n}/", 1, "S1"),
    ("ashby", "acme21", "Acme 21",
     "https://jobs.ashbyhq.com/acme21/1ef2b1c4-0000-4000-8000-00000000021{n}", 1, "S1"),
    ("workday", "acme22.wd1.myworkdayjobs.com/acme22/Careers", "Acme 22",
     "https://acme22.wd1.myworkdayjobs.com/en-US/Careers/job/NYC/Engineer_R{n}", 1, "S2"),
    ("greenhouse", "acme23", "Acme 23",
     "https://job-boards.greenhouse.io/acme23/jobs/43{n}", 1, "S1"),
    ("lever", "acme24", "Acme 24",
     "https://jobs.lever.co/acme24/1a2b3c4d-0000-4000-8000-00000000024{n}", 1, "S1"),
    ("workday", "acme25.wd3.myworkdayjobs.com/acme25/Careers", "Acme 25",
     "https://acme25.wd3.myworkdayjobs.com/Careers/job/Seattle-WA/Engineer_R{n}", 1, "S1"),
    ("smartrecruiters", "acme26", "Acme 26",
     "https://jobs.smartrecruiters.com/Acme26/744000000003{n}-engineer", 1, "S1"),
    ("workday", "acme27.wd1.myworkdayjobs.com/acme27/Careers", "Acme 27",
     "https://acme27.wd1.myworkdayjobs.com/Careers/job/Reno-NV/Engineer_R{n}", 1, "S1"),
    ("workday", "acme28.wd5.myworkdayjobs.com/acme28/apply", "Acme 28",
     "https://acme28.wd5.myworkdayjobs.com/apply/job/London/Engineer_R{n}", 1, "S1"),
    ("ashby", "acme29", "Acme 29",
     "https://jobs.ashbyhq.com/acme29/1ef2b1c4-0000-4000-8000-00000000029{n}", 1, "S1"),
    ("smartrecruiters", "acme30", "Acme 30",
     "https://jobs.smartrecruiters.com/Acme30/744000000004{n}-engineer", 1, "S1"),
)

# Contract §4: 1,820 of 3,776 in-scope records (48.2%) sit on hosts no provider here serves. Invented,
# except
# where the shape IS the point (the EU-greenhouse and myworkdaysite gaps, above).
UNSERVED_URLS: tuple[str, ...] = (
    "https://careers.acme40.test/jobs/1001",
    "https://acme41.test/careers/apply/2002",
    "https://acme42.icims.test/jobs/3003/software-engineer",
    "https://fa-acme43.fa.oraclecloud.test/hcmUI/CandidateExperience/job/4004",
    EU_GREENHOUSE_URL,
    MYWORKDAYSITE_URL,
)


def _record(
    *,
    shape: str,
    seq: int,
    url: Any,
    employer: str,
    active: bool = True,
    is_visible: bool = True,
    omit_url: bool = False,
    season: bool = False,
    stale_update: bool = False,
) -> dict[str, Any]:
    """One list record in the recorded shape for `shape` ("S1" or "S2").

    `company_url` follows the contract exactly: a `simplify.jobs` profile on S1, and the empty
    string on every S2 record. It names an ATS host on 0 of 3,129 real records, so a reader that
    fell back to it would silently find no board at all.
    """
    common: dict[str, Any] = {
        "source": "Simplify" if shape == "S1" else "vanshb03",
        "company_name": employer,
        "id": f"20fe605e-9125-4857-b077-cf25688899{seq:02d}",
        "title": f"Software Engineer {EN_DASH} New Grad",
        "active": active,
        "date_updated": _EPOCH - 60 if stale_update else _EPOCH,
        "date_posted": _EPOCH,
        "locations": ["Austin, TX"],
        "is_visible": is_visible,
        "sponsorship": SPONSORSHIP_VALUES[seq % len(SPONSORSHIP_VALUES)],
    }
    if not omit_url:
        common["url"] = url
    if shape == "S1":
        common["category"] = "Software"
        common["company_url"] = f"https://simplify.jobs/c/{employer.replace(' ', '')}"
        # Recorded: 29.3% of S1 records carry an EMPTY degrees list, and the list may repeat a value.
        common["degrees"] = [] if seq % 3 == 0 else [DEGREE_VALUES[seq % len(DEGREE_VALUES)]]
    else:
        common["company_url"] = ""
        if season:
            # Recorded on 2 of 1,142 S2 records. An OPTIONAL key, and absence is a missing key
            # rather than a null -- which is true of every field in every source.
            common["season"] = "Summer"
    return common


def listings(shape: str) -> list[dict[str, Any]]:
    """One source's whole file: a BARE JSON ARRAY, no envelope key (contract §3)."""
    records: list[dict[str, Any]] = []
    seq = 0

    for _provider, _slug, employer, template, count, source in BOARD_PLAN:
        if source != shape:
            continue
        for offset in range(count):
            seq += 1
            records.append(_record(
                shape=shape, seq=seq, url=template.format(n=offset + 1), employer=employer,
            ))

    if shape == "S1":
        # Padded employer name, recorded on 114 S1 records. It must be stripped before it reaches
        # `companies.name`: `scan/apply.py` feeds that column into the `cross_host` identity.
        seq += 1
        records.append(_record(
            shape=shape, seq=seq, employer="  Acme 02 Holdings  ",
            url="https://job-boards.greenhouse.io/acme02/jobs/4099",
        ))
        # A board whose ONLY record is padded. Without it the strip is unverifiable: `name` comes
        # from the group's FIRST record, and every other padded record here sits behind a clean one
        # -- so removing `.strip()` left the whole suite green.
        seq += 1
        records.append(_record(
            shape=shape, seq=seq, employer="  Acme 34  ",
            url="https://job-boards.greenhouse.io/acme34/jobs/4446",
        ))
        # The one record that is active while the list itself hides it. 1 live record has this.
        seq += 1
        records.append(_record(
            shape=shape, seq=seq, employer="Acme 31", is_visible=False,
            url="https://job-boards.greenhouse.io/acme31/jobs/4444",
        ))
        # `date_updated` before `date_posted`: 5 live records. Read by nothing here; present so a
        # reader that started ordering on it would have a case that fails.
        seq += 1
        records.append(_record(
            shape=shape, seq=seq, employer="Acme 32", stale_update=True,
            url="https://job-boards.greenhouse.io/acme32/jobs/4445",
        ))
        # ATS chrome that PARSES. Not filtered here; surfaced with its evidence URL instead.
        seq += 1
        records.append(_record(
            shape=shape, seq=seq, employer="Squarepoint Capital", url=EMBED_URL,
        ))
        # Percent-encoded ashby board name; the API's accepted form is unestablished.
        seq += 1
        records.append(_record(shape=shape, seq=seq, employer="Flock Safety", url=ENCODED_ASHBY_URL))
        # An accented employer name -- the real non-ASCII in this corpus. There is no CJK.
        seq += 1
        records.append(_record(
            shape=shape, seq=seq, employer=ACCENTED_NAME,
            url="https://acme33.wd3.myworkdayjobs.com/careers/job/Mississauga/Engineer_R1",
        ))
        # INACTIVE records: 15,668 of S1's 18,813. Filtered out, and counted while filtering.
        for closed in range(4):
            seq += 1
            records.append(_record(
                shape=shape, seq=seq, employer=f"Closed {closed}", active=False,
                url=f"https://job-boards.greenhouse.io/closed{closed}/jobs/9{closed}",
            ))
        # A missing `url` KEY, and a non-string one. Zero live records; both would crash a reader
        # that passed the value straight to `parse_board_target`.
        # A stray bracket makes `urlparse` raise a BARE `ValueError` ("Invalid IPv6 URL"), not
        # `UnknownBoardURL`. Zero live records, one third-party pull request away -- and one of them
        # aborted the entire 19,955-record run before the parse fix.
        seq += 1
        records.append(_record(
            shape=shape, seq=seq, employer="Bracket",
            url="https://job-boards.greenhouse.io]/bracket/jobs/1",
        ))
        seq += 1
        records.append(_record(shape=shape, seq=seq, employer="No URL", url=None, omit_url=True))
        seq += 1
        records.append(_record(shape=shape, seq=seq, employer="Int URL", url=12345))
    else:
        # Recorded on 2 of 1,142.
        for _ in range(2):
            seq += 1
            records.append(_record(
                shape=shape, seq=seq, employer="Acme 05", season=True,
                url="https://jobs.lever.co/acme05/1a2b3c4d-0000-4000-8000-000000000099",
            ))
        # All 7 malformed URLs live in S2, all active.
        for bad in MALFORMED_URLS:
            seq += 1
            records.append(_record(shape=shape, seq=seq, employer="Malformed", url=bad))

    for unserved in UNSERVED_URLS:
        seq += 1
        records.append(_record(
            shape=shape, seq=seq, employer=f"Unserved {seq}", url=unserved,
        ))
    return records
