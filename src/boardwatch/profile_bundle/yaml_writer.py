"""The restricted-YAML emitter: the write half of `yaml_loader`'s contract (design §6, §19).

`init` is the first command that writes bundle documents, and `yaml.safe_dump` cannot do it. The
authoring contract narrows YAML 1.1's implicit scalars to nulls, booleans, base-10 integers, and
plain strings that begin with an ASCII letter — so a stock dump of the packaged example emits
documents Boardwatch itself refuses to read. A test discovers that failing subset from the corpus
rather than naming it, so it tracks the example instead of a memory of it.

## The grammar is verified, never restated

This module does **not** carry a second copy of the loader's rules. Restating a grammar is how the
two drift, and this program has already paid for that once: the check that "derived" the locator
rules by rewriting them ended up enforcing a different contract than the emitter it was checking.

So the strategy here is one line of policy — quote every string — followed by *reading the bytes
back through `load_yaml_bytes` and comparing them to the payload*. Anything the loader would
retype, refuse, or silently alter fails at write time, at the file that caused it. That check is
also the reason there is no float branch, no key-type branch, and no reserved-word list: each of
those would be a rule this module believes about the loader, and the loader is right there.

## Why quoting is the policy rather than "quote when ambiguous"

Deciding per scalar means predicting `resolve`'s answer, which is the restatement again. Quoting
unconditionally cannot change a parsed value — a quoted scalar is a string on both sides — and
leaves integers, booleans and nulls untouched because they are not `str`.
"""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any, Final

import yaml

from boardwatch.profile_bundle.errors import ProfileBundleError
from boardwatch.profile_bundle.yaml_loader import load_yaml_bytes

#: Wide enough that PyYAML never wraps a scalar. A fold rewrites the whitespace inside a quoted
#: string, and while YAML defines the unfolding, a document whose bytes depend on where an
#: 80-column boundary landed is one no reviewer can diff.
_UNWRAPPED: Final = 1 << 30


class DocumentEmitError(ProfileBundleError):
    """A payload could not be written as a document this bundle's loader reads back unchanged."""


class _QuotedStringDumper(yaml.SafeDumper):
    """`SafeDumper` with one change: every string is single-quoted."""


def _represent_quoted(dumper: yaml.SafeDumper, value: str) -> yaml.ScalarNode:
    # PyYAML falls back to a double-quoted scalar when single quotes cannot carry the content
    # (a control character, say). Both styles are explicit, so both are outside the implicit
    # resolution the loader narrows, which is the only property being bought here.
    return dumper.represent_scalar("tag:yaml.org,2002:str", value, style="'")


_QuotedStringDumper.add_representer(str, _represent_quoted)


def document_bytes(payload: object, *, logical_path: PurePosixPath) -> bytes:
    """`payload` as YAML bytes that `load_yaml_bytes` reads back as exactly `payload`.

    `logical_path` is required rather than defaulted because it is the only thing that makes a
    failure locatable: an emitter that could not name the document it failed on would report a
    grammar violation with no file attached.
    """
    try:
        raw = yaml.dump(
            payload,
            Dumper=_QuotedStringDumper,
            sort_keys=False,
            allow_unicode=True,
            default_flow_style=False,
            width=_UNWRAPPED,
        ).encode("utf-8")
    except yaml.YAMLError as exc:
        raise DocumentEmitError(f"{logical_path}: cannot be represented as YAML: {exc}") from exc

    try:
        reloaded: Any = load_yaml_bytes(raw, logical_path=logical_path)
    except ProfileBundleError as exc:
        raise DocumentEmitError(
            f"{logical_path}: the emitted document is outside the authoring contract: {exc}"
        ) from exc
    if reloaded != payload:
        raise DocumentEmitError(
            f"{logical_path}: the emitted document reads back as a different value; the payload "
            "holds something YAML cannot carry unchanged"
        )
    return raw


__all__ = ["DocumentEmitError", "document_bytes"]
