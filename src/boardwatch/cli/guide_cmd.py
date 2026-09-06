"""`boardwatch guide` and `boardwatch skill` — the instructions a coding agent drives this CLI by.

The guide is GENERATED from the command tree the installed program actually has. `render_guide`
walks the Typer app, and for every leaf command it prints the command's usage line, its own help,
and the entry written for it in `ENTRIES` below — what the command touches (`effects`) and what an
agent has to know before typing it. A command with no entry fails `tests/unit/test_guide_cmd.py`
by name, and so does an entry naming a command that no longer exists, so the guide can never
describe a command this copy of boardwatch does not have, and never omits one it does.

The effect labels are the reason this file exists. Nothing in this CLI is read-only except the
offline commands: any command that opens the store through the default context first applies every
pending schema migration (`cli/context.py:build_context` calls `ensure_schema`), `show`/`stats`/
`export` backfill extractions and verdicts on the way to their readout, `top` records a run even
with `--no-record`, and `doctor` writes board health. An agent that inspects a live store by
running "the show command" changes that store. The guide says so per command, and `migrates`
derives the migration half from each command's own source so the label cannot drift from the code.

`boardwatch skill` prints the short file an agent saves in its own skills folder. It names one
command, `boardwatch guide`, and carries `SKILL_VERSION`; `guide --skill <n>` opens with a notice
when the saved copy is older than the one this program ships. Raise `SKILL_VERSION` by one, by hand,
whenever `SKILL_TEXT` changes.
"""

from __future__ import annotations

import inspect
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from typing import cast

import typer
from typer.core import TyperCommand, TyperGroup
from typer.main import get_command

# --------------------------------------------------------------------------------------------
# The short instruction file
# --------------------------------------------------------------------------------------------

SKILL_VERSION = 1

SKILL_TEXT = f"""boardwatch is a self-hosted job radar the person you are working with runs on
their own machine: it fetches postings from employers' official ATS APIs and discovery lanes,
judges each one against the person's profile with rules that quote the posting, and hands them a
ranked shortlist with a tailored résumé PDF per lead. Everything stays on this machine.

You type the commands; the person talks to you. Read every command's output before telling them
what happened, and when a number came from a summary, prefer the per-row report behind it.

Two facts govern every command you run here:

1. Almost no boardwatch command is read-only. Opening the store through a command applies any
   pending schema migration, and several "show" commands write derived rows on the way. To look
   at a store you must not change, read the SQLite file yourself with Python's sqlite3 module in
   `?mode=ro` (never the sqlite3 CLI), or run only the commands the guide marks `pure`.
2. A scheduled `boardwatch run` may be armed on this machine. Do not start `run` or `scan` while
   one is running; the scan lock names the blocking pid when you try.

boardwatch searches, judges, ranks and tailors. It does not fill in or submit applications, and
it will not: say so plainly if the person expects that. Marking a lead applied IS in scope.

This file names one command on purpose, because a copy saved months ago would otherwise describe
a boardwatch that has moved on. Before you run anything else for this person, run
`boardwatch guide --skill {SKILL_VERSION}` and read all of it: it is generated from the commands
this machine actually has.
"""

# --------------------------------------------------------------------------------------------
# What a command touches
# --------------------------------------------------------------------------------------------

EFFECTS: frozenset[str] = frozenset(
    {
        "pure",  # no store, no files written, no network
        "reads store",
        "writes store",
        "writes files",
        "network",
        "llm",  # spends model calls (API key or a Claude subscription seat)
        "sends",  # an external side effect: a message, a webhook, a desktop notification
        "interactive",  # prompts on the terminal; not for an unattended run
    }
)

STORE_EFFECTS = frozenset({"reads store", "writes store"})


@dataclass(frozen=True)
class Entry:
    """One command's guide entry: what it touches, and what to know before typing it."""

    effects: tuple[str, ...]
    text: str


