from __future__ import annotations

import re
from importlib.resources import files
from pathlib import Path

from boardwatch.tailor.model import Entry, Resume
from boardwatch.tailor.render.outcome import CompileOutcome, CompileRunner

# A single regex alternation, applied in ONE pass, so a replacement's own characters are
# never re-scanned and rule ORDER does not matter. (Sequential str.replace is broken here.)
_ESCAPES: tuple[tuple[str, str], ...] = (
    ("\\", r"\textbackslash{}"),
    ("&", r"\&"), ("%", r"\%"), ("$", r"\$"), ("#", r"\#"),
    ("_", r"\_"), ("{", r"\{"), ("}", r"\}"),
    ("~", r"\textasciitilde{}"), ("^", r"\textasciicircum{}"),
)
_ESC_MAP = dict(_ESCAPES)
_ESC_RE = re.compile("|".join(re.escape(k) for k, _ in _ESCAPES))


def escape(s: str) -> str:
    """Collapse whitespace to single spaces (matches the frozen single-line invariant), normalize
    en/em dashes to the LaTeX en-dash `--`, then escape every LaTeX special in ONE pass so tectonic
    compiles the payload verbatim as text.

    Dash normalization is the SINGLE site for it (re-review 2 blocker): model dates/headings carry
    `–`/`—` while the emitter asserts `--`; do it here, not a second time in `_subheading`. `-` is
    not a LaTeX special, so `--` passes through untouched. Note the roundtrip `unescape(escape(x))`
    therefore only returns `x` for dash-free `x` (dash normalization is intentionally lossy — the
    no-fabrication belt in `validate_layout` and the model-level `output_is_entailed` both compare
    escaped-vs-escaped or model-vs-model, so this never masks a fabrication)."""
    collapsed = " ".join(s.split()).replace("—", "--").replace("–", "--")
    return _ESC_RE.sub(lambda m: _ESC_MAP[m.group()], collapsed)


def unescape(s: str) -> str:
    """Inverse of `escape` for `parse_bullets`. Longest replacement first so `\textbackslash{}`
    / `\textasciitilde{}` / `\textasciicircum{}` are restored before the 2-char rules can touch
    their inner braces."""
    out = s
    for raw, esc in sorted(_ESCAPES, key=lambda p: -len(p[1])):
        out = out.replace(esc, raw)
    return out


# --- template resolution + validation ---------------------------------------------------

# Closed catalog of leftover-authoring tells (mirrors resume_gate.TEMPLATE_ARTIFACT_WORDS).
# Symbols/words are inlined here rather than imported from `resume_gate` to avoid a cycle:
# `resume_gate` imports `escape` from this module.
_ARTIFACT_SYMBOL = "<placeholder>"
_ARTIFACT_WORDS: tuple[str, ...] = ("TODO", "FIXME", "lorem", "ipsum", "XXX")
_MARKER_RE = re.compile(r"%%([A-Z]+)_(?:START|END)%%")
_ALLOWED_MARKERS = frozenset({"TITLE", "SUMMARY", "SECTIONS"})
# The last line of any LaTeX preamble, and the only anchor a user's own template is guaranteed
# to carry — deliberately not a `%%..%%` marker, which a config-dir template would not have.
_PREAMBLE_END = "\\begin{document}"

# A sibling catalog to `_ARTIFACT_WORDS` (T2): the bundled `resume_base.tex` header/education is
# literally "Your Name" / "555 555 5555" / "you@example.com" / "Example University" / "Example
# Field" — placeholder identity, not a template mechanism. `emit()` never generates
# `Resume.header`/`Resume.education`; they come ONLY from the template, so a config-dir template
# that is a verbatim, never-edited copy of the bundled default would otherwise pass
# `_validate_template` clean and deliver placeholder identity on a real résumé. These are
# multi-word phrases, not single tokens, so they cannot share `_word_token_pattern`'s word-boundary
# regex — a plain case-insensitive substring match is enough and does not risk a false positive
# the way a single common word might.
_PLACEHOLDER_PHRASES: tuple[str, ...] = (
    "Your Name",
    "you@example.com",
    "555 555 5555",
    "Example University",
    "Example Field",
)


