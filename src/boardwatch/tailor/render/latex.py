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


def _word_token_pattern(token: str) -> re.Pattern[str]:
    # Mirrors resume_gate._word_token_pattern: a hyphen does not count as a word boundary
    # either, so a word-like token glued into a hyphenated compound is not a false hit.
    return re.compile(rf"(?<![\w-]){re.escape(token)}(?![\w-])", re.IGNORECASE)


class TemplateArtifactError(RuntimeError):
    """Raised when a resolved LaTeX template still carries a leftover authoring placeholder:
    a standalone TODO/FIXME/lorem/ipsum/XXX token, a literal `<placeholder>`, or a `%%..%%`
    marker outside the closed TITLE/SUMMARY/SECTIONS catalog. Deliberately does NOT scan for
    `{{`/`}}` — real LaTeX macro bodies legitimately produce `}}` (e.g.
    `\\hbox{\\tiny$\\bullet$}}`), so scanning them would false-positive on a valid template."""


def _validate_template(text: str) -> None:
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


def resolve_template(config_dir: Path | None) -> str:
    """`{config_dir}/resume_template.tex` when present, else the bundled default. Either way,
    the resolved text is validated before it's handed back (Major-4 guard: the header/education
    are template-hardcoded and never pass through the model's `layout_scan_fields`)."""
    if config_dir is not None:
        candidate = config_dir / "resume_template.tex"
        if candidate.is_file():
            text = candidate.read_text(encoding="utf-8")
            _validate_template(text)
            return text
    text = files("boardwatch.tailor.render.templates").joinpath("resume_base.tex").read_text(
        encoding="utf-8"
    )
    _validate_template(text)
    return text


# --- section emitters ---------------------------------------------------------------------


def _subheading(e: Entry) -> str:
    # Fallback FIRST, before kind routing (Blocker-2 fix): a heading-only entry has no
    # structured title, so escaping e.title here would be escape(None). Degraded but valid.
    if e.title is None:
        return f"\\resumeSubheading{{{escape(e.heading)}}}{{}}{{}}{{}}"
    if e.kind == "project":
        # Compose arg 1 from only the non-empty segments, joined by ` $|$ `: the bold name, the
        # italic tech list (omitted when blank — an empty `\emph{}` would leave a stray `$|$`), and
        # a clickable link when present. The URL is emitted VERBATIM (never escape()d — escaping
        # would corrupt it); the label is display text and is escaped. URLs containing LaTeX
        # specials (#, %, &, _, ~) are not handled — acceptable because the project URLs here
        # (github.com/…, apps.apple.com/…) contain none.
        segments = [f"\\textbf{{{escape(e.title)}}}"]
        if e.subtitle:
            segments.append(f"\\emph{{{escape(e.subtitle)}}}")
        if e.link_url is not None:
            label = escape(e.link_label or "")
            segments.append(f"\\href{{{e.link_url}}}{{\\underline{{{label}}}}}")
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
    lines: list[str] = []
    for b in e.bullets:
        if b.bullet_id in reworded:
            # A marker comment, not a payload change: parse_bullets only matches
            # \resumeItem{...}, so this is invisible to both the PDF and the firewall.
            lines.append("% reworded (Tier B)")
        lines.append(f"\\resumeItem{{{escape(b.text)}}}")
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
    `LatexRenderer()` with no config must work standalone)."""

    def __init__(self, config_dir: Path | None = None) -> None:
        self._config_dir = config_dir

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
        out_lines: list[str] = []
        in_title = False
        for line in template.splitlines():
            stripped = line.strip()
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