# The parts of the guide that are not about any one command, in the order they print.
SECTIONS: tuple[tuple[str, str], ...] = (
    (
        "overview",
        """boardwatch is a job radar the person you are working with runs on their own machine.
It fetches postings from employers' official ATS APIs (Greenhouse, Lever, Ashby, Workday,
SmartRecruiters, Workable) and from discovery lanes, judges every posting against the person's
profile with rules that quote the exact span of the posting they fired on, ranks what clears,
and hands them a shortlist with a tailored one-page résumé PDF per lead. All of it stays local.

You are the one who types these commands. The person talks to you; you run the commands, read
the whole answer, and tell them what actually happened. Every verdict here carries evidence:
`eligible` names the rule, the profile field and the quoted span; `ineligible` always quotes the
posting; `abstain` means a rule could not decide and is never folded into either neighbour.
Report them as three things, never two.

boardwatch searches, judges, ranks and tailors. It does not fill in or submit applications, and
that is deliberate. Recording that the person applied IS in scope (`track add`), because an
applied role otherwise re-surfaces forever.

Everything below is generated from the commands this copy of boardwatch actually has.""",
    ),
    (
        "journey",
        """The first-run path, in order:

  boardwatch init            pick boards to watch and paste the profile (interactive, once)
  boardwatch scan            fetch the watched boards
  boardwatch top             the ranked shortlist, best first
  boardwatch show <#>        one posting in full, with the eligibility evidence quoted
  boardwatch track add <#>   record an application so the role stops re-surfacing

`boardwatch run` does scan, eligibility, rank, tailor and delivery in one unattended pass; it is
what a scheduler runs every morning. `boardwatch web` is the page the person reviews leads on.""",
    ),
    (
        "store",
        """THE STORE IS WRITTEN BY ALMOST EVERY COMMAND. Read this before "just looking".

Every command whose entry says `reads store` or `writes store` opens the SQLite store through the
default context, and that context applies any pending schema migration before the command runs
(the entries that say "no migration" open it without that step). `show`, `stats` and `export`
backfill extractions and eligibility verdicts on the way to their readout. `top` records a run
and what it surfaced, even with `--no-record`. `doctor` writes board health. So there is no
boardwatch command that inspects a store and leaves it byte-identical, except the ones marked
`pure`.

To look at a store the person must keep pristine — a live store another process is writing, or
one a newer boardwatch owns — do not run a command against it. Read the file yourself:

  python3 -c "import sqlite3; c = sqlite3.connect('file:<path>/boardwatch.db?mode=ro', uri=True)"

Use Python's sqlite3 with `?mode=ro`, never the sqlite3 command-line tool (it fails to open a
store with a live WAL) and never `immutable=1` (it reads stale past the WAL). Two reads are two
snapshots; take counts you will compare in one connection.

`--data-dir <path>` on any command points it at a different store. Tests and experiments belong
in a scratch data dir, never the person's own.""",
    ),
    (
        "json",
        """Commands that hand back rows print one JSON object on standard output when you add
`--json`, and nothing else goes to standard output, so the output can be piped into the next
program. Anything a person needs to read but a pipe must not swallow — preflight notices,
refusals, "nothing tracked yet" — goes to standard error. The commands that take `--json` are
listed as such in their entries below. A command without it prints tables for a person; read
them, do not parse them.

Exit code 0 means the command did what it says. A refusal exits non-zero with its reason on
standard error, and a refusal is not a negative result: confirm a check actually ran before
reading its silence as evidence.""",
    ),
    (
        "unattended",
        """A scheduled `boardwatch run` may be armed on this machine (launchd on macOS). It runs
whatever code and configuration the installed environment points at. Do not start `run` or `scan`
while one is running: the scan lock refuses and names the blocking pid. Do not change eligibility
rules, the profile or the résumé gate casually — each re-keys every stored verdict, and the next
run re-evaluates the whole store once.

`run` may spend model calls (the final-gate judge, résumé tailoring), write PDFs and queue files,
and send notifications when a channel is enabled. Read the run's funnel (`verify`, `stats`,
the run log) rather than the summary line: a stage that reconciles is the evidence.""",
    ),
)

