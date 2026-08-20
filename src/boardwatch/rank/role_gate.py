"""Title role gate: is this posting a software role at all? (P13, M2.)

Fuzzy title overlap cannot separate roles — Intel's "On Shift (IOS) Technology
Development Engineer" matches the target "iOS Engineer" through the literal "(IOS)"
token — so a categorical gate runs beside the score rather than inside it. The gate
reads the TITLE only: zero-recognized-skills postings were measured to have long
bodies genuinely empty of technical nouns (software-term density 0.50 per 1k chars
vs 0.25 for noise and 3.75 for real targets), so a body-text gate cannot separate
the two populations.

ORDER IS LOAD-BEARING, and it is the whole reason this module exists in this shape.
The deny patterns guard themselves with `\\bX\\b(?!.*\\bsoftware\\b)`, and a negative
lookahead only sees text to the RIGHT of the match. "Software Quality Engineer"
therefore matches `quality engineer`, looks to the right, finds no "software"
(it is on the LEFT) and is vetoed. Evaluating denies first buries 16 unambiguously
software titles this way — Software Test Engineer, Data Warehouse Engineer, Kernel
Driver Engineer, Server Engineer, Software Engineer Merchandising Systems among them.
Evaluating TITLE_SWE_RESCUE first fixes all 16 at zero measured precision cost and
runs 2.3x faster (0.30s vs 0.71s over a 19,262-posting rank), because a software
title short-circuits before any deny pattern is tried:

    rescue -> hard denies -> soft denies (only if no software signal) -> signal -> uncertain

`uncertain` passes through to scoring unchanged. That pass-through is why the gate
retains 100% of the protected population (software-titled postings whose skills the
taxonomy missed): those titles exit at the rescue or signal stage and never meet a
deny pattern. A `not_swe` verdict is never silent — it carries the matched text so
the veto is auditable at `show`, countable in `stats`, and viewable in `top` behind
a flag. A gate you cannot audit is how a real job disappears unnoticed.

Deliberately NOT ported from the donor (job-apps' `TECH_NON_SWE_RE`): its denies for
devops / platform / cloud / ML / SRE / forward-deployed titles. Those are targets
here, and much of the protected population. Only the lookahead IDIOM transferred.

R9 note: this module is listed in `tools/generalization/defaults.py::SCOPED_MODULES`
even though it holds no user preference, because the alternative — moving title data
out of a scoped module to escape the rule — is the evasion R9 exists to catch. The
tuples are therefore built with `tuple(...)` constructor calls, the same documented
escape hatch `heuristic.GENERIC_TITLE_TOKENS` uses for `frozenset(...)`.
"""

from __future__ import annotations

import re
from typing import Literal

RoleVerdict = Literal["swe", "not_swe", "uncertain"]

# Anchored guard: `^(?!...)` makes the lookahead cover the WHOLE title rather than only
# the tail, so a bare business-domain noun can never veto an engineering title from the
# left. Used where a trailing `(?!...)` guard would be blind in the wrong direction.
_NOENG = r"^(?!.*\b(?:engineer|engineering|developer|architect|programmer|swe|sde|sdet)\b).*"

