"""`load_resume(serialize(resume)) == resume`. That is the contract.

The round trip runs through the PRODUCTION loader (`tailor.load.load_resume`), not through
`yaml.safe_load` compared to a dict — `load_resume` additionally calls `validate_master`, which
scans every text field for a leftover template artifact and raises if it finds one. A test that
only re-parsed the YAML would miss a serializer that mangles content in a way that still parses.

Every assertion below is against the ORIGINAL `Resume` object built in Python, never against a
second serialization of it — comparing two dumps, or two re-parses, agrees with itself even if the
serializer drops or mangles a field.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from boardwatch.projection.serialize import resume_document_bytes
from boardwatch.tailor.load import MasterResumeError, load_resume
from boardwatch.tailor.model import Bullet, Entry, Resume, SkillGroup


def _resume() -> Resume:
    return Resume(
        header=["Example Candidate", "candidate@example.com", "+1 555 0100"],
        education=["Example University — B.S. Computer Science"],
        skill_groups=[SkillGroup(label="Languages", items=["Example Language", "Swift"])],
        entries=[
            Entry(
                entry_id="entry.employment.example-labs",
                heading="Example Labs",
                kind="experience",
                title="Software Engineer",
                dates="2025-02-01 – Present",
                subtitle="Example Labs",
                location="Remote",
                bullets=[
                    Bullet(
                        bullet_id="claim.a.001",
                        text="Built a retry-safe ingestion path",
                        tech_tags=["Example Language", "Swift"],
                    ),
                    Bullet(bullet_id="claim.a.002", text="Measured sustained local throughput"),
                ],
            ),
            Entry(
                # No title/dates/subtitle/location set: pins that an unset optional field on a
                # SECOND entry stays None rather than inheriting or defaulting from the first.
                entry_id="entry.project.packet-pantry",
                heading="Packet Pantry",
                kind="project",
                bullets=[Bullet(bullet_id="claim.b.001", text="Shipped a public service")],
            ),
        ],
        extracurricular=["Example Society — organiser"],
    )


def test_a_projected_resume_round_trips_through_the_production_loader(tmp_path: Path) -> None:
    original = _resume()
    path = tmp_path / "projected.yaml"
    path.write_bytes(resume_document_bytes(original))
    assert load_resume(path) == original


def test_the_bytes_are_stable_for_one_document() -> None:
    """Deterministic output, so the golden test and the digest both mean something."""
    assert resume_document_bytes(_resume()) == resume_document_bytes(_resume())


def test_a_unicode_extracurricular_line_survives_the_round_trip(tmp_path: Path) -> None:
    """The repo has been bitten by mojibake in appended text; the serializer must not add to it."""
    original = _resume().model_copy(
        update={
            "extracurricular": ["Café résumé — naïve coöperation"],
        }
    )
    path = tmp_path / "projected.yaml"
    path.write_bytes(resume_document_bytes(original))
    assert load_resume(path).extracurricular == ["Café résumé — naïve coöperation"]


def test_a_unicode_bullet_text_survives_the_round_trip(tmp_path: Path) -> None:
    """Same property, on a field that also passes through `Bullet`'s single-line normaliser."""
    original = _resume().model_copy(
        update={
            "entries": [
                Entry(
                    entry_id="entry.a",
                    heading="Heading",
                    bullets=[Bullet(bullet_id="b.1", text="Naïve café — 日本語 — coöperation")],
                )
            ]
        }
    )
    path = tmp_path / "projected.yaml"
    path.write_bytes(resume_document_bytes(original))
    assert load_resume(path).entries[0].bullets[0].text == "Naïve café — 日本語 — coöperation"


# ----------------------------------------------------------------------------------------
# Exhaustive, derived-at-runtime field coverage. If `Resume` gains a field tomorrow, this
# test notices without anyone updating a hand-written list here.
# ----------------------------------------------------------------------------------------


def test_every_declared_field_of_resume_round_trips(tmp_path: Path) -> None:
    original = _resume()
    field_names = list(type(original).model_fields)

    # Non-vacuity: the derivation actually found fields, not an empty/broken accessor. Pinned
    # to the current count's neighbourhood rather than an exact number, so a genuinely new
    # field still trips this if the count moves outside a plausible band, while the real
    # per-field loop below is what a defect must actually defeat.
    assert 4 <= len(field_names) <= 12, field_names

    path = tmp_path / "projected.yaml"
    path.write_bytes(resume_document_bytes(original))
    loaded = load_resume(path)

    for name in field_names:
        assert getattr(loaded, name) == getattr(original, name), name


# ----------------------------------------------------------------------------------------
# None vs absent vs empty string; empty collections vs absent keys.
# ----------------------------------------------------------------------------------------