# One entry per leaf command. Keys are the command path with single spaces: `track add`,
# `eligibility policy set`. Nothing here is generated; this is where a person writes what a
# command is for and what it touches.
ENTRIES: dict[str, Entry] = {
    # ---- the journey ------------------------------------------------------------------------
    "init": Entry(
        ("interactive", "writes store", "writes files"),
        """First-run setup. Prompts for the boards to watch, the profile text and the filters,
writes them into the store, and seeds a résumé template into the config dir when none exists
(never overwriting one). Run it with the person at the keyboard, once.""",
    ),
    "scan": Entry(
        ("network", "writes store"),
        """Fetches every watched board (and the enabled discovery lanes) and applies the result to
the store in one transaction per board. Takes the scan lock; a second scan, or a `run`, refuses
and names the pid holding it. `--company` / `--provider` narrow it to one board or one ATS.
Pacing toward third-party hosts is a promise, not a knob: do not run several at once.""",
    ),
    "top": Entry(
        ("writes store",),
        """The ranked shortlist against the profile: eligibility, the role gate, the seniority band,
the hard filters, dedup and the slate cap all applied, each hidden bucket counted and named.
Takes `--json` (rows on stdout). Every `--include-*` flag shows one hidden bucket for audit.
It RECORDS a run and what it surfaced, and `--no-record` still writes a run row, so `top` is not
the way to peek at a store you must not change.""",
    ),
    "show": Entry(
        ("writes store",),
        """One posting in full: the score components, what the role, signal, band and hard-filter
gates made of it, the eligibility audit with every requirement row and its quoted span, then
the body. Takes `--json`. Runs the extraction preflight first, which backfills extraction rows,
so it writes on the way to reading. A closed posting prints without a score.""",
    ),
    "track add": Entry(
        ("writes store",),
        """Records that the person applied to a posting (or `--status` another stage), so the role
and its duplicates stop re-surfacing. `--new-attempt` opens a second application to the same
posting instead of refusing. Do this only when the person says they applied.""",
    ),
    "track status": Entry(
        ("writes store",),
        """Moves one application to a new status, with an optional `--note`, appending to its
ledger.""",
    ),
    "track list": Entry(
        ("reads store",),
        "The funnel, most recently touched first; `--status` narrows to one stage. Takes `--json`.",
    ),
    "track log": Entry(
        ("reads store",),
        "The immutable event ledger of one application. Takes `--json`.",
    ),
    "track import": Entry(
        ("writes store",),
        """Imports applications made elsewhere from a CSV/JSONL, or from a job-apps `_applied/`
folder tree, so those roles stop re-surfacing. ALWAYS run `--dry-run --report <file>` first and
read the per-row report, not the bucket summary: a url that normalises to many postings is
refused as ambiguous, and the summary count cannot show you which row fanned out.""",
    ),
    "run": Entry(
        ("network", "writes store", "writes files", "llm", "sends"),
        """The whole pipeline once — scan, eligibility, rank, the final-gate judge when armed,
résumé projection and tailoring, PDF render, delivery to the queue, notifications — attributing
every row to one run id. This is what the scheduler runs. `--no-scan` skips the fetch;
`--project` renders through the profile bundle; `--out` / `--queue-root` relocate the artifacts.
Never start one beside a running scheduled run. Read the funnel afterwards (`verify`).""",
    ),
    "web": Entry(
        ("writes files", "network"),
        """Serves the review page on loopback only (never another interface) and opens it. It reads
the run's artifacts under `--out-root` and the delivery queue; marking a lead applied from the
page writes the queue. Leave it running only while the person is reviewing.""",
    ),
    "digest": Entry(
        ("writes store",),
        """New, reopened, updated and closed postings since the last digest, then advances the
digest cursor. `--peek` shows the same digest and leaves the cursor where it was.""",
    ),
    "notify": Entry(
        ("writes store", "sends"),
        """Sends the new profile matches since the last notify to every enabled channel (webhook,
desktop) and advances the cursor only when delivery succeeded. `--dry-run` shows what would go
and sends nothing. Ask the person before sending anything on their behalf.""",
    ),
    "export": Entry(
        ("writes store", "writes files"),
        """Every open or tracked posting with its verdict and funnel state, as JSONL (default) or
CSV, to stdout or `--out`. Runs eligibility first so the verdicts are current, which writes
evaluation rows. This is the bulk read path; `top --json` is the ranked one.""",
    ),
    "stats": Entry(
        ("writes store",),
        """One screen of counts: qualified / uncertain / ineligible / unevaluated over `--days`,
and the discovery pipeline with each hidden bucket. Takes `--json`. Runs the preflight first,
so it backfills rows on the way.""",
    ),
    "verify": Entry(
        ("reads store",),
        """Asserts that a run's store rows and its on-disk artifacts agree — every delivered lead
has its PDF, every PDF has its row. `--run <id>` for one run, none for all. This is how a run
is checked; its own summary line is not.""",
    ),
    "doctor": Entry(
        ("network", "writes store"),
        """Connectivity, per-board health and freshness, and database integrity. Despite the name
it WRITES: it probes every board and stores the fresh health, and it reaps stale run rows.
`--offline` skips the network. Never run it as a "baseline" on a store you must not change.""",
    ),
    "coverage": Entry(
        ("reads store",),
        """Per-board discovery coverage: postings held against the board's own stated total, with
the shortfall named. Takes `--json`. Opens the store without migrating (no migration).""",
    ),
    "seeds": Entry(
        ("reads store",),
        """Unresolved lane seeds, split by whether any enabled resolver's catalog could claim them.
Takes `--json` and `--limit`. Opens the store without migrating (no migration).""",
    ),
    "version": Entry(("pure",), "The installed version and the schema revision it expects."),
    "guide": Entry(
        ("pure",),
        """These instructions. `boardwatch guide <command...>` prints one command's part, or one
section by name (overview, journey, store, json, unattended). `--skill <n>` opens with a notice
when your saved skill file is older than the one this program ships.""",
    ),
    "skill": Entry(
        ("pure",),
        """Prints the short instruction file to save in your own skills folder. It writes nothing
anywhere: every agent tool looks in a different folder, and you know where yours looks. Tell
the person before writing it over a copy they already have.""",
    ),
    # ---- boards -----------------------------------------------------------------------------
    "companies add": Entry(
        ("writes store", "network"),
        """Watches a board by `provider:slug` or by its URL. `--verify` fetches it first and refuses
a board that does not answer. A board added here is scanned from the next `scan` on.""",
    ),
    "companies remove": Entry(("writes store",), "Stops watching one board. Its postings stay."),
    "companies list": Entry(
        ("reads store",),
        "Every watched board with its source, health and last success. Takes `--json`.",
    ),
    "companies search": Entry(
        ("pure",),
        """Substring search over the bundled board catalog, offline. Hands back `provider` and
`slug`.""",
    ),
    "companies export": Entry(
        ("reads store",),
        "The person's watches as registry-format YAML, for contributing them back.",
    ),
    "companies import": Entry(
        ("writes store", "network"),
        "Validates registry-format YAML and watches each entry; `--verify` fetches each first.",
    ),
    "companies discover": Entry(
        ("network", "writes files"),
        """Proposes boards from the two public GitHub new-grad lists, for the person to review;
`--out` writes the proposal. Opens the store without migrating (no migration). It watches
nothing by itself: review, then `companies import`.""",
    ),
    "companies discover-grnh": Entry(
        ("reads store", "writes files"),
        """Proposes Greenhouse boards from stored `grnh.se` seeds, for review; `--out` writes the
proposal. Opens the store without migrating (no migration). Watches nothing by itself.""",
    ),
    # ---- configuration ----------------------------------------------------------------------
    "config show": Entry(
        ("pure",),
        """Every setting with its current value, its default and what it affects, secrets shown as
set/unset. Takes `--json`. Reads config.toml only. A key config.toml misspells is silently
ignored by the loader, so read this back after every `config set`.""",
    ),
    "config set": Entry(
        ("writes files", "writes store"),
        """Sets one key in config.toml. Refuses a secret (those go in the environment). It opens
the store through the default context on the way, so it also migrates. Read `config show`
back afterwards: an unknown key is not an error.""",
    ),
    "settings": Entry(("pure",), "The opt-in feature menu and each feature's state."),
    "settings toggle": Entry(
        ("interactive", "writes files"),
        "Flips opt-in features on and off through numbered prompts, writing config.toml.",
    ),
    # ---- profile ----------------------------------------------------------------------------
    "profile show": Entry(
        ("reads store",),
        """The profile row: text, recognised skills, taxonomy version, targets, filters.
Takes `--json`.""",
    ),
    "profile edit": Entry(
        ("interactive", "writes store"),
        "Opens the profile in an editor and re-derives skills on save. Re-keys every verdict.",
    ),
    # ---- eligibility ------------------------------------------------------------------------
    "eligibility facts": Entry(
        ("reads store",),
        """The person's eligibility facts, per family and field, with each unresolved field named.
A missing fact makes every rule that reads it ABSTAIN, forever, on every posting: a 100%
abstain rate on one rule is a missing fact, not conservatism.""",
    ),
    "eligibility facts set": Entry(
        ("writes store",),
        """Sets one fact, e.g. `work_authorization.status citizen`. Values are checked against the
catalog. Changing a fact re-keys every stored verdict; the next run re-evaluates the store.""",
    ),
    "eligibility policy": Entry(
        ("reads store",),
        """Severity per rule family (blocker, preference, ignore) and each family's near-miss
ceiling.""",
    ),
    "eligibility policy set": Entry(
        ("writes store",),
        """Sets one family's severity. A `preference` family can never yield `ineligible`, only a
demotion; `ignore` silences it. This is policy data, not the catalog. Re-keys every verdict.""",
    ),
    "eligibility policy ceiling": Entry(
        ("writes store",),
        """Sets the highest required-years bar that abstains instead of rejecting, per family.
Re-keys every verdict.""",
    ),
    "eligibility run": Entry(
        ("writes store",),
        """Evaluates every open posting with no current-version verdict. Idempotent; `run` does
this too.""",
    ),
    "eligibility summary": Entry(
        ("writes store",),
        """Counts per family and disposition across the funnel, and how many open postings still
lack a verdict. Runs eligibility first, so it writes evaluation rows.""",
    ),
    "eligibility abstain": Entry(
        ("writes store",),
        """Abstain rate for EVERY rule in the catalog, including rules that have never fired. A rule
at 100% is a monitoring failure to report, never a feature. Runs eligibility first.""",
    ),
    "eligibility extract": Entry(
        ("writes store", "llm"),
        """Opt-in LLM-assisted extraction, advisory only, off by default. `--dry-run` spends
nothing.""",
    ),
    "eligibility score": Entry(
        ("reads store",),
        "Precision against the human-verified labeled set in `--worksheet`, the Gate P5 number.",
    ),
    "eligibility label request": Entry(
        ("reads store", "writes files"),
        """Writes an oracle-judge label request for every unlabeled worksheet row. The judging is
done outside boardwatch by a JD-and-facts-only judge; `label apply` takes the verdicts back.""",
    ),
    "eligibility label apply": Entry(
        ("reads store", "writes files"),
        """Writes oracle verdicts back into the worksheet files, preserving every other column.
Opens the store for the settings and worksheet location on the way.""",
    ),
    "eligibility gate request": Entry(
        ("writes store", "writes files"),
        """Builds the final-gate judge request from the ranked shortlist's visible postings, `--top`
of them, to `--out`. Ranks the shortlist first, so it writes like `top`.""",
    ),
    "eligibility gate apply": Entry(
        ("writes store",),
        """Applies final-gate verdicts to the postings' current open versions. A gate `ineligible`
must carry a raw-substring span from the frozen body or it is downgraded to abstain.""",
    ),
    # ---- identities and the ledger ----------------------------------------------------------
    "identities backfill": Entry(
        ("writes store",),
        """Computes and stores the identity of every open posting under the current algorithm.
Re-runnable.""",
    ),
    "identities regroup": Entry(
        ("writes store",),
        """Moves every duplicate posting onto its survivor's canonical job. `--dry-run` reports
only.""",
    ),
    "identities reap": Entry(
        ("writes store",),
        "Deletes identity rows left by a retired algorithm version. Reports without `--apply`.",
    ),
    "identities verify": Entry(
        ("reads store",),
        "Recounts identities by an independent path and fails on any disagreement.",
    ),
    "identities leakage": Entry(
        ("reads store",),
        "Duplicate leakage over `--days` (the Gate P6 number). Takes `--json`.",
    ),
    "ledger show": Entry(
        ("reads store",),
        """Every job the delivery ledger is suppressing, with disposition, reason and whether it
still governs. Takes `--json`. `--stale` shows permanent decisions whose policy stamp is no
longer current; `--expired` includes lapsed and reopened rows.""",
    ),
    "ledger reopen": Entry(
        ("writes store",),
        """Releases decisions (`--job <id>` or every `--stale` one) so those jobs re-enter the
shortlist. A drain reopens dispositions, not verdicts: a reopened job is re-judged by the
current rules, and it can only be delivered again, never un-delivered.""",
    ),
    "postings reparse-bodies": Entry(
        ("writes store",),
        """Re-derives `body_text` from stored raw JSON for `--provider` and records each change as a
revision. Reports without `--apply`. A body change re-keys that posting's verdict.""",
    ),
    # ---- résumé -----------------------------------------------------------------------------
    "tailor init": Entry(
        ("writes files",),
        """Scaffolds the authored résumé YAML in the config dir; refuses to overwrite without
`--force`.""",
    ),
    "tailor validate": Entry(
        ("pure",),
        "Loads the authored résumé and reports entries, bullets and per-bullet skills. No store.",
    ),
    "tailor run": Entry(
        ("writes store", "writes files", "llm"),
        """Tailors the authored résumé against one posting's JD skills and renders it (`--format`),
to `--out`. `--tier-b` adds the LLM rewrite tier when it is enabled; `--dry-run` renders
nothing. Fabrication checks fail SAFE: a rewrite that cannot be grounded falls back to the
static résumé rather than shipping an invented claim.""",
    ),
    "tailor rewrite request": Entry(
        ("writes store", "writes files"),
        """The subscription-tier rewrite handshake, step 1: writes a JD-aware rewrite request for
one posting for an agent (you) to answer. No API key is spent.""",
    ),
    "tailor rewrite screen": Entry(
        ("writes store", "writes files"),
        "Step 2: re-derives each bullet fresh and screens the agent's candidates against it.",
    ),
    "tailor rewrite apply": Entry(
        ("writes store", "writes files"),
        """Step 3: parses the JD-blind judge's verdicts, keeps only candidates that pass the screen
AND are entailed by the profile, and renders. Anything else falls back to the static bullet.""",
    ),
    "resume project": Entry(
        ("writes store", "writes files"),
        """Projects the profile bundle (JD-blind Stage 1), then selects which entries reach the
résumé for `--posting` under `--scorer`, to `--out`. Needs an approved projection
declaration; approval is granted on a terminal and used durably.""",
    ),
    # ---- the profile bundle (files under --bundle; no store) --------------------------------
    "profile-bundle init": Entry(
        ("writes files",),
        "Creates the bundle skeleton and one empty revision-1 draft. Takes `--json`.",
    ),
    "profile-bundle checkout": Entry(
        ("writes files",),
        "Copies the selected revision into a writable draft. Takes `--json`.",
    ),
    "profile-bundle rebase-draft": Entry(
        ("writes files",),
        "Moves a draft onto the selected revision, keeping a deterministic backup. Takes `--json`.",
    ),
    "profile-bundle validate": Entry(
        ("pure",),
        """Validates the selected revision or `--draft` and reports everything every layer found.
Takes `--json` (the deterministic machine report). Writes nothing. Run it after every edit.""",
    ),
    "profile-bundle inspect": Entry(
        ("pure",),
        "One record from the selected revision, with everything that cites it. Takes `--json`.",
    ),
    "profile-bundle inventory": Entry(
        ("pure",),
        "Every draft, revision, approval stamp and blob the bundle holds. Takes `--json`.",
    ),
    "profile-bundle conflicts": Entry(
        ("pure",),
        "The selected revision's conflict groups and which are still open. Takes `--json`.",
    ),
    "profile-bundle migrate": Entry(
        ("pure",),
        """Reports the selected revision's schema state. At schema v1 it writes nothing.
Takes `--json`.""",
    ),
    "profile-bundle import": Entry(
        ("writes files",),
        """Enumerates one approved `--source` (from `--from`) into a draft's import ledger and
revalidates. Sources are the person's own documents; nothing is invented.""",
    ),
    "profile-bundle extract": Entry(
        ("writes files",),
        "Deterministically extracts one source's candidates into the draft's ledger and report.",
    ),
    "profile-bundle promote-candidates": Entry(
        ("writes files",),
        """Promotes one source's imported candidates into entities, facts and grounded skills. Every
skill must be grounded in evidence or authored by the owner at the shell; none is inferred.""",
    ),
    "profile-bundle add-fact": Entry(
        ("writes files",),
        "Writes one new fact, citing `--evidence-id`, into the owning document and revalidates.",
    ),
    "profile-bundle edit-fact": Entry(
        ("writes files",),
        "Corrects one fact by filing a successor that supersedes it, then revalidates.",
    ),
    "profile-bundle add-evidence": Entry(
        ("writes files",),
        """Captures one evidence record into a draft and revalidates. Takes no bundle lock: do not
run two authoring commands against one bundle at the same time.""",
    ),
    "profile-bundle exclude-record": Entry(
        ("writes files",),
        """Excludes one enumerated source record with `--reason` and `--rationale`, then
revalidates.""",
    ),
    "profile-bundle resolve-conflict": Entry(
        ("writes files",),
        "Appends one owner ruling from `--ruling-file` and updates only the group it rules on.",
    ),
    "profile-bundle approve": Entry(
        ("interactive", "writes files"),
        """Records the owner's approval of a draft's exact content. Needs a controlling terminal:
the person types it, not you. A draft edited after approval is no longer approved.""",
    ),
    "profile-bundle approve-projection": Entry(
        ("interactive", "writes files"),
        """Records the owner's approval of the resolved projection declaration. Terminal-only, like
`approve`; the approval is then used durably by `resume project` and `run --project`.""",
    ),
    "profile-bundle promote": Entry(
        ("writes files",),
        "Promotes an approved draft into the next immutable revision and selects it.",
    ),
    "profile-bundle project": Entry(
        ("writes files",),
        "Serialises the JD-blind Stage 1 pool for the owner's review, to `--json` or the terminal.",
    ),
}


