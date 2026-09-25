"""`core/yamlio.load_bundled`: libyaml for the package's own YAML, the pure parser for the rest.

The equivalence is proved per FILE, not per call site. A bundled file is fixed text, so both
parsers loading every one of them identically is the whole claim, and a future edit that reaches
a construct they read differently fails here. The divergences are pinned as well. They are why
user-authored text stays on plain `yaml.safe_load`, and the routing tests use them as oracles:
each one is an input whose result shows which parser ran.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml

import boardwatch
from boardwatch.core import yamlio
from boardwatch.core.yamlio import load_bundled

libyaml = pytest.mark.skipif(not yaml.__with_libyaml__, reason="libyaml is not installed")

PACKAGE = Path(boardwatch.__file__).resolve().parent
BUNDLED_YAML = sorted(p for p in PACKAGE.rglob("*.y*ml") if "__pycache__" not in p.parts)

#: Parsed as `{'a': None}` by the pure parser and `{'a': ''}` by libyaml.
ORACLE = "a: !\n"


def _outcome(loader: type[Any], text: str | bytes) -> tuple[str, str]:
    try:
        return "value", repr(yaml.load(text, Loader=loader))
    except Exception as exc:  # the exception TYPE is the outcome being compared
        return "raises", type(exc).__name__


def test_the_package_yaml_glob_found_every_file_load_bundled_reads() -> None:
    names = {p.relative_to(PACKAGE).as_posix() for p in BUNDLED_YAML}
    assert {
        "eligibility/rules.yaml",
        "extract/taxonomy.yaml",
        "rank/leveling.yaml",
        "registry/companies.yaml",
        "tailor/personas.yaml",
        "tailor/register.yaml",
        "tailor/equivalences.yaml",
    } <= names
    assert len(names) >= 40


@libyaml
@pytest.mark.parametrize("path", BUNDLED_YAML, ids=lambda p: p.relative_to(PACKAGE).as_posix())
def test_every_bundled_yaml_file_parses_identically_with_both_loaders(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    pure = yaml.load(text, Loader=yaml.SafeLoader)
    # repr, not ==: `True == 1 == 1.0` would let a type change through.
    assert repr(yaml.load(text, Loader=yaml.CSafeLoader)) == repr(pure)
    assert repr(load_bundled(text)) == repr(pure)


AGREEING = {
    "duplicate keys": "a: 1\na: 2\n",
    "yes/no/on/off": "[yes, no, on, off, Yes, NO, True, FALSE, y, n]\n",
    "octal": "[0o17, 017, 0x1F, 0b101, 1_000, 09]\n",
    "sexagesimal": "[190:20:30, 1:30]\n",
    "floats": "[1.0, 1., .5, 1e5, 6.8523015e+5, .inf, -.Inf]\n",
    "nulls": "[~, null, Null, NULL, '']\n",
    "timestamps": "[2001-12-14t21:59:43.10-05:00, 2002-12-14, 2001-12-14 21:59:43.10 -5]\n",
    "very large ints": "[123456789012345678901234567890, -0x1234567890abcdef1234567890]\n",
    "BOM at the start": "\ufeffa: 1\n",
    "BOM inside a value": "a: x\ufeffy\n",
    "CRLF and a block scalar": "a: 1\r\nb: |\r\n  x\r\n  y\r\n",
    "anchors, aliases and merge": "b: &b {k: 1}\nd:\n  <<: *b\n  j: 2\n",
    "explicit core tags": "a: !!int '12'\nb: !!float 1\nc: !!str 12\nd: !!binary aGk=\n",
    "block scalars": "a: |\n  x\nb: >\n  f\n\n  g\nc: |-\n  z\nd: |+\n  w\n\ne: |2\n    i\n",
    "quoted escapes": "a: 'it''s'\nb: \"\\x41\\u263A\\U0001F600\\N\\_\"\n",
    "empty document": "",
    "comment only": "# c\n",
    "non-string keys": "1: a\nnull: b\ntrue: c\n1.5: d\n",
}


@libyaml
@pytest.mark.parametrize("text", AGREEING.values(), ids=AGREEING.keys())
def test_the_edge_cases_the_two_loaders_agree_on(text: str) -> None:
    assert _outcome(yaml.CSafeLoader, text) == _outcome(yaml.SafeLoader, text)
    assert _outcome(yaml.CSafeLoader, text)[0] == "value"


REFUSED_BY_BOTH = {
    "python/object": "!!python/object:os.system {}\n",
    "python/object/apply": "!!python/object/apply:os.system ['true']\n",
    "python/name": "a: !!python/name:os.system\n",
    "python/tuple": "!!python/tuple [1, 2]\n",
    "an unknown tag": "a: !custom 1\n",
    "two documents": "a: 1\n---\nb: 2\n",
    "an undefined alias": "a: *nope\n",
    "an unhashable key": "? [1, 2]\n: c\n",
    "a control character": "a: \x07\n",
}


@libyaml
@pytest.mark.parametrize("text", REFUSED_BY_BOTH.values(), ids=REFUSED_BY_BOTH.keys())
def test_what_the_pure_loader_refuses_libyaml_refuses_with_the_same_exception_type(
    text: str,
) -> None:
    pure = _outcome(yaml.SafeLoader, text)
    assert pure[0] == "raises"
    assert _outcome(yaml.CSafeLoader, text) == pure
    with pytest.raises(yaml.YAMLError):
        load_bundled(text)


@libyaml
def test_non_utf8_bytes_are_refused_by_both_with_the_same_exception_type() -> None:
    latin1 = "a: caf\xe9\n".encode("latin-1")
    assert _outcome(yaml.SafeLoader, latin1) == ("raises", "ReaderError")
    assert _outcome(yaml.CSafeLoader, latin1) == ("raises", "ReaderError")


#: The finding (T229): input on which the two parsers DIFFER, so it must never reach libyaml
#: from a user's file. (pure outcome, libyaml outcome).
DIVERGENT = {
    "tab after a colon": ("a:\tb\n", ("raises", "ScannerError"), ("value", "{'a': 'b'}")),
    "tab inside a plain scalar": (
        "a: b\tc\n", ("raises", "ScannerError"), ("value", "{'a': 'b\\tc'}")
    ),
    "comment touching a block header": (
        "a: |#c\n  x\n", ("raises", "ScannerError"), ("value", "{'a': 'x\\n'}")
    ),
    "? in a flow plain scalar": ("{a?}\n", ("raises", "ParserError"), ("value", "{'a?': None}")),
    "empty scalar tagged !": (ORACLE, ("value", "{'a': None}"), ("value", "{'a': ''}")),
    "BOM starting a later line": ("\n\ufeffb\n", ("value", "'\\ufeffb'"), ("value", "'b'")),
    "BOM before a later key": (
        "a: 1\n\ufeffb: 2\n", ("value", "{'a': 1, '\\ufeffb': 2}"), ("raises", "ParserError")
    ),
    "surrogate escape": ('a: "\\ud800"\n', ("value", "{'a': '\\ud800'}"), ("raises", "ScannerError")),
    "lone surrogate": ("a: \ud800\n", ("raises", "ReaderError"), ("raises", "UnicodeEncodeError")),
}


@libyaml
@pytest.mark.parametrize(("text", "pure", "c"), DIVERGENT.values(), ids=DIVERGENT.keys())
def test_the_divergences_that_keep_user_text_on_the_pure_loader(
    text: str, pure: tuple[str, str], c: tuple[str, str]
) -> None:
    assert _outcome(yaml.SafeLoader, text) == pure
    assert _outcome(yaml.CSafeLoader, text) == c


@libyaml
def test_load_bundled_parses_with_libyaml_when_it_is_installed() -> None:
    assert load_bundled(ORACLE) == {"a": ""}


def test_load_bundled_falls_back_to_the_pure_loader_without_libyaml(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(yaml, "__with_libyaml__", False)
    # Without libyaml, `yaml` has no CSafeLoader at all; naming it would raise AttributeError.
    monkeypatch.delattr(yaml, "CSafeLoader", raising=False)
    assert load_bundled(ORACLE) == {"a": None}
    assert load_bundled("a: [1, yes]\n") == {"a": [1, True]}


def _sites() -> dict[str, tuple[str, Callable[[Path], object]]]:
    from boardwatch.eligibility import catalog
    from boardwatch.extract import taxonomy
    from boardwatch.rank import leveling
    from boardwatch.registry import loader
    from boardwatch.tailor import equivalences, persona, register

    return {
        "catalog": ("boardwatch.eligibility.catalog", catalog.load_rules),
        "taxonomy": ("boardwatch.extract.taxonomy", taxonomy.load_taxonomy),
        "leveling": ("boardwatch.rank.leveling", leveling.load_leveling),
        "personas": ("boardwatch.tailor.persona", persona.load_personas),
        "registry": ("boardwatch.registry.loader", lambda _: loader.load_catalog_raw()),
        "register": ("boardwatch.tailor.register", lambda _: register.load_register()),
        "equivalences": (
            "boardwatch.tailor.equivalences", lambda _: equivalences.load_equivalences()
        ),
    }


@pytest.mark.parametrize("site", list(_sites()))
def test_each_bundled_file_is_parsed_through_load_bundled(
    site: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module, load = _sites()[site]
    texts: list[str] = []

    def spy(text: str) -> Any:
        texts.append(text)
        return yamlio.load_bundled(text)

    monkeypatch.setattr(f"{module}.load_bundled", spy)
    if site == "catalog":
        from boardwatch.eligibility.catalog import _parse_rules

        _parse_rules.cache_clear()  # an earlier test may have cached the bundled catalog
    load(tmp_path)
    assert len(texts) == 1


#: A user's override with a tab after a colon: the pure parser refuses it, libyaml would not.
TAB_OVERRIDE = "a:\tb\n"


@pytest.mark.parametrize(
    ("site", "filename"),
    [
        ("catalog", "rules.yaml"),
        ("taxonomy", "taxonomy.yaml"),
        ("leveling", "leveling.yaml"),
        ("personas", "personas.yaml"),
    ],
)
def test_a_user_override_is_still_parsed_by_the_pure_loader(
    site: str, filename: str, tmp_path: Path
) -> None:
    from boardwatch.eligibility.catalog import CatalogError
    from boardwatch.extract.taxonomy import TaxonomyError
    from boardwatch.tailor.persona import PersonaError

    error = {
        "catalog": CatalogError,
        "taxonomy": TaxonomyError,
        "leveling": yaml.scanner.ScannerError,
        "personas": PersonaError,
    }[site]
    (tmp_path / filename).write_text(TAB_OVERRIDE, encoding="utf-8")
    # libyaml reads this as {'a': 'b'}, and every site but leveling would then raise the same
    # type for a different reason, so the pure scanner's own message is what is asserted.
    with pytest.raises(error, match="found character '\\\\t' that cannot start any token"):
        _sites()[site][1](tmp_path)


def test_a_registry_file_passed_by_path_is_still_parsed_by_the_pure_loader(
    tmp_path: Path,
) -> None:
    from boardwatch.registry.loader import load_catalog_raw

    path = tmp_path / "companies.yaml"
    path.write_text(TAB_OVERRIDE, encoding="utf-8")
    with pytest.raises(yaml.scanner.ScannerError):
        load_catalog_raw(path)