def _word_token_pattern(token: str) -> re.Pattern[str]:
    # Mirrors resume_gate._word_token_pattern: a hyphen does not count as a word boundary
    # either, so a word-like token glued into a hyphenated compound is not a false hit.
    return re.compile(rf"(?<![\w-]){re.escape(token)}(?![\w-])", re.IGNORECASE)


class TemplateArtifactError(RuntimeError):
    """Raised when a resolved LaTeX template still carries a leftover authoring placeholder:
    a standalone TODO/FIXME/lorem/ipsum/XXX token, a literal `<placeholder>`, a `%%..%%`
    marker outside the closed TITLE/SUMMARY/SECTIONS catalog, or (T2) one of the bundled
    template's own header/education phrases copied verbatim into a config-dir template.
    Deliberately does NOT scan for `{{`/`}}` — real LaTeX macro bodies legitimately produce `}}`
    (e.g. `\\hbox{\\tiny$\\bullet$}}`), so scanning them would false-positive on a valid
    template."""


class TemplateMissingError(TemplateArtifactError):
    """Raised by `resolve_template` when `{config_dir}/resume_template.tex` does not exist and
    the caller has not explicitly opted into the bundled default via `allow_bundled_default=True`
    (T2). A subclass of `TemplateArtifactError` rather than a sibling: `run.py`'s
    `FOREIGN_AVAILABILITY` matches `TemplateArtifactError` by `isinstance`, so this maps onto the
    existing `ProjectionAvailability.TEMPLATE_INVALID` member with no new catalog entry."""


def _validate_template(text: str, *, check_placeholder_phrases: bool = True) -> None:
    if _ARTIFACT_SYMBOL in text.lower():
        raise TemplateArtifactError(f"template contains leftover artifact {_ARTIFACT_SYMBOL!r}")
    for word in _ARTIFACT_WORDS:
        if _word_token_pattern(word).search(text):
            raise TemplateArtifactError(f"template contains leftover artifact {word!r}")
    for match in _MARKER_RE.finditer(text):
        if match.group(1) not in _ALLOWED_MARKERS:
            raise TemplateArtifactError(f"template contains unrecognized marker {match.group(0)!r}")
    # SECTIONS is the only load-bearing marker pair: `emit()` injects the résumé body at
    # %%SECTIONS_START%% and relies on %%SECTIONS_END%% surviving untouched. A template
    # missing either one would silently emit zero sections instead of failing loudly.
    if "%%SECTIONS_START%%" not in text or "%%SECTIONS_END%%" not in text:
        raise TemplateArtifactError(
            "template is missing required %%SECTIONS_START%%/%%SECTIONS_END%% markers"
        )
    # `check_placeholder_phrases=False` is for the bundled default ITSELF (`resolve_template`'s
    # own fallback branch): its header/education literally ARE "Your Name" / "Example
    # University" / etc, so scanning it against its own catalog would make the bundled template
    # permanently unloadable. The catalog exists to catch a CONFIG-DIR template that is an
    # unedited copy of that same bundled text — never the bundled text loaded as itself.
    if check_placeholder_phrases:
        lowered = text.lower()
        for phrase in _PLACEHOLDER_PHRASES:
            if phrase.lower() in lowered:
                raise TemplateArtifactError(
                    f"template still carries the bundled placeholder {phrase!r} — edit "
                    "the header/education before using this template"
                )


def resolve_template(config_dir: Path | None, *, allow_bundled_default: bool = False) -> str:
    """`{config_dir}/resume_template.tex` when present, validated and returned.

    T2 (fail-closed default): when `config_dir` is given but carries no `resume_template.tex`,
    this raises `TemplateMissingError` naming the missing path rather than silently falling back
    to the bundled default — the bundled header/education are literally placeholder identity
    ("Your Name", "you@example.com", ...), and `emit()` never generates a header/education of its
    own, so a silent fallback in a real run means a delivered résumé carries someone else's name.
    Pass `allow_bundled_default=True` to opt into the old fallback (tests, previews, examples —
    never a run: both `LatexRenderer` call sites in `projection/run.py` and `reports/tailor.py`
    leave this at its closed default).

    `config_dir=None` (no config dir at all, as opposed to one missing the file) always uses the
    bundled default regardless of `allow_bundled_default` — that is the pre-existing, documented
    "standalone" mode `LatexRenderer()` offers for tests/examples, and no run ever constructs a
    renderer this way.
    """
    if config_dir is not None:
        candidate = config_dir / "resume_template.tex"
        if candidate.is_file():
            text = candidate.read_text(encoding="utf-8")
            _validate_template(text)
            return text
        if not allow_bundled_default:
            raise TemplateMissingError(
                f"no résumé template at {candidate}; a run requires "
                f"{candidate.name!r} in the config dir and never falls back silently"
            )
    text = files("boardwatch.tailor.render.templates").joinpath("resume_base.tex").read_text(
        encoding="utf-8"
    )
    _validate_template(text, check_placeholder_phrases=False)
    return text