# --------------------------------------------------------------------------------------------
# Walking the tree and rendering
# --------------------------------------------------------------------------------------------


def leaf_commands(app: typer.Typer) -> Iterator[tuple[str, TyperCommand | TyperGroup]]:
    """Every runnable command, as (`"track add"`, command), in help order.

    A group whose callback runs on its own (`eligibility facts`, `settings`) is a leaf too: it
    is something a person types and gets an answer from, so it needs an entry.
    """

    def walk(
        command: TyperCommand | TyperGroup, path: list[str]
    ) -> Iterator[tuple[str, TyperCommand | TyperGroup]]:
        if isinstance(command, TyperGroup):
            if path and command.callback is not None and command.invoke_without_command:
                yield " ".join(path), command
            for name in sorted(command.commands):
                yield from walk(
                    cast("TyperCommand | TyperGroup", command.commands[name]), [*path, name]
                )
        else:
            yield " ".join(path), command

    yield from walk(cast(TyperGroup, get_command(app)), [])


def migrates(command: TyperCommand | TyperGroup) -> bool:
    """True when the command opens the store through the default context, which migrates.

    Derived from the callback's own source, so the guide's migration line and the test that
    checks the effect labels both read the code rather than a hand-kept list.
    """
    callback = command.callback
    if callback is None:
        return False
    try:
        source = inspect.getsource(inspect.unwrap(callback))
    except (OSError, TypeError):
        return False
    return "build_context(" in source and "ensure=False" not in source


