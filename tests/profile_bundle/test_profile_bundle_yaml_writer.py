"""The restricted-YAML emitter (design §6, §19).

`init` is the first command that has to *write* bundle documents, and the authoring contract the
restricted loader enforces is narrow enough that a stock `yaml.safe_dump` produces documents
Boardwatch itself cannot read back. These tests pin that the emitter's output is readable by the
one loader that matters, and that the claim is checked against the real example corpus rather than
against a hand-picked string.
"""

from __future__ import annotations

from pathlib import PurePosixPath

import pytest
import yaml

from boardwatch.profile_bundle.errors import ProfileBundleError
from boardwatch.profile_bundle.yaml_loader import load_yaml_bytes
from boardwatch.profile_bundle.yaml_writer import DocumentEmitError, document_bytes
from tests.profile_bundle.conftest import example_source_root

ANY_PATH = PurePosixPath("manifest.yaml")


def _example_documents() -> dict[PurePosixPath, object]:
    """Every packaged example document, parsed through the production loader."""
    root = example_source_root()
    found: dict[PurePosixPath, object] = {}
    for path in sorted(root.rglob("*.yaml")):
        logical = PurePosixPath(path.relative_to(root).as_posix())
        found[logical] = load_yaml_bytes(path.read_bytes(), logical_path=logical)
    return found


def test_every_example_document_survives_a_write_read_round_trip() -> None:
    """The corpus, not a sample: a writer is only usable if it round-trips real content."""
    documents = _example_documents()
    assert len(documents) >= 27, "the example corpus shrank; the round trip is no longer meaningful"
    for logical, payload in documents.items():
        raw = document_bytes(payload, logical_path=logical)
        assert load_yaml_bytes(raw, logical_path=logical) == payload, logical


def test_the_stock_dumper_is_unusable_for_part_of_that_corpus() -> None:
    """The negative control.

    Without it, an emitter that simply delegated to `yaml.safe_dump` would pass the round-trip test
    on whatever subset happened to be unambiguous, and the reason this module exists would be
    invisible. The failing subset is discovered, never hard-coded, so it tracks the corpus.
    """
    rejected: list[PurePosixPath] = []
    for logical, payload in _example_documents().items():
        stock = yaml.safe_dump(payload, sort_keys=False, allow_unicode=True).encode("utf-8")
        try:
            if load_yaml_bytes(stock, logical_path=logical) != payload:
                rejected.append(logical)
        except ProfileBundleError:
            rejected.append(logical)
    assert rejected, "yaml.safe_dump now round-trips every example; this module has no reason to be"


def test_a_scalar_the_loader_would_retype_is_quoted_rather_than_emitted_plain() -> None:
    """The four shapes §7 calls out: a date, an ambiguous integer, a bool word, and a digest."""
    payload = {
        "started_at": "2024-09",
        "code": "01",
        "answer": "no",
        "digest": "a" * 64,
        "prose": "~120 items/s",
    }
    assert load_yaml_bytes(document_bytes(payload, logical_path=ANY_PATH), logical_path=ANY_PATH) == (
        payload
    )


def test_real_integers_booleans_and_nulls_stay_typed() -> None:
    """Quoting strings must not quote everything: a version is an int on both sides."""
    payload = {"schema_version": 1, "negative": -3, "flag": True, "absent": None}
    assert load_yaml_bytes(document_bytes(payload, logical_path=ANY_PATH), logical_path=ANY_PATH) == (
        payload
    )


def test_a_long_string_is_not_folded_into_a_different_value() -> None:
    """PyYAML wraps at 80 columns by default, and a fold rewrites whitespace inside a scalar."""
    payload = {"summary": " ".join(["word"] * 60), "spaced": "a" + " " * 8 + "b " * 40}
    emitted = document_bytes(payload, logical_path=ANY_PATH)
    assert load_yaml_bytes(emitted, logical_path=ANY_PATH) == payload


def test_key_order_is_preserved_and_bytes_are_deterministic() -> None:
    payload = {"zebra": "1", "alpha": "2", "middle": "3"}
    first = document_bytes(payload, logical_path=ANY_PATH)
    assert first == document_bytes(payload, logical_path=ANY_PATH)
    assert first.index(b"zebra") < first.index(b"alpha") < first.index(b"middle")


def test_output_ends_with_exactly_one_newline() -> None:
    raw = document_bytes({"a": "b"}, logical_path=ANY_PATH)
    assert raw.endswith(b"\n") and not raw.endswith(b"\n\n")


def test_a_value_the_loader_would_refuse_fails_at_write_time() -> None:
    """A float has no reproducible spelling, so `canonical.py` refuses it and the loader refuses
    the emitted `1.5`. The emitter must not be the one component that lets it through."""
    with pytest.raises(DocumentEmitError):
        document_bytes({"ratio": 1.5}, logical_path=ANY_PATH)


def test_a_payload_that_does_not_reload_identically_fails_at_write_time() -> None:
    """A tuple emits as a list, so the document on disk would no longer be the payload asked for.

    This is the general guarantee: the emitter verifies its own bytes through the loader instead of
    restating the loader's grammar, so any future divergence fails here rather than at the next
    `validate`.
    """
    with pytest.raises(DocumentEmitError):
        document_bytes({"items": ("a", "b")}, logical_path=ANY_PATH)


def test_a_non_string_mapping_key_fails_at_write_time() -> None:
    with pytest.raises(DocumentEmitError):
        document_bytes({1: "a"}, logical_path=ANY_PATH)