# --- section emitters ---------------------------------------------------------------------


def _escape_url(url: str) -> str:
    """Escape the three characters `\\href{}`'s target cannot carry raw, and only those.

    `\\href` normally reads its target verbatim by changing catcodes, but this emitter puts it
    inside `\\resumeProjectHeading{...}` — a macro ARGUMENT, already tokenized by the time
    `\\href` runs — so `&`, `#` and `%` arrive as alignment tab, parameter and comment and kill
    the compile. Killing it PER LEAD, which the tailor stage reports as a run-level fatal
    whose guidance points at bullets.

    Measured with tectonic 0.17 through this emitter, reading the target back out of the PDF:
    `&`, `#`, `%` fail raw and round-trip byte-identical when backslash-escaped; `_`, `~`, `$`
    and `^` round-trip raw, and escaping `$` corrupts it into `\\protect \\TU\\textdollar`. So
    the set is exactly three, not the whole LaTeX-special class. `{`, `}` and `\\` cannot be
    carried either way and are refused before they reach here (`projection/pool.py`).
    """
    for special in "&#%":
        url = url.replace(special, "\\" + special)
    return url


def _href(url: str, label: str) -> str:
    """`\\href{<url>}{\\underline{<label>}}` — the one link rendering, shared by the project
    heading and the first-bullet append. The URL is escaped for the target position only
    (`_escape_url`, which is NOT `escape()` — that would corrupt it); the label is display text
    and is escaped as display text."""
    return f"\\href{{{_escape_url(url)}}}{{\\underline{{{escape(label)}}}}}"


def _subheading(e: Entry) -> str:
    # Fallback FIRST, before kind routing (Blocker-2 fix): a heading-only entry has no
    # structured title, so escaping e.title here would be escape(None). Degraded but valid.
    if e.title is None:
        return f"\\resumeSubheading{{{escape(e.heading)}}}{{}}{{}}{{}}"
    if e.kind == "project":
        # Compose arg 1 from only the non-empty segments, joined by ` $|$ `: the bold name, the
        # italic tech list (omitted when blank — an empty `\emph{}` would leave a stray `$|$`), and
        # a clickable link when present. The URL goes through `_escape_url` (never escape()d —
        # that would corrupt it); the label is display text and is escaped as display text.
        segments = [f"\\textbf{{{escape(e.title)}}}"]
        if e.subtitle:
            segments.append(f"\\emph{{{escape(e.subtitle)}}}")
        # Both-or-neither is enforced on the declaration (`EntryDeclaration`); the guard here is
        # belt-and-suspenders for a directly-constructed `Entry`, and keeps an incomplete link from
        # emitting an empty `\underline{}` rather than shipping an invisible clickable link.
        # `link_in_first_bullet` moves the link onto the first bullet instead (`_bullet_lines`), so
        # the heading drops it when that opt-in is set.
        if e.link_url and e.link_label and not e.link_in_first_bullet:
            segments.append(_href(e.link_url, e.link_label))
        return f"\\resumeProjectHeading{{{' $|$ '.join(segments)}}}{{{escape(e.dates or '')}}}"
    return (
        f"\\resumeSubheading{{{escape(e.title)}}}{{{escape(e.dates or '')}}}"
        f"{{{escape(e.subtitle or '')}}}{{{escape(e.location or '')}}}"
    )


def _skills(resume: Resume) -> str:
    # A résumé with no skill groups omits the section, like `_experience`/`_projects`/
    # `_extracurricular` — otherwise a field whose résumé carries no skills list would render a
    # stray, empty "Skills" header.
    if not resume.skill_groups:
        return ""
    body = "".join(
        f"\\textbf{{{escape(g.label)}}}: {', '.join(escape(item) for item in g.items)}\\\\\n"
        for g in resume.skill_groups
    )
    return (
        "\\section{Skills}\n"
        "\\begin{itemize}[leftmargin=0.15in, label={}]\n\\small{\\item{\n"
        + body
        + "\n}}\n\\end{itemize}\n"
    )


