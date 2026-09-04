"""`run_tailor` validating and recording a PROJECTED résumé's lineage (P5a task 6).

A projected master's provenance has to be *detected*, not merely inspectable: the pipeline hands
`run_tailor` a file plus the `ResumeSourceLineage` the projection recorded, and this module pins
that (a) a lineage that does not describe the handed-over file refuses the lead before anything is
rendered, and (b) a lineage that does describe it lands on the `resume_tailored` row, in the same
transaction as the artifact.

Fixtures are seeded directly through the store, mirroring tests/unit/test_reports_tailor.py's
_settings/_engine/_seed helpers rather than inventing a conftest fixture.
"""

from __future__ import annotations

import dataclasses
import hashlib
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import Engine, insert, select

from boardwatch.core.lineage import ResumeSourceLineage
from boardwatch.core.settings import Settings
from boardwatch.extract.taxonomy import load_taxonomy
from boardwatch.reports import tailor as tailor_mod
from boardwatch.reports.tailor import ResumeLineageMismatch, run_tailor
from boardwatch.store.db import ensure_schema, get_engine
from boardwatch.store.tables import (
    artifacts,
    companies,
    extractions,
    jobs,
    posting_versions,
    postings,
)
from boardwatch.tailor import load as load_mod
from boardwatch.tailor.equivalences import load_equivalences
from boardwatch.tailor.load import load_resume, scaffold_template
from boardwatch.tailor.persona import load_personas
from boardwatch.tailor.render.outcome import CompileOutcome, CompileReason
from tests.conftest import write_test_resume_template

NOW = datetime(2026, 8, 17, 12, 0, 0)


def _settings(tmp_path: Path) -> Settings:
    config_dir = tmp_path / "cfg"
    config_dir.mkdir(parents=True, exist_ok=True)
    # T2: `resolve_template` no longer falls back to the bundled default for a real config
    # dir missing `resume_template.tex`, and rendering here goes through the real
    # `LatexRenderer(config_dir=settings.config_dir)` — so this environment needs one on
    # disk, as a properly set-up user's config dir would.
    write_test_resume_template(config_dir)
    return Settings(data_dir=tmp_path / "data", config_dir=config_dir)


def _engine(settings: Settings) -> Engine:
    engine = get_engine(settings.data_dir)
    ensure_schema(engine)
    return engine


def _seed(engine: Engine, settings: Settings, *, slug: str = "acme") -> int:
    """Insert company+job+posting+version+extraction; return posting_id."""
    body = "Python JavaScript backend services"
    content_hash = "h1"
    with engine.begin() as conn:
        company_id = int(
            conn.execute(
                insert(companies).values(
                    name=slug, provider="greenhouse", slug=slug, source="user", watched=True
                )
            ).inserted_primary_key[0]
        )
        job_id = int(conn.execute(insert(jobs).values(created_at=NOW)).inserted_primary_key[0])
        posting_id = int(
            conn.execute(
                insert(postings).values(
                    company_id=company_id, job_id=job_id, provider_posting_id=f"pp-{slug}",
                    title="Backend Engineer", normalized_title="backend engineer",
                    url=f"https://example.test/{slug}", locations_json=["Remote"],
                    remote_policy="remote", posted_at=NOW, first_seen_at=NOW, last_seen_at=NOW,
                    status="open", consecutive_missing=0, content_hash=content_hash,
                    body_text=body,
                )
            ).inserted_primary_key[0]
        )
        conn.execute(
            insert(posting_versions).values(
                posting_id=posting_id, content_hash=content_hash, body_text=body,
                captured_at=NOW, capture_reason="new",
            )
        )
        conn.execute(
            insert(extractions).values(
                posting_id=posting_id, content_hash=content_hash, kind="taxonomy",
                engine_version=load_taxonomy(settings.config_dir).version,
                json={"skills": ["Python", "JavaScript"]}, created_at=NOW,
            )
        )
    return posting_id