def _usage(name: str, command: TyperCommand | TyperGroup) -> str:
    pieces = [f"boardwatch {name}".rstrip()]
    for param in command.params:
        if param.name in {"help"}:
            continue
        if param.param_type_name == "argument":
            pieces.append(f"<{param.human_readable_name.lower()}>")
        elif param.opts:
            pieces.append(f"[{param.opts[0]}]")
    return " ".join(pieces)


def _option_lines(command: TyperCommand | TyperGroup) -> list[str]:
    lines: list[str] = []
    for param in command.params:
        help_text = getattr(param, "help", None)
        if param.param_type_name != "option" or not param.opts or not help_text:
            continue
        lines.append(f"    {param.opts[0]:<24} {help_text}")
    return lines


def render_command(name: str, command: TyperCommand | TyperGroup) -> str:
    entry = ENTRIES[name]
    lines = [_usage(name, command)]
    help_text = (command.help or "").strip()
    if help_text:
        lines.append(f"  {help_text.splitlines()[0]}")
    effects = ", ".join(entry.effects)
    if migrates(command):
        effects += " (default context: applies pending schema migrations first)"
    lines.append(f"  effect: {effects}")
    lines.extend(f"  {line}" for line in entry.text.strip().splitlines())
    lines.extend(_option_lines(command))
    return "\n".join(lines)