def _bullet_lines(e: Entry, reworded: frozenset[str]) -> str:
    # `link_in_first_bullet` (opt-in) appends the entry's link to the FIRST bullet's text instead
    # of the heading: ` \href{<url>}{\underline{<label>}}`, URL verbatim, label escaped. The
    # append lands on `escape(b.text)` (never re-escaped) and only when both link fields are
    # present — the declaration pairs them, and the guard keeps a half-declared directly-built
    # `Entry` from emitting an empty `\underline{}`. Empty suffix otherwise, so the default path is
    # byte-for-byte unchanged.
    link_suffix = ""
    if e.link_in_first_bullet and e.link_url and e.link_label:
        link_suffix = f" {_href(e.link_url, e.link_label)}"
    lines: list[str] = []
    for index, b in enumerate(e.bullets):
        if b.bullet_id in reworded:
            # A marker comment, not a payload change: parse_bullets only matches
            # \resumeItem{...}, so this is invisible to both the PDF and the firewall.
            lines.append("% reworded (Tier B)")
        text = escape(b.text)
        if index == 0:
            text += link_suffix
        lines.append(f"\\resumeItem{{{text}}}")
    return "\n".join(lines)


def _entry_block(e: Entry, reworded: frozenset[str]) -> list[str]:
    # The subheading always renders; the item list is emitted ONLY when the entry has bullets. An
    # itemize with zero \item is a LaTeX error ("Something's wrong--perhaps a missing \item"), so a
    # bulletless entry (e.g. a projected project whose contribution facts are not yet effective)
    # omits the \resumeItemListStart/End pair — the same guard `_experience`/`_projects` apply at
    # the section level, now applied per entry too.
    lines = [_subheading(e)]
    if e.bullets:
        lines.append("\\resumeItemListStart")
        lines.append(_bullet_lines(e, reworded))
        lines.append("\\resumeItemListEnd")
    return lines


def _entry_section(name: str, entries: list[Entry], kind: str, reworded: frozenset[str]) -> str:
    # An empty \resumeSubHeadingListStart...End (an itemize with zero \item) is a LaTeX error, not
    # a blank section — so a résumé with no entries of this kind must omit the whole section,
    # mirroring `_extracurricular`'s guard.
    matching = [e for e in entries if e.kind == kind]
    if not matching:
        return ""
    lines = [f"\\section{{{name}}}", "\\resumeSubHeadingListStart"]
    for e in matching:
        lines.extend(_entry_block(e, reworded))
    lines.append("\\resumeSubHeadingListEnd")
    return "\n".join(lines) + "\n"


def _experience(entries: list[Entry], reworded: frozenset[str]) -> str:
    return _entry_section("Experience", entries, "experience", reworded)


def _projects(entries: list[Entry], reworded: frozenset[str]) -> str:
    return _entry_section("Projects", entries, "project", reworded)


def _extracurricular(resume: Resume) -> str:
    if not resume.extracurricular:
        return ""
    lines = ["\\section{Extracurricular}", "\\begin{itemize}[leftmargin=0.15in]"]
    for line in resume.extracurricular:
        lines.append(f"\\item \\small{{{escape(line)}}}")
    lines.append("\\end{itemize}")
    return "\n".join(lines) + "\n"