def _version_id(engine: Engine, posting_id: int) -> int:
    with engine.connect() as conn:
        return int(
            conn.execute(
                select(posting_versions.c.id).where(posting_versions.c.posting_id == posting_id)
            ).scalar_one()
        )


class _Runner:
    """A compile runner that records every invocation, so "refused before rendering" is asserted
    on an observed absence of compiles rather than inferred from the exception alone."""

    def __init__(self) -> None:
        self.calls: list[Path] = []

    def __call__(self, typ: Path, pdf: Path) -> CompileOutcome:
        self.calls.append(typ)
        pdf.write_bytes(b"%PDF")
        return CompileOutcome(CompileReason.OK, pdf, 1, "ok")


def _projected(tmp_path: Path) -> Path:
    """Stands in for `resume.projected.yaml`: bytes published by the projection, which the
    tailor is handed rather than authoring."""
    path = tmp_path / "resume.projected.yaml"
    path.write_text(scaffold_template(), encoding="utf-8")
    return path


def _lineage(path: Path, posting_version_id: int, settings: Settings) -> ResumeSourceLineage:
    """The lineage the projection would have recorded for `path`. Both hashes are computed the
    way `boardwatch.projection.run` computes them — sha256 over the published bytes, and sha256
    over `model_dump_json()` of the model those bytes parse to.

    The three transformation versions are RESOLVED from the same loaders `resolve_projection_run`
    calls, never spelled as literals. They used to be `"tax-1"`/`"eq-1"`/`"pr-1"`, which is what a
    projection whose taxonomy, equivalence table and persona registry had all been replaced would
    have recorded — and every test in this file passed, because nothing compared them. Deriving
    them is what makes the three mutation tests below able to fail for the reason they name (D-142).
    """
    return ResumeSourceLineage(
        kind="projection",
        bundle_revision="21",
        bundle_digest="b" * 64,
        projection_digest="p" * 64,
        posting_version_id=posting_version_id,
        as_of="2026-08-17T12:00:00",
        scorer_id="mean_per_bullet",
        taxonomy_version=load_taxonomy(settings.config_dir).version,
        equivalence_version=load_equivalences().version,
        persona_registry_version=load_personas(settings.config_dir).version,
        resume_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        resume_model_sha256=hashlib.sha256(
            load_resume(path).model_dump_json().encode("utf-8")
        ).hexdigest(),
        manifest_schema=1,
    )


def test_lineage_lands_on_the_tailored_row(tmp_path: Path) -> None:
    """Not on resume_master: that node is content-addressed and reused, and its metadata is
    written only on first creation, so lineage there would be attributed to whichever run
    happened to create the master first."""
    settings = _settings(tmp_path)
    engine = _engine(settings)
    pid = _seed(engine, settings)
    projected = _projected(tmp_path)
    lineage = _lineage(projected, _version_id(engine, pid), settings)

    res = run_tailor(
        engine, settings, pid, resume_path=projected, out_dir=tmp_path / "out",
        typst_runner=_Runner(), source_lineage=lineage,
    )

    assert res.tailored_artifact_id is not None
    with engine.connect() as conn:
        rows = conn.execute(artifacts.select()).fetchall()
    tailored = next(r for r in rows if r.kind == "resume_tailored")
    meta = tailored.meta_json
    assert meta["projection_bundle_revision"] == "21"
    assert meta["projection_kind"] == "projection"
    assert meta["projection_posting_version_id"] == lineage.posting_version_id
    assert meta["projection_resume_sha256"] == lineage.resume_sha256
    # Every field, not a sample: a lineage that dropped a transformation version on the way to
    # the row would still satisfy the four assertions above.
    assert lineage.as_meta().items() <= meta.items()
    # The pre-existing tailoring keys survive the merge.
    assert meta["master_content_hash"] and meta["posting_version_id"] == lineage.posting_version_id


