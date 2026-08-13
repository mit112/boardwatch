"""The shipped example declaration is real, loadable, and inventoried."""

from __future__ import annotations

from importlib import resources

from boardwatch.projection.declaration import load_declaration
from tools.generalization import allowlists as al

EXAMPLE = "src/boardwatch/projection/examples/projection.example.yaml"


def test_the_example_is_registered_as_synthetic_shipped_data() -> None:
    entry = al.SHIPPED_DATA.get(EXAMPLE)
    assert entry is not None, f"{EXAMPLE} needs a reviewed SHIPPED_DATA entry (R7)"
    assert entry.kind == "fixture"
    assert entry.provenance == "synthetic"
    assert entry.pin.startswith("sha256:")


def test_the_example_parses_through_the_production_loader() -> None:
    """Delegates rather than re-parsing: a fixture validated by its own path would let the
    fixture agree with itself while disagreeing with what the CLI reads."""
    traversable = resources.files("boardwatch.projection.examples").joinpath(
        "projection.example.yaml"
    )
    with resources.as_file(traversable) as path:
        declaration = load_declaration(path)
    assert declaration.entries
    assert declaration.pinned_ids
    assert declaration.candidate_ids, "the example must exercise BOTH pinned and candidate arms"