class LatexRenderer:
    """Renders a `Resume` into the resolved LaTeX template's `%%SECTIONS%%` slot and compiles
    it via tectonic. `config_dir=None` uses the bundled default template (re-review 2 minor:
    `LatexRenderer()` with no config must work standalone).

    `pdf_title`/`pdf_author` become the document's /Info `Title` and `Author`. They are given
    per instance rather than per `emit` call because a renderer is already built per lead, and
    because widening the `Renderer` protocol would put the metadata in front of every caller
    that only wants a preview."""

    def __init__(
        self,
        config_dir: Path | None = None,
        *,
        pdf_title: str | None = None,
        pdf_author: str | None = None,
    ) -> None:
        self._config_dir = config_dir
        self._pdf_title = pdf_title
        self._pdf_author = pdf_author

    def emit(self, resume: Resume, *, reworded: frozenset[str] = frozenset()) -> str:
        template = resolve_template(self._config_dir)
        sections = (
            _skills(resume)
            + _experience(resume.entries, reworded)
            + _projects(resume.entries, reworded)
            + _extracurricular(resume)
        )
        # The persona headline (P4 item 7): a single escaped line, styled to match the
        # template's centered name header. None when the résumé carries no persona title.
        title_line = (
            f"    {{\\small \\scshape {escape(resume.title)}}} \\\\ \\vspace{{2pt}}"
            if resume.title
            else None
        )
        # SECTIONS: mirrors build_resume.sh's awk insertion — on the START marker line, print
        # it, then the section body, then fall through to the untouched END marker line. Both
        # SECTIONS markers survive in the output; only the region between them changes.
        #
        # TITLE differs deliberately: its marker PAIR is consumed, never echoed, so no
        # `%%TITLE_*%%` token can survive into the .tex. When the résumé has a title the
        # escaped headline replaces the pair; when it does not (or a custom template omits the
        # pair) the slot degrades to nothing — no crash, no title, no stray marker.
        metadata = self._pdf_metadata()
        out_lines: list[str] = []
        in_title = False
        for line in template.splitlines():
            stripped = line.strip()
            if metadata and stripped == _PREAMBLE_END:
                out_lines.extend(metadata)
            if stripped == "%%TITLE_START%%":
                in_title = True
                if title_line is not None:
                    out_lines.append(title_line)
                continue
            if stripped == "%%TITLE_END%%":
                in_title = False
                continue
            if in_title:
                continue  # drop any placeholder content between the TITLE markers
            out_lines.append(line)
            if stripped == "%%SECTIONS_START%%":
                out_lines.extend(sections.splitlines())
        return "\n".join(out_lines) + "\n"

    def _pdf_metadata(self) -> list[str]:
        """The `\\hypersetup` block for the document's /Info Title and Author, or no lines.

        **Injected here rather than written into the bundled template.** A template-side fix would
        be shadowed the moment a user installs their own `resume_template.tex`, which is exactly
        the configuration this ships into. `\\begin{document}` is the anchor because it is the one
        line every template is guaranteed to carry, and the block goes immediately BEFORE it: that
        is where hyperref's own documentation puts the PDF-info keys, and where drivers that read
        them at `\\begin{document}` still see them. Measured under this toolchain (tectonic/XeTeX)
        the keys also survive from just after `\\begin{document}`, so the position is a portability
        choice rather than a necessity — and it is pinned by a test so it cannot drift silently.

        `\\providecommand` first, so a template that never loads hyperref loses the metadata
        instead of failing to compile — a failed compile costs the owner the lead (P1a), and
        losing a /Info key costs nothing that matters.

        `escape` is this module's one escaping helper and it is sufficient here: measured
        through tectonic, every sequence it produces — `\\&` `\\%` `\\_` `\\#` `\\$` `\\{` `\\}`
        `\\textasciitilde{}` `\\textasciicircum{}` `\\textbackslash{}` — round-trips through
        hyperref's `\\pdfstringdef` into /Info verbatim, and non-ASCII survives as itself. Its
        whitespace collapse and en-dash normalization apply to the metadata too, which is
        wanted: a scraped employer name can carry newlines.
        """
        keys = [
            f"pdf{key}={{{escape(value)}}}"
            for key, value in (("title", self._pdf_title), ("author", self._pdf_author))
            if value
        ]
        if not keys:
            return []
        return ["\\providecommand{\\hypersetup}[1]{}", f"\\hypersetup{{{','.join(keys)}}}"]

    def to_pdf(
        self, source: str, out_dir: Path, name: str, runner: CompileRunner
    ) -> CompileOutcome:
        out_dir.mkdir(parents=True, exist_ok=True)
        tex = out_dir / f"{name}.tex"
        tex.write_text(source, encoding="utf-8")
        pdf = out_dir / f"{name}.pdf"
        # Both paths are deterministic per posting, so a failed compile after an earlier
        # success would otherwise leave last run's PDF next to this run's .tex.
        pdf.unlink(missing_ok=True)
        return runner(tex, pdf)
