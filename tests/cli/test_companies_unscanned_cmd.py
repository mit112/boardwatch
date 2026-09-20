"""`boardwatch companies unscanned` — the census of boards the store holds but never scans (T142).

The properties that matter, and every one of them is a falsifier astra named: the population is
`watched = 0` AND the provider has a scanner adapter; a provider with no adapter is EXCLUDED
rather than reported as a new bucket; a `source='user'` row is shown but never proposed; one
board is proposed once however many slug cases the store holds it under; and the command
promotes NOTHING — the `companies` table is identical before and after.

`BOARDWATCH_CONFIG_DIR` is pinned in every test, never inherited: `conftest.py` autouses
`BOARDWATCH_DATA_DIR` but deliberately leaves the config dir alone, so without this these tests
would read the operator's real `config.toml`.

Every name here is synthetic (`acme`, "Acme Corp"). No real employer, host or slug appears.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import yaml
from sqlalchemy import insert, select
from typer.testing import CliRunner

from boardwatch.cli.app import app
from boardwatch.providers.registry import PROVIDER_NAMES
from boardwatch.registry.validate import CompanyEntry, validate_entries
from boardwatch.store import tables
from boardwatch.store.db import ensure_schema, get_engine

runner = CliRunner()

#: A provider with no adapter in `providers/`, so a board on it can never be scanned and must
#: never be proposed. Asserted against the registry below rather than assumed.
NO_ADAPTER = "jazzhr"

#: Aggregator placeholders. A `linkedin:` or `indeed:` row is a lane's key for a company, not a
#: board any scanner can read.
PLACEHOLDERS = ("linkedin", "indeed", "jobapps")

_T0 = datetime(2026, 9, 1, 12, 0, 0)


@pytest.fixture(autouse=True)
def _pinned_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOARDWATCH_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)


def _data_dir(tmp_path: Path) -> Path:
    return tmp_path / "data"


def _seed(tmp_path: Path, rows: list[dict[str, object]]) -> dict[str, int]:
    """Insert company rows in the order given (so `id` order is the order written) and return
    each one's id keyed by `provider:slug`."""
    ids: dict[str, int] = {}
    engine = get_engine(_data_dir(tmp_path))
    ensure_schema(engine)
    with engine.begin() as conn:
        for row in rows:
            result = conn.execute(insert(tables.companies).values(**row))
            ids[f"{row['provider']}:{row['slug']}"] = int(result.inserted_primary_key[0])
    engine.dispose()
    return ids


def _seed_postings(tmp_path: Path, company_id: int, count: int, *, first: datetime) -> None:
    engine = get_engine(_data_dir(tmp_path))
    with engine.begin() as conn:
        for n in range(count):
            # `postings.job_id` is NOT NULL by trigger, so every posting needs its canonical job.
            job_id = conn.execute(
                insert(tables.jobs).values(created_at=first)
            ).inserted_primary_key[0]
            conn.execute(
                insert(tables.postings).values(
                    company_id=company_id,
                    job_id=job_id,
                    provider_posting_id=f"p{n}",
                    title="Engineer",
                    normalized_title="engineer",
                    remote_policy="unknown",
                    first_seen_at=first + timedelta(days=n),
                    last_seen_at=first + timedelta(days=n),
                    status="open",
                    content_hash=f"h{n}",
                    body_text="",
                )
            )
    engine.dispose()


def _companies_snapshot(tmp_path: Path) -> list[dict[str, Any]]:
    """Every column of every company row, so a change to `watched` — or to anything else —
    shows up as an inequality."""
    engine = get_engine(_data_dir(tmp_path))
    with engine.connect() as conn:
        rows = [
            dict(row._mapping)
            for row in conn.execute(select(tables.companies).order_by(tables.companies.c.id)).all()
        ]
    engine.dispose()
    return rows


def _cli(tmp_path: Path, args: list[str] | None = None):
    return runner.invoke(
        app, ["--data-dir", str(_data_dir(tmp_path)), "companies", "unscanned", *(args or [])]
    )


def _document(tmp_path: Path) -> tuple[str, list[dict[str, Any]]]:
    """The emitted document and the entries `companies import` would read out of it."""
    result = _cli(tmp_path)
    assert result.exit_code == 0, result.output
    parsed = yaml.safe_load(result.stdout) or {}
    return result.stdout, list(parsed.get("companies") or [])


def _keys(entries: list[dict[str, Any]]) -> list[str]:
    return [f"{e['provider']}:{e['slug']}" for e in entries]


