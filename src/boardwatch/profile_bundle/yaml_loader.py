"""The one restricted YAML loader for bundle documents (design §7).

Nothing else in this package may call `yaml.safe_load`. `SafeLoader` implements YAML 1.1's
implicit scalars, and every one of them is a silent type change in a knowledge base:

- `no`, `off`, `n` become `False`, so a skill named "No-SQL" or a status word becomes a boolean;
- `2026-08-10` becomes a `datetime.date` before Pydantic sees it, and `2026-08-10T12:00:00Z`
  becomes a `datetime`, so the authoring contract's "dates are quoted strings" is unenforceable;
- `01` becomes octal `1`, and `1_000` becomes `1000`;
- `1.5`, `.inf`, and `.nan` become floats, which the canonical serializer cannot hash
  reproducibly and `json.dumps(allow_nan=False)` refuses outright.

An out-of-contract plain scalar is REFUSED rather than stringified. Stringifying it would make
`expires_at: 2026-08-10` parse cleanly while quietly disagreeing with the contract, and the author
would never find out. Quoting is the documented escape hatch and is tested as such.

Anchors, aliases, and merge keys are refused wholesale: they make one logical record expressible
in two byte sequences, which is exactly what content addressing must not have to reason about.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Any, Final, cast

import yaml
from yaml.nodes import MappingNode, Node, ScalarNode

from boardwatch.profile_bundle.errors import IssueCode, ProfileBundleError, RestrictedYamlError

_STR_TAG: Final = "tag:yaml.org,2002:str"
_NULL_TAG: Final = "tag:yaml.org,2002:null"
_BOOL_TAG: Final = "tag:yaml.org,2002:bool"
_INT_TAG: Final = "tag:yaml.org,2002:int"

#: Exactly base-10, optional sign, no leading zeroes beyond a bare `0`, no underscores.
_INT_RE: Final = re.compile(r"^[-+]?(?:0|[1-9][0-9]*)$")
#: Unquoted strings are identifiers or prose beginning with an ASCII letter or underscore.
#: Numeric-looking strings, punctuation-leading prose, dates, digests, and free-form captures use
#: YAML's quoted-string escape hatch instead of growing a blocklist of ambiguous spellings.
_PLAIN_STRING_RE: Final = re.compile(r"^[A-Za-z_][^\r\n]*$")

_ACCEPTED_NULL: Final = frozenset({"", "null", "~"})
_ACCEPTED_BOOL: Final = frozenset({"true", "false"})


class CareerProfileLoader(yaml.SafeLoader):
    """`SafeLoader` narrowed to the bundle's authoring contract.

    The narrowing happens in `resolve`, which is the single place PyYAML decides what an
    unquoted scalar means. Overriding it — rather than deleting entries from
    `yaml_implicit_resolvers` — keeps the stock table available as the definition of "this scalar
    is ambiguous", which is what lets the loader refuse instead of guessing.
    """

    # `types-PyYAML` leaves `Resolver.resolve`, `Composer.compose_node`, `check_event` and
    # `peek_event` untyped, so every call into them needs an explicit ignore. They are marked
    # individually rather than silenced module-wide: a future stub release should make each one
    # fail as unused, which is the signal to delete it.

    def resolve(self, kind: type[Node], value: Any, implicit: Any) -> str:
        if kind is ScalarNode and implicit and implicit[0] and isinstance(value, str):
            return self._strict_scalar_tag(value)
        resolved = super().resolve(kind, value, implicit)  # type: ignore[no-untyped-call]
        return cast(str, resolved)

    def _strict_scalar_tag(self, value: str) -> str:
        if value in _ACCEPTED_NULL:
            return _NULL_TAG
        if value in _ACCEPTED_BOOL:
            return _BOOL_TAG
        if _INT_RE.match(value):
            return _INT_TAG
        stock = cast(
            str,
            super().resolve(ScalarNode, value, (True, False)),  # type: ignore[no-untyped-call]
        )
        if stock != _STR_TAG:
            raise RestrictedYamlError(
                IssueCode.RESTRICTED_YAML_VIOLATION,
                f"plain scalar {value!r} would be read as {stock.rsplit(':', 1)[-1]!r} under "
                "YAML 1.1; the authoring contract requires it quoted, or written as `true`, "
                "`false`, `null`, or a base-10 integer"
            )
        if not _PLAIN_STRING_RE.fullmatch(value):
            raise RestrictedYamlError(
                IssueCode.RESTRICTED_YAML_VIOLATION,
                f"plain scalar {value!r} is outside the plain-string grammar; quote it or start "
                "it with an ASCII letter or underscore"
            )
        return _STR_TAG

    def compose_node(self, parent: Node | None, index: Any) -> Node | None:
        if self.check_event(yaml.events.AliasEvent):  # type: ignore[no-untyped-call]
            raise RestrictedYamlError(
                IssueCode.RESTRICTED_YAML_VIOLATION,
                "YAML aliases are not permitted: one record must have one byte sequence"
            )
        event = self.peek_event()  # type: ignore[no-untyped-call]
        tag = getattr(event, "tag", None)
        if tag is not None:
            raise RestrictedYamlError(
                IssueCode.RESTRICTED_YAML_VIOLATION,
                f"explicit YAML tag {tag!r} is not permitted: the restricted loader alone "
                "decides scalar and collection types"
            )
        anchor = getattr(event, "anchor", None)
        if anchor is not None:
            raise RestrictedYamlError(
                IssueCode.RESTRICTED_YAML_VIOLATION,
                f"YAML anchor {anchor!r} is not permitted: an anchor is the first half of an alias"
            )
        return super().compose_node(parent, index)

    def construct_mapping(self, node: MappingNode, deep: bool = False) -> dict[Any, Any]:
        """Reject duplicate and non-string keys before the mapping exists.

        `SafeConstructor` keeps the last duplicate silently, so `a: 1` / `a: 2` parses to `{a: 2}`
        and a reviewer reading the diff sees both lines. A non-string key is refused because
        canonical JSON stringifies keys: `{1: x}` and `{"1": x}` would hash identically.
        """
        seen: set[Any] = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=True)
            if not isinstance(key, str):
                raise RestrictedYamlError(
                    IssueCode.RESTRICTED_YAML_VIOLATION,
                    f"mapping key {key!r} is not a string; canonical JSON stringifies keys, so a "
                    "non-string key would collide with its own string spelling"
                )
            if key == "<<":
                raise RestrictedYamlError(
                    IssueCode.RESTRICTED_YAML_VIOLATION,
                    "YAML merge keys are not permitted",
                )
            if key in seen:
                raise RestrictedYamlError(
                    IssueCode.RESTRICTED_YAML_VIOLATION,
                    f"duplicate mapping key {key!r}",
                )
            seen.add(key)
        return super().construct_mapping(node, deep=deep)


def load_yaml_bytes(raw: bytes, *, logical_path: PurePosixPath) -> object:
    """Parse one bundle document. Raises `RestrictedYamlError` for anything out of contract.

    Exactly one YAML document per file: a second document would be discarded by `safe_load` and
    its content would never be validated, hashed, or reviewed.
    """
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RestrictedYamlError(
            IssueCode.INVALID_UTF8,
            f"{logical_path}: not valid UTF-8 ({exc.reason})",
        ) from exc
    try:
        documents = list(yaml.load_all(text, Loader=CareerProfileLoader))
    except RestrictedYamlError as exc:
        raise RestrictedYamlError(exc.code, f"{logical_path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise RestrictedYamlError(
            IssueCode.INVALID_YAML,
            f"{logical_path}: invalid YAML ({type(exc).__name__})",
        ) from exc
    except Exception as exc:
        raise ProfileBundleError(f"{logical_path}: internal YAML loader failure") from exc
    if len(documents) > 1:
        raise RestrictedYamlError(
            IssueCode.RESTRICTED_YAML_VIOLATION,
            f"{logical_path}: {len(documents)} YAML documents; exactly one is permitted"
        )
    return documents[0] if documents else None
