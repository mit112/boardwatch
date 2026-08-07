"""One canonical JSON form backs all three hashes, matching the shape at
extract/taxonomy.py:95-103. Formatting and key order must never change a hash;
content always must."""

from pathlib import Path

import pytest

from boardwatch.eligibility.catalog import load_rules
from boardwatch.eligibility.facts import ClearanceFact, Facts, Policy, WorkAuthFact
from boardwatch.eligibility.hashing import (
    IdentityMismatchError,
    build_identity,
    canonical,
    digest,
    verify_identity,
)
from boardwatch.eligibility.resolve import declared_fields


def test_key_order_never_changes_the_canonical_form() -> None:
    assert canonical({"b": 1, "a": 2}) == canonical({"a": 2, "b": 1}) == '{"a":2,"b":1}'


def test_canonical_form_is_compact() -> None:
    assert canonical({"a": [1, 2]}) == '{"a":[1,2]}'


def test_nested_key_order_never_changes_the_canonical_form() -> None:
    left = {"outer": {"z": 1, "a": {"q": 2, "b": 3}}}
    right = {"outer": {"a": {"b": 3, "q": 2}, "z": 1}}
    assert canonical(left) == canonical(right)


def test_digest_is_stable_across_calls() -> None:
    assert digest({"a": 1}) == digest({"a": 1})


def test_digest_changes_on_content() -> None:
    assert digest({"a": 1}) != digest({"a": 2})


def test_digest_distinguishes_null_from_absent() -> None:
    """A vanishing key must not collide with an explicit null, or "fact never set" and
    "fact set then cleared" become the same fingerprint."""
    assert digest({"a": None}) != digest({})


def test_digest_is_hex_sha256() -> None:
    value = digest({"a": 1})
    assert len(value) == 64
    assert set(value) <= set("0123456789abcdef")


def test_list_order_does_change_the_canonical_form() -> None:
    """Only MAPPING key order is insignificant. A list is ordered data, so reordering it
    is a content change and must move the hash, or a reordered evidence span list would
    silently reuse a stale fingerprint."""
    assert canonical({"a": [1, 2]}) != canonical({"a": [2, 1]})
    assert digest({"a": [1, 2]}) != digest({"a": [2, 1]})


def test_digest_distinguishes_string_from_number() -> None:
    """`1` and `"1"` are different facts. json.dumps keeps them apart, and this pins it so
    a future switch to a stringifying serialiser cannot collapse them unnoticed."""
    assert digest({"a": 1}) != digest({"a": "1"})


def test_canonical_rejects_a_non_string_mapping_key() -> None:
    """The same collision one level up from the value test above: JSON stringifies keys,
    so {1: x} and {"1": x} canonicalise identically and two distinct snapshots could share
    a hash. This boundary refuses the ambiguous input rather than trusting it; every real
    snapshot key is already a string."""
    with pytest.raises(TypeError):
        canonical({1: "x"})
    with pytest.raises(TypeError):
        canonical({"outer": {2: "x"}})  # the collision must be refused when nested too
    with pytest.raises(TypeError):
        digest({1: "x"})


def test_canonical_allows_string_keyed_nesting_inside_lists() -> None:
    """Positive control: the guard must not over-reject legitimate string-keyed structures
    nested inside lists, which the facts payload produces."""
    assert canonical({"a": [{"b": 1}], "c": {"d": 2}}) == '{"a":[{"b":1}],"c":{"d":2}}'


# Every family's resolver declares its inputs STATICALLY. The degree resolver declares
# total_years_experience as well as highest_degree, because a measurable OR-alternative
# reads it (D-P2-23).
DECLARED = {
    "work_auth": ("work_authorization",),
    "experience_years": ("total_years_experience",),
    "clearance": ("security_clearance",),
    "degree": ("highest_degree", "total_years_experience"),
    "contract_not_fte": ("employment_type_preference",),
    "internship": ("internship_preference",),
}

FACTS = Facts(
    work_authorization=WorkAuthFact(status="citizen", jurisdiction="us"),
    total_years_experience=8,
    security_clearance=ClearanceFact(scheme="us_dod", level="secret", state="active"),
    highest_degree="bachelor",
)