def test_lineage_is_not_written_to_the_master_row(tmp_path: Path) -> None:
    """The master row is shared across runs and postings; a projection_* key there would claim
    one posting's projection describes every later tailoring of the same master."""
    settings = _settings(tmp_path)
    engine = _engine(settings)
    pid = _seed(engine, settings)
    projected = _projected(tmp_path)

    run_tailor(
        engine, settings, pid, resume_path=projected, out_dir=tmp_path / "out",
        typst_runner=_Runner(), source_lineage=_lineage(projected, _version_id(engine, pid), settings),
    )

    with engine.connect() as conn:
        rows = conn.execute(artifacts.select()).fetchall()
    master = next(r for r in rows if r.kind == "resume_master")
    assert [k for k in master.meta_json if k.startswith("projection_")] == []


def test_a_hash_mismatch_refuses_before_rendering(tmp_path: Path) -> None:
    """The check must be able to fail. A lineage whose hash does not match the file handed over
    is exactly the manifest-B-with-resume-A case."""
    settings = _settings(tmp_path)
    engine = _engine(settings)
    pid = _seed(engine, settings)
    projected = _projected(tmp_path)
    wrong = dataclasses.replace(
        _lineage(projected, _version_id(engine, pid), settings), resume_sha256="0" * 64
    )
    runner = _Runner()

    with pytest.raises(ResumeLineageMismatch):
        run_tailor(
            engine, settings, pid, resume_path=projected, out_dir=tmp_path / "out",
            typst_runner=runner, source_lineage=wrong,
        )

    assert runner.calls == []  # refused before any render
    with engine.connect() as conn:
        assert conn.execute(artifacts.select()).first() is None


def test_a_swapped_file_is_refused_even_though_it_loads(tmp_path: Path) -> None:
    """The realistic shape of the byte check: the lineage is honest, the file underneath it moved.
    A perfectly valid résumé that is not the projected one must still be refused."""
    settings = _settings(tmp_path)
    engine = _engine(settings)
    pid = _seed(engine, settings)
    projected = _projected(tmp_path)
    lineage = _lineage(projected, _version_id(engine, pid), settings)
    projected.write_text(
        scaffold_template().replace("Ada Lovelace", "Grace Hopper"), encoding="utf-8"
    )
    assert load_resume(projected).header[0] == "Grace Hopper"  # still a loadable master

    with pytest.raises(ResumeLineageMismatch):
        run_tailor(
            engine, settings, pid, resume_path=projected, out_dir=tmp_path / "out",
            typst_runner=_Runner(), source_lineage=lineage,
        )


def test_a_posting_version_change_refuses(tmp_path: Path) -> None:
    """Selection ran against version A; if tailoring resolves version B the lead is refused."""
    settings = _settings(tmp_path)
    engine = _engine(settings)
    pid = _seed(engine, settings)
    projected = _projected(tmp_path)
    lineage = _lineage(projected, _version_id(engine, pid), settings)
    stale = dataclasses.replace(lineage, posting_version_id=lineage.posting_version_id - 1)
    runner = _Runner()

    with pytest.raises(ResumeLineageMismatch):
        run_tailor(
            engine, settings, pid, resume_path=projected, out_dir=tmp_path / "out",
            typst_runner=runner, source_lineage=stale,
        )

    assert runner.calls == []
    with engine.connect() as conn:
        assert conn.execute(artifacts.select()).first() is None


def test_a_model_hash_mismatch_refuses(tmp_path: Path) -> None:
    """The second hash is not redundant with the first: matching bytes that parse to a different
    model than the projection recorded means the two ends disagree about the document, which is a
    loader/schema divergence, not a swapped file."""
    settings = _settings(tmp_path)
    engine = _engine(settings)
    pid = _seed(engine, settings)
    projected = _projected(tmp_path)
    wrong = dataclasses.replace(
        _lineage(projected, _version_id(engine, pid), settings), resume_model_sha256="1" * 64
    )

    with pytest.raises(ResumeLineageMismatch):
        run_tailor(
            engine, settings, pid, resume_path=projected, out_dir=tmp_path / "out",
            typst_runner=_Runner(), source_lineage=wrong,
        )

    with engine.connect() as conn:
        assert conn.execute(artifacts.select()).first() is None


