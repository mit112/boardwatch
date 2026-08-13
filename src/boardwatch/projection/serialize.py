"""`Resume` → YAML bytes that `tailor.load.load_resume` reads back as the same document.

There was no such function before this. `Resume` is load-only today: the only two serialization
sites (`reports/tailor.py`) call `model_dump_json()` to SHA-256 the model for content addressing,
and `scaffold_template()` writes a static string constant. So this is the one place the projected
document's bytes are decided.

`profile_bundle.yaml_writer.document_bytes` — the restricted-loader-safe emitter used by the
canonical bundle — is deliberately NOT used here. That module exists because the bundle's loader
narrows YAML 1.1's implicit scalars to a stricter grammar than PyYAML's own resolver, so a stock
`yaml.safe_dump` can emit documents the *bundle's* loader refuses. `load_resume`
(`tailor/load.py`) has no such restriction: it calls plain `yaml.safe_load`, whose implicit
scalar resolution is exactly the one `yaml.safe_dump` writes against. Routing through the bundle's
emitter here would import a module that solves a problem this loader does not have, for a
package `src/boardwatch/projection/` must not depend on regardless.

The mapping carries EXACTLY the keys `load_resume` reads, in `Resume`'s own field order
(`model_dump`'s order, preserved with `sort_keys=False` so the document reads the way the model is
declared). `exclude_none=True` drops unset optional fields (`Entry.title`, `.dates`, `.subtitle`,
`.location`; `Resume.title`) instead of emitting `null` for them — `load_resume` treats a missing
key and an explicit `null` identically (both validate to `None`), so this is a readability choice,
not a correctness one. No provenance comment: `load_resume` calls `yaml.safe_load`, which discards
comments, so a comment could never reach the artifact ledger anyway — provenance is the projection
manifest's job, not this file's.

`width` is set far past any realistic line length so PyYAML never folds a long plain scalar across
multiple physical lines. Folding is lossless for ordinary text (`load_resume` would unfold it back
to the same string), but a document whose on-disk shape depends on where an 80-column boundary
landed is one a reviewer cannot diff cleanly — the same reason `profile_bundle.yaml_writer` widens
it, restated here because that module is not imported.

There is no float/tuple/non-string-key refusal here, unlike the bundle's general-purpose emitter:
every field `Resume.model_dump(mode="json")` can produce is a `str`, `list[str]`, `None`, or a
mapping built from those, so that failure mode does not exist for this model and a defensive check
against it would be dead code.
"""

from __future__ import annotations

from typing import Final

import yaml

from boardwatch.tailor.model import Resume

#: Wide enough that PyYAML never wraps a plain scalar onto a second physical line.
_UNWRAPPED: Final = 1 << 30


def resume_document_bytes(resume: Resume) -> bytes:
    """The projected document's bytes: `load_resume(path)` on this output equals `resume`."""
    payload = resume.model_dump(mode="json", exclude_none=True)
    return yaml.safe_dump(
        payload,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
        width=_UNWRAPPED,
    ).encode("utf-8")


__all__ = ["resume_document_bytes"]