def _identity(tmp_path: Path, **kwargs: object):
    args: dict[str, object] = {
        "posting_version_id": 1, "facts": FACTS, "policy": Policy(),
        "catalog": load_rules(tmp_path), "declared_fields": DECLARED,
    }
    args.update(kwargs)
    return build_identity(**args)  # type: ignore[arg-type]


def test_the_snapshot_is_byte_identical_to_the_hashed_payload(tmp_path: Path) -> None:
    """D-P2-14. _get_or_create_input keeps the FIRST snapshot for a fingerprint and
    validates nothing, so a snapshot broader than its hashed payload records an audit row
    that cannot reproduce its own hash."""
    identity = _identity(tmp_path)
    assert digest(identity.profile_snapshot) == identity.profile_hash
    assert digest(identity.rules_snapshot) == identity.rules_hash
    verify_identity(identity, posting_version_id=1)


def test_verify_rejects_a_tampered_profile_snapshot(tmp_path: Path) -> None:
    identity = _identity(tmp_path)
    broken = type(identity)(
        profile_hash=identity.profile_hash,
        profile_snapshot={"fields": {"highest_degree": "doctorate"}},
        rules_hash=identity.rules_hash,
        rules_snapshot=identity.rules_snapshot,
        input_fingerprint=identity.input_fingerprint,
    )
    with pytest.raises(IdentityMismatchError, match="profile"):
        verify_identity(broken, posting_version_id=1)


def test_verify_rejects_a_fingerprint_for_a_different_posting_version(tmp_path: Path) -> None:
    identity = _identity(tmp_path)
    with pytest.raises(IdentityMismatchError, match="fingerprint"):
        verify_identity(identity, posting_version_id=2)


def test_the_fingerprint_is_sensitive_to_the_posting_version(tmp_path: Path) -> None:
    a = _identity(tmp_path, posting_version_id=1)
    b = _identity(tmp_path, posting_version_id=2)
    assert a.input_fingerprint != b.input_fingerprint
    assert a.profile_hash == b.profile_hash  # only the version differs


def test_the_fingerprint_is_sensitive_to_a_fact_change(tmp_path: Path) -> None:
    a = _identity(tmp_path)
    b = _identity(tmp_path, facts=FACTS.model_copy(update={"highest_degree": "master"}))
    assert a.profile_hash != b.profile_hash
    assert a.input_fingerprint != b.input_fingerprint


def test_the_fingerprint_is_sensitive_to_a_sub_field_of_a_structured_fact(
    tmp_path: Path,
) -> None:
    """P2a: `needs_sponsorship` is a nested field on `WorkAuthFact`, not a new top-level
    Facts field, so nothing in declared_fields or the resolver's `inputs` names it directly.
    It only re-keys the hash because facts_payload dumps the WHOLE work_authorization object
    and declared_fields["work_auth"] names that object wholesale (hashing.py:84-92). That
    mechanism is unlocked by reasoning about the code, not by a test, until now: every other
    hash-sensitivity test here varies a top-level scalar fact, never a sub-field of a
    structured one, so a change that accidentally narrowed the snapshot to named sub-fields
    (dropping this one) would pass every existing test in this module."""
    varying = FACTS.model_copy(
        update={"work_authorization": FACTS.work_authorization.model_copy(  # type: ignore[union-attr]
            update={"needs_sponsorship": False}
        )}
    )
    a = _identity(tmp_path)
    b = _identity(tmp_path, facts=varying)
    assert a.profile_hash != b.profile_hash
    assert a.input_fingerprint != b.input_fingerprint
    # And a second, different bit value re-keys again, distinct from both `a` and `None`.
    varying_true = FACTS.model_copy(
        update={"work_authorization": FACTS.work_authorization.model_copy(  # type: ignore[union-attr]
            update={"needs_sponsorship": True}
        )}
    )
    c = _identity(tmp_path, facts=varying_true)
    assert c.profile_hash not in (a.profile_hash, b.profile_hash)


def test_the_fingerprint_is_sensitive_to_a_policy_change(tmp_path: Path) -> None:
    a = _identity(tmp_path)
    b = _identity(tmp_path, policy=Policy(families={"degree": "blocker"}))
    assert a.rules_hash != b.rules_hash
    assert a.input_fingerprint != b.input_fingerprint