# Non-software engineering and technical disciplines.
_DENY_DISCIPLINE: tuple[str, ...] = tuple([
    r"\b(mechanical|civil|chemical|industrial|aerospace|structural|electrical|process|"
    r"manufacturing|packaging|optical|thermal|materials|metallurg\w*|nuclear|petroleum|"
    # Bare `tooling` dropped (live-run finding): across 7,745 ranked postings its ONLY
    # veto was "iOS Tooling Engineer" — a real iOS job. The rescue cannot save it because
    # `(ios|android|mobile)` there must sit next to engineer/developer, and widening that
    # would un-veto the Intel "(IOS)" row this gate exists to demote.
    r"mining|acoustic\w*|geotechnical|hydraulic|welding|facilities|hvac|"
    r"corrosion|reliability physics|rf|analog|mixed[- ]signal|asic|fpga|silicon|"
    r"semiconductor|photonic\w*|antenna|battery|powertrain|vehicle|flight|propulsion|"
    r"avionics|robotics hardware)\s+(engineer|engineering|technician|designer)\b"
    r"(?!.*\bsoftware\b)",
    r"\bhardware\s+(engineer|design|technician)\b(?!.*\bsoftware\b)",
    r"\bfield\s+(service|application|support)\s+(engineer|technician|specialist)\b",
    r"\bcontrols?\s+(systems?\s+)?engineer\b(?!.*\bsoftware\b)",
    r"\b(sales|solutions?|pre.?sales|customer|technical\s+account)\s+engineer\b"
    r"(?!.*\bsoftware\b)",
    r"\bservice\s+(technician|engineer)\b",
    r"\b(test|validation|verification|quality)\s+(engineer|technician|inspector)\b"
    r"(?!.*\b(software|automation|sdet)\b)",
    # Bare `manufacturing` dropped: marginal veto contribution 0 (every row it caught is
    # caught by the alternation above, `technician`, or `(product|program|project) manager`)
    # and it buried "Software Engineer, Manufacturing Systems".
    r"\bprocess\s+(engineer|technician)\b(?!.*\bsoftware\b)",
    r"\bcad\b|\bsolidworks\b|\bautocad\b",
    r"\bdrafter\b|\bdraftsman\b",
    r"\bsurveyor\b",
    # Bare `on shift` dropped: added for one Intel row, which the next two patterns still
    # veto twice over, so its marginal contribution is 0.
    r"\b(night|day|swing|weekend)\s+shift\b",
    r"\b(fab|wafer|lithograph\w*|etch|module|equipment|yield|packaging)\s+"
    r"(engineer|technician|operator)\b",
    r"\btechnology\s+development\s+engineer\b(?!.*\bsoftware\b)",
])

# Manual trades, operations, logistics, facilities.
_DENY_TRADE: tuple[str, ...] = tuple([
    r"\btechnician\b(?!.*\b(software|devops|platform|sre|developer)\b)",
    r"\bmechanic\b|\bplumber\b|\belectrician\b|\bwelder\b|\bmachinist\b|\bpainter\b",
    r"\bforklift\b|\bjanitor\b|\bcustodian\b|\bhousekeep\w*\b",
    # Bare `warehouse` narrowed: it buried "Data Warehouse Engineer" and "Software
    # Engineer II, Warehouse Automation". Every noise row it caught is a
    # "Warehouse Operations"/"Warehouse Worker" and survives the narrowing.
    r"\bwarehouse\s+(associate|worker|operations?|operative|clerk|selector|"
    r"supervisor|lead|labor\w*)\b",
    # Bare `driver` narrowed: it hard-denied "Kernel Driver Engineer" / "Driver
    # Development Engineer" — device-driver work is a real software family. 0 fires
    # in the eval set, so the narrowing is free.
    r"\b(truck|delivery|cdl|route|shuttle|bus|forklift)\s+drivers?\b|"
    r"\bdrivers?\s*[-–]\s*(cdl|class\s+[ab])\b",
    r"\bassembler\b|\bassembly\s+(operator|associate|technician)\b",
    r"\b(machine|equipment|plant|production|forklift|press|line)\s+operator\b",
    r"\binstaller\b|\blineman\b|\brigger\b|\broofer\b|\blandscap\w*\b",
    # Bare `maintenance` narrowed (0 fires; buried "Software Engineer, Maintenance Platform").
    r"\bmaintenance\s+(technician|mechanic|worker|planner|supervisor|associate|crew)\b",
    r"\bmaterial handler\b|\bpicker\b|\bpacker\b",
    r"\bsecurity\s+(guard|officer)\b",
    r"\bcustodial\b|\bgroundskeep\w*\b",
])

# Clinical, life sciences, care. None of these nouns appear in software titles.
_DENY_CLINICAL: tuple[str, ...] = tuple([
    r"\bnurse\b|\brn\b|\blpn\b|\bcna\b|\bphysician\b|\bsurgeon\b|\bdoctor\b",
    r"\b(physical|occupational|respiratory|speech|behavior\w*)\s+therap\w*\b|\btherapist\b",
    r"\bdental\b|\bhygienist\b|\bpharmac\w*\b|\bphlebotom\w*\b|\bsonograph\w*\b",
    r"\bradiolog\w*\b|\bmedical\s+(assistant|technologist|scribe|coder)\b",
    r"\bpatient\s+(access|care|service)\b|\bcaregiver\b|\bveterinar\w*\b",
    r"\bclinical\s+(specialist|coordinator|research|trial|liaison|educator)\b",
    r"\b(biolog|chemist|geolog|toxicolog|microbiolog|pathol)\w*\b",
    r"\blab(oratory)?\s+(technician|assistant|manager)\b",
])