# -- transformation identity: the rules, not just the document ---------------------------
#
# The document checks above prove WHICH DOCUMENT this is. They cannot prove WHICH RULES produced
# it: `_plan_tier_a` loads the taxonomy, the persona registry and the equivalence table itself, so
# a configuration change landing between projection and tailoring left the artifact recording the
# frozen versions while the transform actually applied the new ones — the design's §4.1 requirement
# ("`run_tailor` either consumes the same snapshot or compares its own resolved dependencies
# against the recorded versions and refuses"), and it was the unimplemented half.
#
# Each case changes the configuration FOR REAL where the loader supports it — `load_taxonomy` and
# `load_personas` both take a `{config_dir}` override — rather than mutating the recorded version,
# so what is exercised is the value `run_tailor` genuinely resolved.

#: A valid taxonomy override whose CONTENT differs from the bundled table, so `_version_of` (a hash
#: of the canonical parsed document) necessarily moves. One pattern is enough: the version is what
#: is under test, not the extraction.
_OTHER_TAXONOMY = (
    "patterns:\n"
    "  - name: Python\n"
    "    category: language\n"
    "    pattern: '\\bPython\\b'\n"
)

#: A valid persona override — exactly one default, unique ids, role_families inside the closed
#: `classify_role_family` output set. Different content from the bundled seed, so its derived
#: version differs.
_OTHER_PERSONAS = (
    "personas:\n"
    "  - id: general_swe\n"
    "    title: 'Software Engineer'\n"
    "    default: true\n"
    "    role_families: [backend, frontend, fullstack, data_eng, devops_sre, ml_ai, security,"
    " general_swe]\n"
    "    skill_group_order: [Languages]\n"
    "    entries: null\n"
)


def test_a_taxonomy_change_between_projection_and_tailoring_refuses(tmp_path: Path) -> None:
    """The lineage names taxonomy A; `_plan_tier_a` resolves B, so the transform about to run is
    not the one the artifact would claim.

    This is the arm a document hash cannot reach — the bytes are untouched and both hashes still
    match — and it is the one the extraction lookup would otherwise hide: `jd_skills_for` is keyed
    to the taxonomy version, so a miss coalesces to an EMPTY skill set and the lead tailors on
    silently. The refusal therefore has to land before that lookup, which is where it is.
    """
    settings = _settings(tmp_path)
    engine = _engine(settings)
    pid = _seed(engine, settings)
    projected = _projected(tmp_path)
    lineage = _lineage(projected, _version_id(engine, pid), settings)
    settings.config_dir.mkdir(parents=True, exist_ok=True)
    (settings.config_dir / "taxonomy.yaml").write_text(_OTHER_TAXONOMY, encoding="utf-8")
    # Non-vacuity: the override really did move the version, so the refusal below is about a
    # genuine disagreement and not about a lineage field nobody changed.
    assert load_taxonomy(settings.config_dir).version != lineage.taxonomy_version
    runner = _Runner()

    with pytest.raises(ResumeLineageMismatch, match="taxonomy_version"):
        run_tailor(
            engine, settings, pid, resume_path=projected, out_dir=tmp_path / "out",
            typst_runner=runner, source_lineage=lineage,
        )

    assert runner.calls == []  # refused before any render
    with engine.connect() as conn:
        assert conn.execute(artifacts.select()).first() is None


def test_a_persona_registry_change_between_projection_and_tailoring_refuses(
    tmp_path: Path,
) -> None:
    """The persona lens shapes the résumé BEFORE planning (`apply_persona`), so a registry that
    moved changes which entries and which headline the tailored document carries — under a lineage
    naming the registry that did not."""
    settings = _settings(tmp_path)
    engine = _engine(settings)
    pid = _seed(engine, settings)
    projected = _projected(tmp_path)
    lineage = _lineage(projected, _version_id(engine, pid), settings)
    settings.config_dir.mkdir(parents=True, exist_ok=True)
    (settings.config_dir / "personas.yaml").write_text(_OTHER_PERSONAS, encoding="utf-8")
    assert load_personas(settings.config_dir).version != lineage.persona_registry_version
    runner = _Runner()

    with pytest.raises(ResumeLineageMismatch, match="persona_registry_version"):
        run_tailor(
            engine, settings, pid, resume_path=projected, out_dir=tmp_path / "out",
            typst_runner=runner, source_lineage=lineage,
        )

    assert runner.calls == []
    with engine.connect() as conn:
        assert conn.execute(artifacts.select()).first() is None


