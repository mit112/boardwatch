"""The restricted YAML authoring contract (design §7).

YAML 1.1's implicit scalars are the hazard this loader exists to close: `no` becomes `False`,
`2026-08-10` becomes a `datetime.date` before Pydantic ever sees it, `01` becomes octal `1`, and
`1.5` becomes a float that the canonical serializer cannot hash reproducibly.

The chosen behaviour is to REFUSE an out-of-contract plain scalar rather than silently treat it as
a string. Silently stringifying is worse: `expires_at: 2026-08-10` would parse, and the author
would never learn that the contract wants it quoted.
"""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import NoReturn

import pytest
import yaml

from boardwatch.profile_bundle.errors import RestrictedYamlError
from boardwatch.profile_bundle.yaml_loader import load_yaml_bytes

IDENTITY = PurePosixPath("facts/identity.yaml")
MANIFEST = PurePosixPath("manifest.yaml")


@pytest.mark.parametrize(
    "token",
    [
        "yes",
        "no",
        "on",
        "off",
        "2026-08-10",
        "01",
        ".nan",
        ".inf",
        "-.inf",
        "1.5",
        "0x1f",
        "0o17",
        "1_000",
        "12:30",
        "True",
        "FALSE",
        "Null",
        "089",
        "2026-08-10T12:00:00Z",
    ],
)
def test_ambiguous_plain_scalar_is_rejected(token: str) -> None:
    with pytest.raises(RestrictedYamlError):
        load_yaml_bytes(f"value: {token}\n".encode(), logical_path=IDENTITY)


def test_quoted_boolean_like_string_stays_a_string() -> None:
    assert load_yaml_bytes(b'value: "no"\n', logical_path=IDENTITY) == {"value": "no"}


@pytest.mark.parametrize(
    "token",
    ["2026-08-10", "1.5", "01", "yes", "true", "12:30", ".nan"],
)
def test_quoting_is_the_documented_escape_hatch(token: str) -> None:
    assert load_yaml_bytes(f'value: "{token}"\n'.encode(), logical_path=IDENTITY) == {
        "value": token
    }


@pytest.mark.parametrize("body", [b"a: 1\na: 2\n", b"base: &x {a: 1}\ncopy: *x\n", b"x: {<<: {a: 1}}\n"])
def test_duplicate_anchor_alias_and_merge_are_rejected(body: bytes) -> None:
    with pytest.raises(RestrictedYamlError):
        load_yaml_bytes(body, logical_path=MANIFEST)


def test_duplicate_key_is_rejected_even_nested_and_in_a_sequence() -> None:
    with pytest.raises(RestrictedYamlError):
        load_yaml_bytes(b"rows:\n  - a: 1\n    a: 2\n", logical_path=MANIFEST)


def test_anchor_alone_is_rejected_even_without_an_alias() -> None:
    """An anchor with no alias is harmless today and is the first half of one tomorrow."""
    with pytest.raises(RestrictedYamlError):
        load_yaml_bytes(b"base: &anchor {a: 1}\n", logical_path=MANIFEST)


def test_exact_lowercase_booleans_and_plain_integers_are_accepted() -> None:
    parsed = load_yaml_bytes(
        b"flag: true\nother: false\ncount: 0\nnegative: -12\nbig: 1234567890\n",
        logical_path=MANIFEST,
    )
    assert parsed == {
        "flag": True,
        "other": False,
        "count": 0,
        "negative": -12,
        "big": 1234567890,
    }


def test_null_and_empty_value_are_null() -> None:
    assert load_yaml_bytes(b"a: null\nb:\nc: ~\n", logical_path=MANIFEST) == {
        "a": None,
        "b": None,
        "c": None,
    }


def test_integer_type_is_int_not_bool() -> None:
    """`isinstance(True, int)` is True in Python, so identity is the only honest check."""
    parsed = load_yaml_bytes(b"one: 1\nyes_flag: true\n", logical_path=MANIFEST)
    assert isinstance(parsed, dict)
    assert parsed["one"] is not True
    assert parsed["yes_flag"] is True


def test_invalid_utf8_is_refused_before_parsing() -> None:
    with pytest.raises(RestrictedYamlError):
        load_yaml_bytes(b"value: \xff\xfe\n", logical_path=IDENTITY)


def test_malformed_yaml_is_refused() -> None:
    with pytest.raises(RestrictedYamlError):
        load_yaml_bytes(b"value: [unclosed\n", logical_path=IDENTITY)


def test_multiple_documents_are_refused() -> None:
    """One logical file is one document; a second would be silently discarded."""
    with pytest.raises(RestrictedYamlError):
        load_yaml_bytes(b"a: 1\n---\nb: 2\n", logical_path=MANIFEST)


def test_python_object_tags_are_refused() -> None:
    with pytest.raises(RestrictedYamlError):
        load_yaml_bytes(b"!!python/object:os.system {}\n", logical_path=MANIFEST)


@pytest.mark.parametrize(
    "body",
    [
        b"value: !!str text\n",
        b"value: !!int 1\n",
        b"value: !!float 1.5\n",
        b"value: !!bool true\n",
        b"value: !!null null\n",
        b"value: !!timestamp 2026-08-10\n",
        b"value: !!binary MQ==\n",
        b"value: !!set {member: null}\n",
        b"value: !!omap [{key: value}]\n",
        b"value: !!pairs [{key: value}]\n",
        b"value: !!seq [item]\n",
        b"value: !!map {key: value}\n",
    ],
)
def test_explicit_standard_yaml_tag_is_refused(body: bytes) -> None:
    with pytest.raises(RestrictedYamlError):
        load_yaml_bytes(body, logical_path=MANIFEST)


def test_custom_yaml_tag_is_refused() -> None:
    with pytest.raises(RestrictedYamlError):
        load_yaml_bytes(b"value: !foo text\n", logical_path=MANIFEST)


def test_unexpected_parser_exception_is_wrapped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_builtin(*args: object, **kwargs: object) -> NoReturn:
        raise ValueError("constructor failed")

    monkeypatch.setattr(yaml, "load_all", raise_builtin)

    with pytest.raises(RestrictedYamlError) as excinfo:
        load_yaml_bytes(b"value: text\n", logical_path=MANIFEST)
    assert "manifest.yaml" in str(excinfo.value)


def test_empty_document_parses_to_none_for_the_model_layer_to_reject() -> None:
    """The loader does not invent a shape. An empty declared file fails model validation."""
    assert load_yaml_bytes(b"", logical_path=MANIFEST) is None


def test_error_names_the_logical_path_so_the_author_can_find_it() -> None:
    with pytest.raises(RestrictedYamlError) as excinfo:
        load_yaml_bytes(b"value: yes\n", logical_path=IDENTITY)
    assert "facts/identity.yaml" in str(excinfo.value)


@pytest.mark.parametrize("body", [b"1: value\n", b"? [1, 2]\n: value\n", b"true: value\n"])
def test_non_string_mapping_key_is_refused(body: bytes) -> None:
    """A non-string key canonicalises to a string and would collide with the real one."""
    with pytest.raises(RestrictedYamlError):
        load_yaml_bytes(body, logical_path=MANIFEST)
