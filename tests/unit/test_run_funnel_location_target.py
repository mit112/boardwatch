"""T204 — a lead's `location_class` is the location GATE's verdict for the run's target countries.

Since T186 (D-583) the hard location gate reads the profile's `target_countries` through
`location_target(...).classify`. The funnel labelled each lead with `classify_location`, the US
reading, so for a tenant targeting another country the artifact answered the wrong question. The
manifest now carries the run's `target_countries` and the class is derived from them.

The `usa` pack is the only one that ships, so a Canadian tenant's pack is a fixture here, patched
in at the one call the funnel makes — exactly as `test_location_target.py` hands it to the gates.
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from boardwatch.rank import location_gate
from boardwatch.reports import run_funnel
from boardwatch.reports.run_funnel import ARTIFACT_VERSION, funnel_to_dict, funnel_to_markdown
from tests.unit.test_location_target import WITH_CAN
from tests.unit.test_run_funnel import funnel, lead, run_manifest


@pytest.fixture()
def with_can_pack(monkeypatch: pytest.MonkeyPatch) -> None:
    def target(countries: Sequence[str]) -> location_gate.LocationTarget:
        return location_gate.location_target(countries, WITH_CAN)

    monkeypatch.setattr(run_funnel, "location_target", target)


def _classes(target_countries: tuple[str, ...] | None, *leads: object) -> list[object]:
    payload = funnel_to_dict(
        funnel(manifest=run_manifest(target_countries=target_countries), leads=list(leads))
    )
    return [row["location_class"] for row in payload["leads"]]


@pytest.mark.usefixtures("with_can_pack")
def test_a_canadian_tenant_s_leads_are_classed_against_canada() -> None:
    """Toronto is in the target, Austin is out of it, and a posting naming no place is
    `unknown` — the three answers the gate itself gives a CAN profile."""
    got = _classes(
        ("CAN",),
        lead(1, locations=("Toronto, ON",)),
        lead(2, locations=("Austin, TX",)),
        lead(3, locations=None),
    )

    assert got == ["in_target", "out_of_target", "unknown"]


def test_the_class_is_the_gate_s_own_verdict_not_a_second_copy() -> None:
    """Asserted against `location_target(...).classify` — the call the ranker and the review gate
    make — rather than against transcribed answers."""
    cases: tuple[tuple[str, ...], ...] = (
        ("Austin, TX",), ("Berlin, Germany",), ("Remote",), ("Bengaluru, India", "New York, NY"),
    )
    for locations in cases:
        (got,) = _classes(("USA",), lead(locations=locations))
        assert got == location_gate.location_target(("USA",)).classify(locations), locations


@pytest.mark.parametrize("target_countries", [None, ()])
def test_undeclared_targets_read_abstain_never_a_location_verdict(
    target_countries: tuple[str, ...] | None,
) -> None:
    """`None` is a funnel built without the field; `()` is a profile that declared no targets.
    Either way the gate is INERT (owner ruling Q2), so the lead reads `abstain` — not `unknown`,
    which is a verdict about the posting, and never the US reading's `us`."""
    got = _classes(target_countries, lead(1, locations=("Austin, TX",)), lead(2, locations=None))

    assert got == ["abstain", "abstain"]


def test_a_target_with_no_shipped_pack_reads_abstain() -> None:
    """The production packs: a CAN target has no `can` pack, so the gate abstains
    (`missing_country_pack:CAN`) and so does the lead — never `out_of_target` for Toronto."""
    assert _classes(("CAN",), lead(locations=("Toronto, ON",))) == ["abstain"]


def test_the_manifest_publishes_the_target_countries_the_classes_were_read_against() -> None:
    manifest = funnel_to_dict(funnel(manifest=run_manifest(target_countries=("USA",))))["manifest"]
    assert manifest["target_countries"] == ["USA"]

    unrecorded = funnel_to_dict(funnel(manifest=run_manifest(target_countries=None)))["manifest"]
    assert unrecorded["target_countries"] is None

    body = funnel_to_markdown(funnel(manifest=run_manifest(target_countries=("USA", "CAN"))))
    row = next(line for line in body.splitlines() if line.startswith("| target countries |"))
    assert "USA, CAN" in row, row


def test_the_class_vocabulary_moved_so_the_artifact_version_did() -> None:
    """`us`/`non_us` became `in_target`/`out_of_target`/`abstain`: an existing key changed
    MEANING, which is what the version exists to say."""
    assert ARTIFACT_VERSION == 9
    assert funnel_to_dict(funnel())["artifact_version"] == 9