def test_an_equivalence_table_change_between_projection_and_tailoring_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The third dependency, and the only one with no `{config_dir}` override: `load_equivalences`
    reads a packaged file, so the change is injected at the BY-NAME binding `reports.tailor`
    actually calls. Patching `boardwatch.tailor.equivalences` instead would leave that binding
    untouched and the test could not fail (the same resolution-at-call-time subtlety
    `projection/run.py` records for `load_taxonomy`).

    Equivalence swaps rewrite bullet TEXT, so a table that moved changes the shipped words — which
    no hash over the projected bytes can see, because the swap happens after they were hashed.
    """
    settings = _settings(tmp_path)
    engine = _engine(settings)
    pid = _seed(engine, settings)
    projected = _projected(tmp_path)
    lineage = _lineage(projected, _version_id(engine, pid), settings)
    moved = dataclasses.replace(load_equivalences(), version="equivalences-after-the-edit")
    assert moved.version != lineage.equivalence_version
    monkeypatch.setattr(tailor_mod, "load_equivalences", lambda: moved)
    runner = _Runner()

    with pytest.raises(ResumeLineageMismatch, match="equivalence_version"):
        run_tailor(
            engine, settings, pid, resume_path=projected, out_dir=tmp_path / "out",
            typst_runner=runner, source_lineage=lineage,
        )

    assert runner.calls == []
    with engine.connect() as conn:
        assert conn.execute(artifacts.select()).first() is None


def test_an_authored_run_never_compares_transformation_versions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The negative control for the three above. With no `source_lineage` there is nothing to
    compare against, and the same configuration changes that refuse a projected lead must leave an
    authored one completely unaffected — otherwise this check would have made every ordinary
    `boardwatch run` depend on a bundle nobody asked it to read."""
    settings = _settings(tmp_path)
    engine = _engine(settings)
    pid = _seed(engine, settings)
    authored = tmp_path / "resume.yaml"
    authored.write_text(scaffold_template(), encoding="utf-8")
    settings.config_dir.mkdir(parents=True, exist_ok=True)
    (settings.config_dir / "taxonomy.yaml").write_text(_OTHER_TAXONOMY, encoding="utf-8")
    (settings.config_dir / "personas.yaml").write_text(_OTHER_PERSONAS, encoding="utf-8")
    monkeypatch.setattr(
        tailor_mod,
        "load_equivalences",
        lambda: dataclasses.replace(load_equivalences(), version="equivalences-after-the-edit"),
    )

    res = run_tailor(
        engine, settings, pid, resume_path=authored, out_dir=tmp_path / "out",
        typst_runner=_Runner(),
    )

    assert res.pdf_path is not None
    with engine.connect() as conn:
        rows = conn.execute(artifacts.select()).fetchall()
    assert any(row.kind == "resume_tailored" for row in rows)


