"""The inert `header`/`education` shell.

`LatexRenderer.emit` never reads either field — the template hardcodes the contact block
(`resume_base.tex:72-80`) and Education (`:87-93`), and the layout gate says so in its own
docstring. So projecting them cannot change the PDF. But both are REQUIRED on the frozen model with
no default, and `load_resume` additionally rejects a header with no valid email, a blank name line,
or a template artifact — so a document without them is not constructible or loadable at all.
Revision 2 of the design narrowed the scope without sourcing them and made no projected document
constructible.

The shell is therefore copied verbatim from the owner's existing authored résumé:

- model-only — it satisfies the frozen model and the loader, and the renderer still ignores it;
- NOT authoritative for the PDF, which keeps using the template's hardcoded values;
- part of `ProjectionPool.resume` itself, so a shell change IS visible in the projected document
  (`pool.resume.header`/`.education`) and in `resume_document_bytes`'s serialized YAML.

**But `shell_source`'s CONTENT is not covered by any digest in v1.** `projection_digest` hashes
the parsed `ProjectionDeclaration`, which carries `shell_source` as a `Path` — the filename it was
declared with, not the bytes at that path — and `shell_source` lives in `config_dir`, outside the
bundle, so `bundle_digest` cannot see it either. Editing `{config_dir}/master_resume.yaml` changes
`pool.resume.header`/`.education` with no digest moving and no re-approval required. Blast radius
is small — the renderer ignores both fields, so the PDF is unaffected — but `load_resume`'s
validation and the serialized YAML both see whatever the shell says today, unpinned.

This is the one place v1 reads the file it is replacing, and it is transitional: when renderer
ownership of header/education lands, the shell goes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from boardwatch.projection.errors import ProjectionIssue, raise_violation
from boardwatch.tailor.load import ResumeLoadError, validate_master
from boardwatch.tailor.model import Resume


def load_shell(path: Path) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """`(header, education)` from an authored résumé, held to exactly `validate_master`'s
    contact-block and template-artifact contract — the same function `load_resume` calls.

    `load_resume` itself is not the route: it additionally requires `skill_groups` and
    `entries` (no default on the frozen `Resume` model), so it cannot load a shell file that
    carries only `header`/`education`. This builds the minimal `Resume` those two fields
    support and validates it directly, which works identically whether `shell_source` names
    a dedicated header/education file or the owner's full `resume.yaml` (every other key is
    simply ignored). A shell that passed a private check here and failed `load_resume`
    elsewhere would be a document projection called valid and the tailor refused.
    """
    try:
        raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
        payload = raw if isinstance(raw, dict) else {}
        resume = Resume.model_validate(
            {
                "header": payload.get("header"),
                "education": payload.get("education"),
                "skill_groups": [],
                "entries": [],
            }
        )
        validate_master(resume)
    except (OSError, UnicodeDecodeError, yaml.YAMLError, ValidationError, ResumeLoadError) as exc:
        raise_violation(
            ProjectionIssue.SHELL_SOURCE_UNREADABLE,
            f"shell_source is not a valid header/education shell: {exc}",
            where=path.name,
        )
    return tuple(resume.header), tuple(resume.education)