# Food, retail, hospitality, front desk.
_DENY_SERVICE: tuple[str, ...] = tuple([
    r"\bchef\b|\bcook\b|\bbarista\b|\bbartender\b|\bbaker\b|\bbutcher\b|\bdishwasher\b",
    # Bare `server` narrowed: it vetoed "Server Engineer" / "Server Infrastructure
    # Engineer". `host(ess)?` narrowed to `hostess` (0 fires; "Host Networking Engineer").
    r"\bcashier\b|\breceptionist\b|\bhostess\b",
    r"\b(banquet|food|cocktail|dining|restaurant|bar)\s+servers?\b|\bserver\s+assistant\b",
    # Bare `merchandis*` narrowed: it buried "Software Engineer, Merchandising Systems",
    # and its noise rows are all caught by `sales associate`.
    r"\bsales\s+associate\b|\bstore\s+(manager|associate|lead)\b",
    r"\bmerchandis\w*\s+(associate|specialist|manager|coordinator|planner|lead)\b|"
    r"\bvisual\s+merchandis\w*\b",
    r"\bcrew\s+member\b|\bteam\s+member\b|\bshift\s+(lead|supervisor)\b",
    r"\bguest\s+(service|experience)\b|\bconcierge\b|\bvalet\b|\bflight attendant\b",
    r"\blifeguard\b|\bbarber\b|\bstylist\b",
])

# Business, GTM, people, finance, legal, education, creative — HARD half: the head noun
# re-labels the role no matter what else the title says.
_DENY_BUSINESS_HARD: tuple[str, ...] = tuple([
    # Bare `recruit*` narrowed (buried "Software Engineer, Recruiting Products"); both
    # noise rows are "Technical Recruiter" and survive.
    r"\brecruiter\b|\brecruit(ing|ment)\s+(coordinator|manager|specialist|partner|"
    r"lead|associate|sourcer)\b|\btalent\s+acquisition\b|\bsourcer\b",
    r"\baccount\s+(executive|manager|director)\b|\bsales\s+(development|representative|"
    r"specialist|manager|director|associate)\b|\bbusiness\s+development\b",
    # Bare `tax` narrowed ("Software Engineer, Tax Platform"); bare `controller` narrowed
    # ("Ingress Controller Engineer" is Kubernetes work), its one noise fire survives.
    r"\baccountant\b|\bbookkeeper\b|\bauditor\b|"
    r"\b(financial|assistant|corporate|plant|divisional|legal\s+entity)\s+controller\b|"
    r"\bcontroller\b(?=\s*$)|"
    r"\btax\s+(manager|analyst|accountant|associate|specialist|preparer|counsel|"
    r"director|examiner)\b|\b(income|sales|property|corporate|indirect)\s+tax\b",
    r"\battorney\b|\blawyer\b|\bparalegal\b|\bcounsel\b|\bcompliance\s+(officer|analyst)\b",
    r"\b(marketing|brand|content|social media|seo|growth|communications?|pr)\s+"
    r"(manager|specialist|associate|coordinator|lead|strategist|analyst|director)\b",
    r"\bstrategist\b|\bstrategy\s+(manager|associate|analyst|lead)\b",
    r"\b(product|program|project|engagement|portfolio)\s+manager\b",
    r"\bchief of staff\b|\bexecutive assistant\b|\badministrative assistant\b",
    r"\b(office|facilities|operations)\s+(manager|coordinator|administrator)\b",
    r"\bteacher\b|\bprofessor\b|\btutor\b|\binstructor\b|\bcurriculum\b|\bfaculty\b",
    r"\b(ux|ui|visual|graphic|industrial|product)\s+design(er)?\b",
    r"\bhead\s+of\b|\bchief\b.{0,30}\bofficer\b|\bvice\s+president\b|\bpresident\b",
])