def test_the_lineage_path_reads_the_resume_file_exactly_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One read, hashed and parsed from the same buffer. The property is structurally unobservable
    from BEHAVIOUR — single-threaded, the file holds the same bytes however often it is read — but a
    call COUNT is observable, and it is what a regression moves: `hashlib.sha256(path.read_bytes())`
    followed by `load_resume(path)` reads twice and reopens the read/swap/read window
    `_master_from_lineage` exists to close, while satisfying every other test in this file.

    Counted on two routes, because either alone has a blind spot. `read_resume_bytes` is the only
    sanctioned reader, and it is bound in TWO modules: `load_resume` calls `tailor.load`'s own
    global, `_master_from_lineage` calls the by-name import in `reports.tailor`, so a swap from one
    route to the other is invisible to a counter that watches only one. `Path.read_bytes` underneath
    both catches the re-read that bypasses the helper entirely.
    """
    settings = _settings(tmp_path)
    engine = _engine(settings)
    pid = _seed(engine, settings)
    projected = _projected(tmp_path)
    # Computed BEFORE the counters are installed, so the lineage's own hashing is not counted.
    lineage = _lineage(projected, _version_id(engine, pid), settings)

    helper_calls = 0
    file_reads = 0
    real_helper = load_mod.read_resume_bytes
    real_read_bytes = Path.read_bytes

    def counting_helper(path: Path) -> bytes:
        nonlocal helper_calls
        if path == projected:
            helper_calls += 1
        return real_helper(path)

    def counting_read_bytes(self: Path) -> bytes:
        nonlocal file_reads
        if self == projected:
            file_reads += 1
        return real_read_bytes(self)

    monkeypatch.setattr(load_mod, "read_resume_bytes", counting_helper)
    monkeypatch.setattr(tailor_mod, "read_resume_bytes", counting_helper)
    monkeypatch.setattr(Path, "read_bytes", counting_read_bytes)

    res = run_tailor(
        engine, settings, pid, resume_path=projected, out_dir=tmp_path / "out",
        typst_runner=_Runner(), source_lineage=lineage,
    )

    # Non-vacuity: the run completed, so the single read really did serve both the hash checks and
    # the parse rather than the lead having been refused before either.
    assert res.tailored_artifact_id is not None
    assert helper_calls == 1
    assert file_reads == 1


def test_a_dry_run_with_lineage_records_no_artifact_and_no_lineage(tmp_path: Path) -> None:
    """`dry_run=True` validates the lineage (the check lives in `_plan_tier_a`, above the write) and
    then records NOTHING — and the write is the only thing that carries the lineage, so "no artifact
    ⇒ no lineage" has to hold on this path too.

    Unasserted, it was true only by inspection: `run_tailor`'s whole recording block sits under
    `if not dry_run:`, and a `meta.update(source_lineage.as_meta())` hoisted above that guard, or a
    `record_artifact` call moved out of it, would attribute a projection provenance to a résumé this
    call never kept.
    """
    settings = _settings(tmp_path)
    engine = _engine(settings)
    pid = _seed(engine, settings)
    projected = _projected(tmp_path)
    runner = _Runner()

    res = run_tailor(
        engine, settings, pid, resume_path=projected, out_dir=tmp_path / "out",
        typst_runner=runner, dry_run=True,
        source_lineage=_lineage(projected, _version_id(engine, pid), settings),
    )

    assert res.dry_run is True
    assert res.tailored_artifact_id is None
    assert res.pdf_path is None
    # Non-vacuity: Tier A really did plan and render source from the projected master, so the empty
    # artifacts table below is a dry run's restraint and not a refusal earlier in the call.
    assert res.source
    assert res.kept
    assert runner.calls == []  # a dry run never reaches the compile gate
    with engine.connect() as conn:
        assert conn.execute(artifacts.select()).first() is None


def test_existing_callers_are_unaffected(tmp_path: Path) -> None:
    """Every current caller passes no lineage and must behave exactly as before: an authored
    résumé still ships a PDF, and the tailored row carries no projection_* keys to be
    misread as provenance."""
    settings = _settings(tmp_path)
    engine = _engine(settings)
    pid = _seed(engine, settings)
    authored = tmp_path / "resume.yaml"
    authored.write_text(scaffold_template(), encoding="utf-8")

    before = run_tailor(
        engine, settings, pid, resume_path=authored, out_dir=tmp_path / "out",
        typst_runner=_Runner(),
    )

    assert before.pdf_path is not None
    with engine.connect() as conn:
        rows = conn.execute(artifacts.select()).fetchall()
    tailored = next(r for r in rows if r.kind == "resume_tailored")
    assert [k for k in tailored.meta_json if k.startswith("projection_")] == []