# The six-case fixture astra named, in one store. Written in id order so the case-variant tests
# below can rely on which row is older.
def _six_cases(tmp_path: Path) -> dict[str, int]:
    return _seed(
        tmp_path,
        [
            # 1. unwatched on a scannable provider -> proposed
            {"name": "Acme Corp", "provider": "greenhouse", "slug": "acme",
             "source": "lane", "watched": False},
            # 2. watched on the same provider -> not proposed
            {"name": "Beta Inc", "provider": "greenhouse", "slug": "beta",
             "source": "registry", "watched": True},
            # 3. unwatched on a provider with no adapter -> excluded entirely
            {"name": "Gamma Ltd", "provider": NO_ADAPTER, "slug": "gamma",
             "source": "lane", "watched": False},
            # 4. unwatched aggregator placeholders -> never proposed
            *[
                {"name": f"Delta {p}", "provider": p, "slug": "delta",
                 "source": "lane", "watched": False}
                for p in PLACEHOLDERS
            ],
            # 5. unwatched source='user' -> review-only
            {"name": "Eta Co", "provider": "lever", "slug": "eta",
             "source": "user", "watched": False},
            # 6. case variant of an already-watched board -> proposed zero times
            {"name": "Theta AG", "provider": "ashby", "slug": "Theta",
             "source": "user", "watched": True},
            {"name": "Theta AG", "provider": "ashby", "slug": "theta",
             "source": "lane", "watched": False},
        ],
    )


class TestPopulation:
    def test_the_no_adapter_provider_really_has_no_adapter(self) -> None:
        """The fixture's premise, asserted against the registry rather than assumed: if
        `jazzhr` ever gains an adapter, case 3 stops testing what it claims to."""
        assert NO_ADAPTER not in PROVIDER_NAMES
        for placeholder in PLACEHOLDERS:
            assert placeholder not in PROVIDER_NAMES
        assert "greenhouse" in PROVIDER_NAMES and "lever" in PROVIDER_NAMES

    def test_an_unwatched_scannable_board_is_proposed_exactly_once(self, tmp_path: Path) -> None:
        _six_cases(tmp_path)
        _, entries = _document(tmp_path)
        assert _keys(entries).count("greenhouse:acme") == 1

    def test_a_watched_board_is_not_proposed(self, tmp_path: Path) -> None:
        """The control that stops the census from being 'every company'."""
        _six_cases(tmp_path)
        _, entries = _document(tmp_path)
        assert "greenhouse:beta" not in _keys(entries)

    def test_a_provider_with_no_adapter_is_excluded_and_not_a_new_bucket(
        self, tmp_path: Path
    ) -> None:
        _six_cases(tmp_path)
        document, entries = _document(tmp_path)
        assert f"{NO_ADAPTER}:gamma" not in _keys(entries)
        # Excluded, not bucketed: the provider must not appear anywhere in the document, header
        # included. A "no adapter" section would be a new category for something that can never
        # be watched, which is exactly the out-of-catalog-as-a-bucket failure this repo refuses.
        assert NO_ADAPTER not in document
        assert "Gamma Ltd" not in document

    def test_an_aggregator_placeholder_is_never_proposed(self, tmp_path: Path) -> None:
        _six_cases(tmp_path)
        document, entries = _document(tmp_path)
        for placeholder in PLACEHOLDERS:
            assert f"{placeholder}:delta" not in _keys(entries)
            assert f"Delta {placeholder}" not in document

    def test_a_source_user_row_is_held_back_for_review_and_not_proposed(
        self, tmp_path: Path
    ) -> None:
        _six_cases(tmp_path)
        document, entries = _document(tmp_path)
        assert "lever:eta" not in _keys(entries)
        header = document[: document.index("companies:")]
        assert "HELD BACK FOR REVIEW" in header
        held = header[header.index("HELD BACK FOR REVIEW") :]
        assert "lever:eta" in held and "Eta Co" in held

    def test_a_case_variant_of_a_watched_board_is_proposed_zero_times(
        self, tmp_path: Path
    ) -> None:
        _six_cases(tmp_path)
        _, entries = _document(tmp_path)
        assert [key for key in _keys(entries) if key.lower() == "ashby:theta"] == []

    def test_two_unwatched_case_variants_of_one_board_are_proposed_once(
        self, tmp_path: Path
    ) -> None:
        """The store's own identity is `(provider, slug)` case-folded, so two spellings of one
        unwatched board are one board — and the OLDER row is the one `upsert_watch` lands on."""
        _seed(
            tmp_path,
            [
                {"name": "Iota SA", "provider": "greenhouse", "slug": "Iota",
                 "source": "lane", "watched": False},
                {"name": "Iota SA", "provider": "greenhouse", "slug": "iota",
                 "source": "lane", "watched": False},
            ],
        )
        _, entries = _document(tmp_path)
        assert _keys(entries) == ["greenhouse:Iota"]

    def test_an_unsliced_board_is_not_proposed_beside_its_watched_facet_slice(
        self, tmp_path: Path
    ) -> None:
        """A Workday slice is an in-place narrowing of the watched row, so proposing the whole
        board would re-add everything the slice was made to exclude."""
        _seed(
            tmp_path,
            [
                {"name": "Kappa", "provider": "workday",
                 "slug": "kappa.wd5.myworkdayjobs.com/kappa/KappaCareers#jobFamilyGroup=Technology",
                 "source": "user", "watched": True},
                {"name": "Kappa", "provider": "workday",
                 "slug": "kappa.wd5.myworkdayjobs.com/kappa/KappaCareers",
                 "source": "lane", "watched": False},
            ],
        )
        _, entries = _document(tmp_path)
        assert _keys(entries) == []

    def test_a_sibling_slice_of_a_watched_slice_is_still_its_own_board(
        self, tmp_path: Path
    ) -> None:
        """One direction only: a slug that CARRIES a fragment is matched exactly, because a
        second `#group=` on the same board is a deliberate second board, not a case variant."""
        _seed(
            tmp_path,
            [
                {"name": "Kappa", "provider": "workday",
                 "slug": "kappa.wd5.myworkdayjobs.com/kappa/KappaCareers#jobFamilyGroup=Technology",
                 "source": "user", "watched": True},
                {"name": "Kappa", "provider": "workday",
                 "slug": "kappa.wd5.myworkdayjobs.com/kappa/KappaCareers#jobFamilyGroup=Finance",
                 "source": "lane", "watched": False},
            ],
        )
        _, entries = _document(tmp_path)
        assert _keys(entries) == [
            "workday:kappa.wd5.myworkdayjobs.com/kappa/KappaCareers#jobFamilyGroup=Finance"
        ]