# SOFT half: skipped whenever the title carries any software signal.
_DENY_BUSINESS_SOFT: tuple[str, ...] = tuple([
    r"\bhuman\s+resources\b|\bhr\s+(generalist|business partner|coordinator)\b",
    # Bare `benefits`/`payroll` narrowed — "Software Engineer, Payroll" (Gusto/Rippling)
    # and "Engineer, Benefits Platform" are real software titles.
    r"\bpeople\s+(partner|operations)\b|"
    r"\b(benefits|payroll)\s+(manager|specialist|analyst|administrator|coordinator|"
    r"associate|clerk)\b",
    r"\bcustomer\s+(success|support|service|experience)\b(?!.*\bengineer\b)",
    r"\b(financial|investment|credit|risk|treasury|actuarial)\s+analyst\b",
    # `developer` added to the guard (live-run finding): this pattern's only veto across
    # 7,745 ranked postings was "Consultant Developer (Kotlin + Java)", a real dev job.
    r"\bconsultant\b(?!.*\b(software|developer)\b)",
    r"\bcopywriter\b|\beditor\b|\bjournalist\b|\bvideographer\b|\billustrator\b",
    r"\btechnical\s+writer\b",
    r"\bbusiness\s+(systems?\s+)?analyst\b(?!.*\bengineer\b)",
    # Bare `logistics` narrowed ("Engineer, Logistics Platform"); bare `planner` narrowed
    # (0 marginal; "Engineer, Planner Platform"). The noise rows survive both.
    r"\bsupply\s+chain\b|\bprocurement\b|\bbuyer\b|"
    r"\blogistics\s+(specialist|coordinator|manager|analyst|associate|supervisor|"
    r"planner|clerk)\b|\b(inbound|outbound|reverse)\s+logistics\b|"
    r"\b(demand|supply|material|production|capacity|financial|merchandise)\s+planner\b",
    # Bare `claims`/`loan`/`mortgage` narrowed — "Claims Platform Engineer" (Lemonade)
    # and "Engineer, Loan Origination" are real software titles.
    r"\bunderwrit\w*\b|"
    r"\bclaims\s+(adjuster|examiner|processor|specialist|analyst|representative|"
    r"manager|associate)\b|"
    r"\bloan\s+(officer|processor|originator|servicing|advisor)\b|"
    r"\bmortgage\s+(loan|banker|advisor|underwriter|specialist|consultant)\b|\bbanker\b",
    # Bare `property` narrowed (0 fires; "Property Graph Engineer").
    r"\breal estate\b|\bleasing\b|"
    r"\bproperty\s+(manager|management|accountant|administrator|coordinator)\b",
    # Bare `fellow` narrowed — "Engineering Fellow" is a senior IC software title at
    # several companies, and this pattern's marginal veto contribution is 0.
    r"\b(research|clinical|teaching|postdoctoral|policy|design)\s+fellow\b|"
    r"\bfellowship\b|\bpostdoc\w*\b|\bresearch\s+(scientist|associate|assistant)\b"
    r"(?!.*\b(software|engineer)\b)",
    r"\beconomist\b|\bstatistician\b|\bactuary\b",
    # Bare `portfolio` narrowed ("Engineer, Portfolio Analytics").
    r"\btrader\b|\bportfolio\s+(manager|management|analyst|associate)\b|"
    r"\bquantitative\s+researcher\b",
    # Bare `sales` kept but ANCHOR-guarded: its four real noise rows carry no engineering
    # head noun, so the guard keeps all four while making "Engineer, Sales Systems"
    # unreachable. Bare `retail` dropped outright — marginal contribution 0, and it is
    # exactly the pattern that would veto "Engineer, Retail Systems".
    _NOENG + r"\bsales\b",
    r"\bgtm\b|\bgo.?to.?market\b|\bpre.?sales\b|\bconsult(ing|ancy)\b",
    # Bare `coordinator`, anchor-guarded (D-245). "Disaster Response Coordinator" reached the
    # shortlist on run 61 because it verdicts `uncertain` and the ranker passes `uncertain`
    # through. Measured over 26,997 open postings: 135 flip to not_swe, all non-software, and
    # 0 `swe`-classified titles contain the word, so this cannot bury a software job. The
    # anchored guard additionally spares 4 administrative roles at engineering schools.
    _NOENG + r"\bcoordinator\b",
    # D-252 consistency gaps: the gate already denied "Solutions ENGINEER", "field support
    # engineer", and bare sales, but not these pre-sales / support / non-sales-BD twins. All
    # are in the SOFT lane, so a real "Software Architect" (rescued) or a signalled IC title is
    # never reached; a "Software Solutions Architect" is rescued software-first.
    r"\b(solutions?|enterprise|customer|pre.?sales|sales)\s+architect\b",
    r"\b(business|partner|account|channel|corporate|market|revenue)\s+development\s+"
    r"(representative|rep|manager|associate|executive|director|lead|specialist)\b",
    r"\b(customer|technical|it|desktop|help\s*desk)\s+support\s+engineer\b",
])