def render_section(name: str) -> str:
    body = dict(SECTIONS)[name].strip()
    return f"{name.upper()}\n{'-' * len(name)}\n{body}"


def render_guide(app: typer.Typer, parts: list[str] | None = None) -> str:
    """The whole guide, or only the named parts (a section name or a command path)."""
    leaves = dict(leaf_commands(app))
    if parts:
        wanted = " ".join(parts)
        if wanted in dict(SECTIONS):
            return render_section(wanted)
        if wanted in leaves:
            return render_command(wanted, leaves[wanted])
        raise KeyError(wanted)
    blocks = [render_section(name) for name, _ in SECTIONS]
    blocks.append("COMMANDS\n--------")
    blocks.extend(render_command(name, command) for name, command in leaves.items())
    return "\n\n".join(blocks)


def stale_skill_notice(saved: int, newest: int) -> str:
    return (
        f"The copy of the boardwatch skill file you have saved is out of date: you hold version "
        f"{saved} and this boardwatch ships version {newest}. Tell the person their saved copy is "
        f'being replaced, then run "boardwatch skill" and save its output over the old file.'
    )


def guide(
    part: list[str] | None = typer.Argument(  # noqa: B008
        None, help="A command path (`track add`) or a section name to print on its own."
    ),
    skill_version: int | None = typer.Option(
        None, "--skill", help="The version of the skill file you have saved."
    ),
) -> None:
    """Print the agent-facing instructions, generated from this copy's command tree."""
    from boardwatch.cli.app import app

    if skill_version is not None and skill_version < SKILL_VERSION:
        sys.stdout.write(stale_skill_notice(skill_version, SKILL_VERSION) + "\n\n")
    try:
        text = render_guide(app, part)
    except KeyError as exc:
        sys.stderr.write(
            f"no command or section named {exc.args[0]!r}. Run `boardwatch guide` for all.\n"
        )
        raise typer.Exit(code=1) from None
    sys.stdout.write(text + "\n")


def skill() -> None:
    """Print the short skill file for a coding agent to save in its own skills folder."""
    sys.stdout.write(SKILL_TEXT)