class TestProvenance:
    def test_each_row_carries_its_posting_count_and_first_seen_date(
        self, tmp_path: Path
    ) -> None:
        ids = _six_cases(tmp_path)
        _seed_postings(tmp_path, ids["greenhouse:acme"], 3, first=_T0)
        document, _ = _document(tmp_path)
        line = next(ln for ln in document.splitlines() if "greenhouse:acme" in ln)
        assert "Acme Corp" in line
        assert "3 posting(s)" in line
        assert str(_T0) in line
        assert "source=lane" in line

    def test_a_board_with_no_posting_at_all_is_reported_as_never_seen(
        self, tmp_path: Path
    ) -> None:
        """Not filtered out: 'recorded but never actually observed' is the reviewer's cue that
        the slug may be wrong, and dropping the row would hide exactly that."""
        _six_cases(tmp_path)
        document, entries = _document(tmp_path)
        line = next(ln for ln in document.splitlines() if "greenhouse:acme" in ln)
        assert "0 posting(s)" in line
        assert "first seen never" in line
        assert "greenhouse:acme" in _keys(entries)


class TestItPromotesNothing:
    def test_the_companies_table_is_unchanged_by_the_census(self, tmp_path: Path) -> None:
        """The test that pins 'this command promotes nothing' — every column of every row,
        `watched` included."""
        ids = _six_cases(tmp_path)
        _seed_postings(tmp_path, ids["greenhouse:acme"], 2, first=_T0)
        before = _companies_snapshot(tmp_path)
        result = _cli(tmp_path)
        assert result.exit_code == 0, result.output
        assert _companies_snapshot(tmp_path) == before
        assert [row["watched"] for row in before] == [row["watched"] for row in before]
        assert sum(1 for row in before if row["watched"]) == 2

    def test_writing_the_file_also_leaves_the_store_alone(self, tmp_path: Path) -> None:
        _six_cases(tmp_path)
        before = _companies_snapshot(tmp_path)
        target = tmp_path / "candidates.yaml"
        result = _cli(tmp_path, ["--out", str(target)])
        assert result.exit_code == 0, result.output
        assert _companies_snapshot(tmp_path) == before
        flat = " ".join(result.stdout.split())
        assert "Wrote 1 candidate board(s)" in flat
        assert "1 source=user row(s) held back for review" in flat
        assert "companies:" in target.read_text(encoding="utf-8")