# Positive SWE signal on the title. Bare `reliability` is deliberately absent: it made a
# manufacturing "Reliability Engineer" a positive match while `reliability physics` was a
# deny. `site reliability` and `sre` still match, so genuine SRE titles are unaffected.
_TITLE_SWE_SIGNAL = (
    r"\bsoftware\s+(engineer|engineering|developer|development|architect)\w*\b|"
    r"\b(software|application|apps?|systems?|product)\s+development\s+engineer\b|"
    r"\b(web|application|app|api|full[\s-]?stack|fullstack|front[\s-]?end|frontend|"
    r"back[\s-]?end|backend|server[\s-]?side|client[\s-]?side|mobile|ios|android|"
    r"react|node|java|python|golang|rust|c\+\+|embedded software)\s+"
    r"(engineer|developer|programmer|architect)\w*\b|"
    r"\b(devops|sre|site\s+reliability|platform|infrastructure|infra|cloud|"
    r"distributed\s+systems|data|machine\s+learning|ml|ai|applied\s+ai|"
    r"perception|compiler|kernel|firmware|graphics|security|network|"
    r"observability|search|payments|growth|productivity|tools|"
    r"automation|test\s+automation|quality\s+engineering)\s+engineer\w*\b|"
    r"\b(engineer|developer)\s*,?\s*(backend|frontend|full[\s-]?stack|mobile|ios|android|"
    r"platform|infrastructure|distributed\s+systems|api)\b|"
    r"\b(swe|sde|sdet|mts|amts|imts)\b|\bmember\s+of\s+technical\s+staff\b|"
    r"\bsw\s+engineer\w*\b|"
    r"\bprogrammer\b|\bprogrammer\s+analyst\b|"
    r"\bweb\s+develop\w*\b|\bapplication\s+develop\w*\b|"
    r"\bnew\s+grad\w*\b.{0,30}\b(engineer|developer)\b|"
    r"\b(engineer|developer)\b.{0,20}\bnew\s+grad\w*\b|"
    r"\bcomputer\s+scientist\b|\bresearch\s+engineer\b|\bforward\s+deployed\s+engineer\b"
)

# Broad rescue: the title reads software-first, so every deny is skipped. Evaluated FIRST.
_TITLE_SWE_RESCUE = (
    r"\bsoftware\b.{0,40}\b(engineer|developer|development|architect)\w*\b|"
    r"\b(sde|swe|sdet)\b|"
    r"\b(full[\s-]?stack|fullstack|front[\s-]?end|frontend|back[\s-]?end|backend)\b|"
    r"\b(ios|android|mobile)\s+(engineer|developer)\b|"
    r"\bweb\s+develop\w*\b|\bapplication\s+develop\w*\b|"
    r"\b(devops|sre|site\s+reliability)\b"
)

# Compiled once at import: the gate runs per posting over a full rank.
_RESCUE = re.compile(_TITLE_SWE_RESCUE, re.IGNORECASE)
_SIGNAL = re.compile(_TITLE_SWE_SIGNAL, re.IGNORECASE)
_DENY_HARD = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in _DENY_DISCIPLINE
    + _DENY_TRADE
    + _DENY_CLINICAL
    + _DENY_SERVICE
    + _DENY_BUSINESS_HARD
)
_DENY_SOFT = tuple(re.compile(pattern, re.IGNORECASE) for pattern in _DENY_BUSINESS_SOFT)


def role_verdict(title: str) -> tuple[RoleVerdict, str]:
    """Classify a posting TITLE as a software role, not one, or unknown.

    Returns the verdict and a one-line reason naming the text that decided it, so a
    `not_swe` veto can always be audited against the posting it hid.
    """
    rescue = _RESCUE.search(title)
    if rescue is not None:  # software-first title: every deny below is skipped
        return "swe", f'software title (matched "{rescue.group(0)}")'
    for pattern in _DENY_HARD:
        hard = pattern.search(title)
        if hard is not None:
            return "not_swe", f'not software (matched "{hard.group(0)}")'
    signal = _SIGNAL.search(title)
    if signal is None:
        # Soft denies apply only to titles with no software signal at all.
        for pattern in _DENY_SOFT:
            soft = pattern.search(title)
            if soft is not None:
                return "not_swe", f'not software (matched "{soft.group(0)}")'
        return "uncertain", "no role signal in title"
    return "swe", f'software title (matched "{signal.group(0)}")'