def test_a_policy_that_restates_the_catalog_default_does_not_re_key(tmp_path: Path) -> None:
    """The map is MATERIALISED before hashing, so an empty map and a map that spells out
    the defaults are one fingerprint for identical behaviour (D-P2-2)."""
    catalog = load_rules(tmp_path)
    spelled_out = Policy(
        families={f.id: f.default_policy for f in catalog.families}  # type: ignore[misc]
    )
    assert _identity(tmp_path).rules_hash == _identity(tmp_path, policy=spelled_out).rules_hash


def test_the_fingerprint_is_sensitive_to_catalog_content(tmp_path: Path) -> None:
    override = tmp_path / "cfg"
    override.mkdir()
    (override / "rules.yaml").write_text(
        (Path("src/boardwatch/eligibility/rules.yaml").read_text(encoding="utf-8")).replace(
            "version: 1", "version: 2", 1
        ),
        encoding="utf-8",
    )
    assert _identity(tmp_path).rules_hash != _identity(
        tmp_path, catalog=load_rules(override)
    ).rules_hash


def test_catalog_source_is_part_of_the_rules_hash(tmp_path: Path) -> None:
    """An override with IDENTICAL content is a different trust position and must not
    collide with the bundled catalog (spec §4.5)."""
    override = tmp_path / "cfg"
    override.mkdir()
    (override / "rules.yaml").write_text(
        Path("src/boardwatch/eligibility/rules.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    bundled, overridden = load_rules(tmp_path), load_rules(override)
    assert bundled.version == overridden.version  # identical content
    assert bundled.source != overridden.source
    assert _identity(tmp_path, catalog=bundled).rules_hash != _identity(
        tmp_path, catalog=overridden
    ).rules_hash


def test_a_statically_declared_but_unconsumed_field_still_re_keys(tmp_path: Path) -> None:
    """D-P2-23. The degree resolver DECLARES total_years_experience, so editing it
    re-keys even when no degree detection consumed it. The alternative, hashing only
    what a prior run happened to read, meant a user adding equivalent experience never
    triggered the re-evaluation that would have used it."""
    a = _identity(tmp_path, policy=Policy(families={"experience_years": "ignore"}))
    b = _identity(
        tmp_path,
        facts=FACTS.model_copy(update={"total_years_experience": 12}),
        policy=Policy(families={"experience_years": "ignore"}),
    )
    assert a.profile_hash != b.profile_hash


def test_an_ignored_family_drops_its_declared_fields_from_the_hash(tmp_path: Path) -> None:
    a = _identity(tmp_path)
    b = _identity(tmp_path, policy=Policy(families={"clearance": "ignore"}))
    assert a.profile_hash != b.profile_hash
    assert "security_clearance" not in b.profile_snapshot["fields"]  # type: ignore[operator]


def test_ranking_only_profile_fields_are_never_hashed(tmp_path: Path) -> None:
    """Rev 1 hashed six ranking-only fields no resolver reads, so editing exclude_titles,
    or any pattern in taxonomy.yaml, re-keyed and re-evaluated the entire corpus."""
    fields = _identity(tmp_path).profile_snapshot["fields"]
    assert set(fields) == {  # type: ignore[arg-type]
        "work_authorization", "total_years_experience", "security_clearance", "highest_degree",
        "employment_type_preference", "internship_preference",
    }


def test_the_declared_map_in_this_module_matches_the_real_registry() -> None:
    """DECLARED above is a hand-written copy, and every test here feeds it to
    build_identity instead of the registry. P9 proved that is a SILENT drift class: two
    families were added with resolvers and Facts fields, and every hashing test kept passing
    while hashing four families' inputs out of six. A stale copy under-tests the profile hash
    rather than failing, so the copy is pinned to the registry here.
    """
    assert DECLARED == declared_fields()


def test_the_snapshot_does_not_embed_the_catalog(tmp_path: Path) -> None:
    """D-P2-21. catalog_version is a sha256 over the whole document, so it pins the
    catalog exactly; copying it into every input row would be 10,000 copies at corpus
    scale to recover what the hash already carries."""
    snapshot = _identity(tmp_path).rules_snapshot
    assert set(snapshot) == {"catalog_version", "catalog_source", "policy"}
