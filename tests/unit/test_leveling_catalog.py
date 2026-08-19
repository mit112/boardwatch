from pathlib import Path

import pytest

from boardwatch.rank.leveling import (
    LEVELING_VERSION,
    LevelingError,
    load_bindings,
    load_leveling,
)


def test_bundled_catalog_loads_and_pins_its_version(tmp_path: Path) -> None:
    catalog = load_leveling(tmp_path)
    assert catalog.version == LEVELING_VERSION
    assert catalog.digest  # content-addressed, for policy_version


def test_software_field_tier_carries_the_measured_words(tmp_path: Path) -> None:
    words = load_leveling(tmp_path).fields["software"].words
    assert words["senior"] == "senior"
    assert words["leader"] == "senior"        # required: `Lead` c `Leader` (spec 3.5)
    assert words["distinguished"] == "staff_plus"
    assert words["vice president"] == "staff_plus"
    # Measured false drop: `fellow` kills early-career fellowships (spec 3.4).
    assert "fellow" not in words
    # Dropped as ambiguous or field-inverting.
    for absent in ("architect", "specialist", "associate", "expert", "advanced", "master"):
        assert absent not in words


def test_bare_letter_grammars_are_declared_ambiguous(tmp_path: Path) -> None:
    catalog = load_leveling(tmp_path)
    assert "l_prefix" in catalog.ambiguous_grammars
    assert "e_prefix" in catalog.ambiguous_grammars
    assert "level_n" not in catalog.ambiguous_grammars


def test_no_company_name_appears_in_the_shipped_catalog(tmp_path: Path) -> None:
    """Shipped data must contain zero company names (spec 2.1); bindings are user config."""
    from importlib.resources import files

    text = (files("boardwatch.rank") / "leveling.yaml").read_text(encoding="utf-8").lower()
    for company in ("snap", "twilio", "google", "meta", "amazon", "microsoft", "cisco"):
        assert company not in text


def _write(tmp_path: Path, body: str) -> Path:
    (tmp_path / "leveling.yaml").write_text(body, encoding="utf-8")
    return tmp_path


def test_out_of_catalog_band_raises_rather_than_bucketing(tmp_path: Path) -> None:
    cfg = _write(tmp_path, """
leveling_version: 1
grammars: {level_n: {kind: self_describing}}
schemes: {s: {grammar: level_n, levels: {"5": archmage}}}
fields: {software: {words: {}, roman: {}}}
""")
    with pytest.raises(LevelingError, match="archmage"):
        load_leveling(cfg)


def test_unquoted_yaml_boolean_level_key_raises(tmp_path: Path) -> None:
    """YAML 1.1: an unquoted `no`/`on`/`y` loads as a bool and becomes a plausible token."""
    cfg = _write(tmp_path, """
leveling_version: 1
grammars: {level_n: {kind: self_describing}}
schemes: {s: {grammar: level_n, levels: {no: senior}}}
fields: {software: {words: {}, roman: {}}}
""")
    with pytest.raises(LevelingError, match="QUOTE"):
        load_leveling(cfg)


def test_version_mismatch_raises(tmp_path: Path) -> None:
    cfg = _write(tmp_path, """
leveling_version: 99
grammars: {}
schemes: {}
fields: {software: {words: {}, roman: {}}}
""")
    with pytest.raises(LevelingError, match="99"):
        load_leveling(cfg)


def test_scheme_naming_an_unknown_grammar_raises(tmp_path: Path) -> None:
    cfg = _write(tmp_path, """
leveling_version: 1
grammars: {level_n: {kind: self_describing}}
schemes: {s: {grammar: nonesuch, levels: {"5": senior}}}
fields: {software: {words: {}, roman: {}}}
""")
    with pytest.raises(LevelingError, match="nonesuch"):
        load_leveling(cfg)


def test_bindings_default_to_empty(tmp_path: Path) -> None:
    assert load_bindings(tmp_path) == {}


def test_bindings_are_keyed_on_provider_and_slug(tmp_path: Path) -> None:
    (tmp_path / "leveling-bindings.yaml").write_text(
        'bindings:\n'
        '  - provider: workday\n'
        '    slug: snapchat.wd1.myworkdayjobs.com/snapchat/snap\n'
        '    scheme: ic_1_to_7\n',
        encoding="utf-8",
    )
    got = load_bindings(tmp_path)
    assert got == {("workday", "snapchat.wd1.myworkdayjobs.com/snapchat/snap"): "ic_1_to_7"}


class TestFailDirectionIsPerGate:
    """A broken override raises; broken bindings degrade loudly. Deliberately different."""

    def test_a_catalog_missing_the_software_tier_raises_typed(self, tmp_path: Path) -> None:
        # Otherwise it loads fine and KeyErrors at four call sites, the 8 AM run included.
        cfg = _write(tmp_path, """
leveling_version: 1
grammars: {}
schemes: {}
fields: {nursing: {words: {}, roman: {}}}
""")
        with pytest.raises(LevelingError, match="software"):
            load_leveling(cfg)

    def test_structurally_broken_bindings_degrade_instead_of_raising(self, tmp_path: Path) -> None:
        """Bindings only ever turn an abstain into a drop, so losing them cannot hide a job."""
        from boardwatch.rank.leveling import resolve_schemes

        (tmp_path / "leveling-bindings.yaml").write_text(
            "bindings:\n  provider: workday\n", encoding="utf-8"
        )
        schemes, warning = resolve_schemes(load_leveling(tmp_path), tmp_path)
        assert schemes == {}
        assert warning is not None and "unusable" in warning

    def test_an_unknown_scheme_name_is_ignored_with_a_warning(self, tmp_path: Path) -> None:
        from boardwatch.rank.leveling import resolve_schemes

        (tmp_path / "leveling-bindings.yaml").write_text(
            "bindings:\n  - provider: workday\n    slug: s\n    scheme: nope\n", encoding="utf-8"
        )
        schemes, warning = resolve_schemes(load_leveling(tmp_path), tmp_path)
        assert schemes == {}
        assert warning is not None and "nope" in warning

    def test_a_valid_binding_resolves_to_a_scheme_object(self, tmp_path: Path) -> None:
        from boardwatch.rank.leveling import resolve_schemes

        (tmp_path / "leveling-bindings.yaml").write_text(
            "bindings:\n  - provider: workday\n    slug: s\n    scheme: ic_1_to_7\n",
            encoding="utf-8",
        )
        schemes, warning = resolve_schemes(load_leveling(tmp_path), tmp_path)
        assert warning is None
        assert schemes[("workday", "s")].name == "ic_1_to_7"