class TestTheFileTheImporterReads:
    def test_the_document_validates_as_the_registry_format(self, tmp_path: Path) -> None:
        """`companies import` is the only admission route, so the file has to survive its
        validator — including the provider check, which is the registry's own catalog."""
        _six_cases(tmp_path)
        _, entries = _document(tmp_path)
        validated = validate_entries([CompanyEntry.model_validate(e) for e in entries])
        assert [e.slug for e in validated] == ["acme"]
        assert [e.name for e in validated] == ["Acme Corp"]

    def test_the_header_records_the_adapter_set_it_selected_on(self, tmp_path: Path) -> None:
        _six_cases(tmp_path)
        document, _ = _document(tmp_path)
        header = document[: document.index("companies:")]
        for provider in PROVIDER_NAMES:
            assert provider in header

    def test_an_empty_census_still_emits_an_importable_document(self, tmp_path: Path) -> None:
        _seed(
            tmp_path,
            [{"name": "Beta Inc", "provider": "greenhouse", "slug": "beta",
              "source": "registry", "watched": True}],
        )
        document, entries = _document(tmp_path)
        assert entries == []
        assert "No unscanned board to propose" in document

    def test_a_newline_in_a_stored_name_cannot_forge_a_header_line(self, tmp_path: Path) -> None:
        """Lane-written names are third-party text. A newline in one would end the `#` comment
        and let the remainder parse as a top-level YAML key."""
        _seed(
            tmp_path,
            [{"name": "Acme\nevil: pwned", "provider": "greenhouse", "slug": "acme",
              "source": "lane", "watched": False}],
        )
        result = _cli(tmp_path)
        assert result.exit_code == 0, result.output
        parsed = yaml.safe_load(result.stdout)
        assert set(parsed) == {"companies"}


def test_no_store_means_a_named_error_not_a_traceback(tmp_path: Path) -> None:
    result = _cli(tmp_path)
    assert result.exit_code == 1
    assert "no companies table" in result.output


class TestTheImportRoundTrip:
    """The file has to be admissible by `companies import`, which is the only admission route."""

    def test_a_slug_the_importer_refuses_is_shown_and_does_not_poison_the_file(
        self, tmp_path: Path
    ) -> None:
        """A candidate slug is whatever a LANE wrote into the store, not this command's own
        output. `companies import` parses every entry before it writes anything, so one
        unparseable slug aborts the import for the whole file."""
        _seed(
            tmp_path,
            [
                {"name": "Acme Corp", "provider": "greenhouse", "slug": "acme",
                 "source": "lane", "watched": False},
                # A workday slug is a host/tenant/site triple; a bare token is not one.
                {"name": "Mu Group", "provider": "workday", "slug": "mu",
                 "source": "lane", "watched": False},
            ],
        )
        document, entries = _document(tmp_path)
        assert _keys(entries) == ["greenhouse:acme"]
        header = document[: document.index("companies:")]
        assert "UNIMPORTABLE" in header
        refused = header[header.index("UNIMPORTABLE") :]
        assert "workday:mu" in refused
        assert "expected host/tenant/site" in refused
        # And the file it did emit is the one the importer accepts.
        validate_entries([CompanyEntry.model_validate(e) for e in entries])

    def test_importing_the_emitted_file_watches_the_proposals_and_nothing_else(
        self, tmp_path: Path
    ) -> None:
        """End to end through a DIFFERENT path than the one that produced the file: the census
        writes it, `companies import` reads it, and only the proposed boards end up watched."""
        _seed(
            tmp_path,
            [
                {"name": "Acme Corp", "provider": "greenhouse", "slug": "acme",
                 "source": "lane", "watched": False},
                {"name": "Nu Labs", "provider": "workday",
                 "slug": "nu.wd5.myworkdayjobs.com/nu/NuCareers", "source": "lane",
                 "watched": False},
                {"name": "Eta Co", "provider": "lever", "slug": "eta",
                 "source": "user", "watched": False},
                {"name": "Gamma Ltd", "provider": NO_ADAPTER, "slug": "gamma",
                 "source": "lane", "watched": False},
            ],
        )
        target = tmp_path / "candidates.yaml"
        assert _cli(tmp_path, ["--out", str(target)]).exit_code == 0

        imported = runner.invoke(
            app, ["--data-dir", str(_data_dir(tmp_path)), "companies", "import", str(target)]
        )
        assert imported.exit_code == 0, imported.output

        watched = {
            f"{row['provider']}:{row['slug']}"
            for row in _companies_snapshot(tmp_path)
            if row["watched"]
        }
        assert watched == {
            "greenhouse:acme",
            "workday:nu.wd5.myworkdayjobs.com/nu/NuCareers",
        }
