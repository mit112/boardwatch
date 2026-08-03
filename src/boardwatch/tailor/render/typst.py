from __future__ import annotations

from pathlib import Path

from boardwatch.tailor.model import Resume
from boardwatch.tailor.render import TypstRunner

_PREAMBLE = (
    '#let resume-header(t) = text(weight: "bold", t)\n'
    '#let resume-education(t) = block(t)\n'
    '#let resume-skills(l, i) = block[#text(weight: "bold")[#l]: #i]\n'
    '#let resume-entry(t) = block(above: 0.8em)[#text(weight: "bold")[#t]]\n'
    '#let resume-bullet(t) = list.item(t)\n'
)


def escape(s: str) -> str:
    return " ".join(s.split()).replace("\\", "\\\\").replace('"', '\\"')


class TypstRenderer:
    def emit(self, resume: Resume, *, reworded: frozenset[str] = frozenset()) -> str:
        lines: list[str] = [_PREAMBLE, '#set document(title: "resume")', ""]
        for h in resume.header:
            lines.append(f'#resume-header("{escape(h)}")')
        for ed in resume.education:
            lines.append(f'#resume-education("{escape(ed)}")')
        for g in resume.skill_groups:
            items = ", ".join(g.items)
            lines.append(f'#resume-skills("{escape(g.label)}", "{escape(items)}")')
        for e in resume.entries:
            lines.append(f'#resume-entry("{escape(e.heading)}")')
            for b in e.bullets:
                # A marker comment, not a payload change — parse_bullets only matches
                # #resume-bullet(...) lines, so this cannot leak into the firewall payload.
                if b.bullet_id in reworded:
                    lines.append("// reworded (Tier B)")
                lines.append(f'#resume-bullet("{escape(b.text)}")')
        return "\n".join(lines) + "\n"

    def to_pdf(
        self, source: str, out_dir: Path, name: str, runner: TypstRunner
    ) -> Path | None:
        out_dir.mkdir(parents=True, exist_ok=True)
        typ = out_dir / f"{name}.typ"
        typ.write_text(source, encoding="utf-8")
        pdf = out_dir / f"{name}.pdf"
        # Both paths are deterministic per posting, so a failed compile after an earlier
        # success would otherwise leave last run's PDF next to this run's .typ.
        pdf.unlink(missing_ok=True)
        return pdf if runner(typ, pdf) and pdf.exists() else None