def test_none_valued_optional_fields_survive_as_absent_not_the_literal_string_none(
    tmp_path: Path,
) -> None:
    original = _resume()  # second entry already leaves title/dates/subtitle/location unset
    assert original.title is None
    second = original.entries[1]
    assert second.title is None and second.dates is None
    assert second.subtitle is None and second.location is None

    path = tmp_path / "projected.yaml"
    raw = resume_document_bytes(original)
    assert b"None" not in raw  # the Python repr of None must never leak into the document
    path.write_bytes(raw)

    loaded = load_resume(path)
    assert loaded.title is None
    loaded_second = loaded.entries[1]
    assert loaded_second.title is None
    assert loaded_second.dates is None
    assert loaded_second.subtitle is None
    assert loaded_second.location is None


def test_empty_string_title_is_distinct_from_a_none_title(tmp_path: Path) -> None:
    original = _resume().model_copy(update={"title": ""})
    path = tmp_path / "projected.yaml"
    path.write_bytes(resume_document_bytes(original))
    loaded = load_resume(path)
    assert loaded.title == ""
    assert loaded.title is not None


def test_empty_collections_round_trip_as_empty_not_absent(tmp_path: Path) -> None:
    original = _resume().model_copy(
        update={
            "extracurricular": [],
            "entries": [
                Entry(
                    entry_id="entry.a",
                    heading="Heading",
                    bullets=[Bullet(bullet_id="b.1", text="No tags on this one")],
                )
            ],
            "skill_groups": [SkillGroup(label="Empty group", items=[])],
        }
    )
    assert original.entries[0].bullets[0].tech_tags == []

    path = tmp_path / "projected.yaml"
    path.write_bytes(resume_document_bytes(original))
    loaded = load_resume(path)

    assert loaded.extracurricular == []
    assert loaded.skill_groups[0].items == []
    assert loaded.entries[0].bullets[0].tech_tags == []


# ----------------------------------------------------------------------------------------
# Scalars that look like another YAML type.
# ----------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "look_alike",
    [
        "12:30",
        "true",
        "False",
        "no",
        "off",
        "2021-01-01",
        "0123",
        "1e10",
        "null",
        "~",
        "-1",
        "3.14",
    ],
)
def test_strings_that_look_like_other_yaml_types_round_trip_as_strings(
    tmp_path: Path, look_alike: str
) -> None:
    original = _resume().model_copy(
        update={
            "education": [look_alike],
            "entries": [
                Entry(
                    entry_id="entry.a",
                    heading="Heading",
                    dates=look_alike,
                    bullets=[Bullet(bullet_id="b.1", text=f"Handled {look_alike} in production")],
                )
            ],
        }
    )
    path = tmp_path / "projected.yaml"
    path.write_bytes(resume_document_bytes(original))
    loaded = load_resume(path)

    assert loaded.education == [look_alike]
    assert isinstance(loaded.education[0], str)
    assert loaded.entries[0].dates == look_alike
    assert isinstance(loaded.entries[0].dates, str)


# ----------------------------------------------------------------------------------------
# Multi-line strings and long single-line strings.
# ----------------------------------------------------------------------------------------


def test_a_multiline_header_line_survives_the_round_trip(tmp_path: Path) -> None:
    """`Bullet` normalises embedded newlines to spaces, but `header` carries no such
    validator, so a literal newline is directly constructible here and is a real edge case
    for a YAML emitter (block vs folded vs quoted-with-escape styles all differ)."""
    original = _resume().model_copy(
        update={"header": ["Example Candidate\nSecond line", "candidate@example.com"]}
    )
    path = tmp_path / "projected.yaml"
    path.write_bytes(resume_document_bytes(original))
    assert load_resume(path).header == ["Example Candidate\nSecond line", "candidate@example.com"]


def test_a_long_line_is_not_folded_or_reflowed(tmp_path: Path) -> None:
    """Guards the emitter's width choice: PyYAML's default 80-column fold is lossless for
    plain space-separated text, but a serializer that forgot to widen it would still be
    correct by luck on short fixtures. This one is long enough to force a fold at width=80."""
    long_text = "word " * 40  # ~200 chars, comfortably past the default fold width
    original = _resume().model_copy(update={"extracurricular": [long_text]})
    path = tmp_path / "projected.yaml"
    path.write_bytes(resume_document_bytes(original))
    assert load_resume(path).extracurricular == [long_text]


# ----------------------------------------------------------------------------------------
# The round trip is not just re-parsing: the master gate must actually run on the reloaded
# document.
# ----------------------------------------------------------------------------------------


def test_a_template_artifact_in_the_source_resume_is_still_caught_after_serializing(
    tmp_path: Path,
) -> None:
    """`resume_document_bytes` is a serializer, not a validator — it has no opinion about
    content. This pins that the loader's `validate_master` gate still fires on the
    round-tripped bytes, which is what a test that stopped at `yaml.safe_load(...) ==
    payload` could never demonstrate."""
    original = _resume().model_copy(update={"extracurricular": ["TODO: write this section"]})
    path = tmp_path / "projected.yaml"
    path.write_bytes(resume_document_bytes(original))
    with pytest.raises(MasterResumeError):
        load_resume(path)
