"""T371: the replay harness clones a quiet store into isolated arms, runs offline, and diffs."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

import pytest

from tools import replay
from tools.replay import Refused, Source

BOARDWATCH = Path(sys.executable).with_name("boardwatch")

# The harness is POSIX-only (`main` refuses on Windows: `os.kill(pid, 0)` terminates there).
pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="the replay harness is POSIX-only")

LIVE_CONFIG = """\
data_dir = "{data}"
lanes_enabled = ["hiringcafe", "linkedin", "jobapps"]
jobapps_queue_dir = "{staging}"
form_question_fetch_budget = 100

[gate]
enabled = true
model = "sonnet"

[llm]
enabled = true
"""


def _source(tmp_path: Path) -> Source:
    """A minimal operator layout: a store, a config that names it, a staging dir and a queue."""
    data, config, queue = tmp_path / "live-data", tmp_path / "live-config", tmp_path / "live-queue"
    data.mkdir()
    config.mkdir()
    (queue / "Acme_Engineer").mkdir(parents=True)
    staging = config / "jobapps-staging"
    staging.mkdir()
    db = sqlite3.connect(data / "boardwatch.db")
    db.execute("create table runs (id integer primary key, started_at text)")
    db.commit()
    db.close()
    (config / "config.toml").write_text(LIVE_CONFIG.format(data=data, staging=staging))
    return Source(data, config, queue)


def _fingerprint(*dirs: Path) -> set[tuple[str, int, int]]:
    """Every file under the dirs with its size and mtime: any write by a replay changes it."""
    out = set()
    for d in dirs:
        for path in d.rglob("*"):
            if path.is_file():
                st = path.stat()
                out.add((str(path), st.st_size, st.st_mtime_ns))
    return out


def test_clone_makes_arms_whose_settings_point_only_into_the_arm(tmp_path: Path) -> None:
    source = _source(tmp_path)
    before = _fingerprint(*source.dirs())

    arms = replay.clone(source, tmp_path / "scratch", ["base", "change"])

    assert [a.name for a in arms] == ["base", "change"]
    assert _fingerprint(*source.dirs()) == before, "cloning wrote to the source"
    for arm in arms:
        settings = replay.verify_isolation(arm, source, with_llm=False)
        assert settings.data_dir == arm / "data"
        assert settings.config_dir == arm / "config"
        assert settings.lanes_enabled == ()
        assert settings.form_question_fetch_budget == 0
        assert not settings.gate.enabled and not settings.llm.enabled
        assert settings.jobapps_queue_dir == arm / "jobapps-staging"
        assert (arm / "data" / "boardwatch.db").is_file()
        assert (arm / "queue" / "Acme_Engineer").is_dir()
        assert json.loads((arm / "replay.json").read_text())["source"]["data_dir"] == str(
            source.data_dir
        )


def test_with_llm_keeps_the_judge_and_llm_tiers_as_configured(tmp_path: Path) -> None:
    source = _source(tmp_path)
    (arm,) = replay.clone(source, tmp_path / "scratch", ["judged"], with_llm=True)
    settings = replay.verify_isolation(arm, source, with_llm=True)
    assert settings.gate.enabled and settings.llm.enabled
    assert settings.lanes_enabled == ()


def test_an_overlay_lands_before_the_isolation_rewrite(tmp_path: Path) -> None:
    """An overlay may carry its own `config.toml`; the rewrite still points it into the arm."""
    source = _source(tmp_path)
    overlay = tmp_path / "overlay"
    overlay.mkdir()
    (overlay / "apply-routes.toml").write_text("last_hosts = []\n")
    (overlay / "config.toml").write_text(f'data_dir = "{source.data_dir}"\nslate_ceiling = 7\n')

    base, change = replay.clone(
        source, tmp_path / "scratch", ["base", "change"], overlays={"change": overlay}
    )

    assert not (base / "config" / "apply-routes.toml").exists()
    assert (change / "config" / "apply-routes.toml").read_text() == "last_hosts = []\n"
    settings = replay.verify_isolation(change, source, with_llm=False)
    assert settings.slate_ceiling == 7
    assert settings.data_dir == change / "data"


def test_the_rewrite_is_checked_through_load_settings_not_trusted(tmp_path: Path) -> None:
    source = _source(tmp_path)
    (arm,) = replay.clone(source, tmp_path / "scratch", ["base"])
    config = arm / "config" / "config.toml"
    raw = tomllib.loads(config.read_text())
    raw["data_dir"] = str(source.data_dir)
    import tomli_w

    config.write_text(tomli_w.dumps(raw))

    with pytest.raises(Refused, match="data_dir"):
        replay.verify_isolation(arm, source, with_llm=False)


def test_a_wal_left_by_a_writer_that_exited_is_copied_with_the_store(tmp_path: Path) -> None:
    """A writer that exits without a checkpoint leaves committed rows in the WAL alone. The
    main file without its WAL would be an older store, so the arm must carry both."""
    source = _source(tmp_path)
    db_path = source.data_dir / "boardwatch.db"
    writer = sqlite3.connect(db_path)
    writer.execute("pragma journal_mode=wal")
    writer.execute("pragma wal_autocheckpoint=0")
    writer.execute("insert into runs values (2922, '2026-11-28 19:36:15')")
    writer.commit()
    assert (source.data_dir / "boardwatch.db-wal").stat().st_size > 0
    try:
        (arm,) = replay.clone(source, tmp_path / "scratch", ["base"])
    finally:
        writer.close()
    copied = sqlite3.connect(arm / "data" / "boardwatch.db")
    assert copied.execute("select id from runs").fetchall() == [(2922,)]
    copied.close()
    assert not (arm / "data" / "boardwatch.db-shm").exists()


def test_clone_refuses_while_a_live_process_holds_the_scan_lock(tmp_path: Path) -> None:
    source = _source(tmp_path)
    (source.data_dir / "scan.lock.meta").write_text(json.dumps({"pid": os.getpid()}))

    with pytest.raises(Refused, match="live holder"):
        replay.clone(source, tmp_path / "scratch", ["base"])


def test_a_stale_lock_sidecar_from_a_dead_process_does_not_block(tmp_path: Path) -> None:
    source = _source(tmp_path)
    dead = subprocess.run([sys.executable, "-c", "import os; print(os.getpid())"],
                          capture_output=True, text=True, check=True)
    (source.data_dir / "scan.lock.meta").write_text(json.dumps({"pid": int(dead.stdout)}))

    (arm,) = replay.clone(source, tmp_path / "scratch", ["base"])
    assert not (arm / "data" / "scan.lock.meta").exists()


def test_clone_discards_every_arm_when_the_store_moves_mid_copy(tmp_path: Path) -> None:
    source = _source(tmp_path)
    copied: list[Path] = []

    def copy_then_write(src: Path, dst: Path) -> None:
        replay._copy(src, dst)
        copied.append(dst)
        if len(copied) == 1:  # a peer commits while the first arm is being copied
            db = sqlite3.connect(source.data_dir / "boardwatch.db")
            db.execute("insert into runs (started_at) values ('2026-11-28 19:57:14')")
            db.commit()
            db.close()

    with pytest.raises(Refused, match="changed while it was copied"):
        replay.clone(source, tmp_path / "scratch", ["a", "b"], copy=copy_then_write)
    assert copied, "the copy never ran, so the refusal proves nothing"
    assert list((tmp_path / "scratch").iterdir()) == []


def test_clone_discards_its_arms_when_a_restarted_wal_is_rewritten_mid_copy(
    tmp_path: Path,
) -> None:
    """After a passive checkpoint the WAL keeps its size and the next commit rewrites it from the
    top, so neither the main file nor the WAL's size moves: only the WAL's mtime does."""
    source = _source(tmp_path)
    writer = sqlite3.connect(source.data_dir / "boardwatch.db")
    writer.execute("pragma journal_mode=wal")
    writer.execute("pragma wal_autocheckpoint=0")
    for i in range(50):
        writer.execute("insert into runs (started_at) values (?)", (f"row {i} " + "x" * 200,))
        writer.commit()
    writer.execute("pragma wal_checkpoint(PASSIVE)")
    wal = source.data_dir / "boardwatch.db-wal"
    main = source.data_dir / "boardwatch.db"
    sizes = (main.stat().st_size, main.stat().st_mtime_ns, wal.stat().st_size)
    copied: list[Path] = []

    def copy_then_commit(src: Path, dst: Path) -> None:
        replay._copy(src, dst)
        copied.append(dst)
        if len(copied) == 1:
            writer.execute("insert into runs (started_at) values ('late')")
            writer.commit()

    try:
        with pytest.raises(Refused, match="changed while it was copied"):
            replay.clone(source, tmp_path / "scratch", ["a"], copy=copy_then_commit)
        assert (main.stat().st_size, main.stat().st_mtime_ns, wal.stat().st_size) == sizes, (
            "the late commit moved the main file or the WAL size, so this is not the case"
        )
    finally:
        writer.close()


def test_a_link_into_a_source_dir_is_pointed_at_the_arms_copy(tmp_path: Path) -> None:
    """`cp -R` copies a symlink as a link: the maintainer's config keeps `tailored` as a link to
    the data dir's, so a copied link would be the live folder."""
    source = _source(tmp_path)
    (source.data_dir / "tailored").mkdir()
    (source.config_dir / "tailored").symlink_to(source.data_dir / "tailored")
    (source.queue_root / "linked").symlink_to(source.queue_root / "Acme_Engineer")

    (arm,) = replay.clone(source, tmp_path / "scratch", ["base"])

    assert (arm / "config" / "tailored").resolve() == (arm / "data" / "tailored").resolve()
    assert (arm / "queue" / "linked").resolve() == (arm / "queue" / "Acme_Engineer").resolve()
    assert replay.escaping_links(arm) == []
    assert json.loads((arm / "replay.json").read_text())["links_removed"] == []


def test_a_link_to_anywhere_else_is_removed_and_named(tmp_path: Path) -> None:
    """Including one inside the job-apps staging dir, which the config rewrite copies late."""
    source = _source(tmp_path)
    elsewhere = tmp_path / "other-repo" / "APPLY_QUEUE"
    elsewhere.mkdir(parents=True)
    (source.config_dir / "jobapps-staging" / "aq-Ashby").symlink_to(elsewhere)

    (arm,) = replay.clone(source, tmp_path / "scratch", ["base"])

    assert not (arm / "config" / "jobapps-staging" / "aq-Ashby").exists()
    assert not (arm / "jobapps-staging" / "aq-Ashby").exists()
    assert replay.escaping_links(arm) == []
    removed = json.loads((arm / "replay.json").read_text())["links_removed"]
    assert sorted(removed) == sorted(
        f"{p}/aq-Ashby -> {elsewhere.resolve()}" for p in ("config/jobapps-staging", "jobapps-staging")
    )


def test_a_symlinked_source_root_is_resolved_and_copied(tmp_path: Path) -> None:
    source = _source(tmp_path)
    link = tmp_path / "queue-link"
    link.symlink_to(source.queue_root)

    (arm,) = replay.clone(
        Source.resolved(source.data_dir, source.config_dir, link), tmp_path / "scratch", ["base"]
    )
    assert not (arm / "queue").is_symlink()
    assert (arm / "queue" / "Acme_Engineer").is_dir()


@pytest.mark.parametrize("name", ["", "Base", "../x", "a/b", "-x"])
def test_clone_refuses_an_arm_name_that_is_not_a_plain_name(tmp_path: Path, name: str) -> None:
    with pytest.raises(Refused, match="arm name"):
        replay.clone(_source(tmp_path), tmp_path / "scratch", [name])


def test_clone_refuses_a_scratch_root_inside_a_source_dir(tmp_path: Path) -> None:
    source = _source(tmp_path)
    with pytest.raises(Refused, match="overlap"):
        replay.clone(source, source.data_dir / "scratch", ["base"])


def test_the_run_command_points_every_path_into_the_arm(tmp_path: Path) -> None:
    arm = tmp_path / "base"
    argv = replay.run_command(arm, ["--project", "--top", "40"], BOARDWATCH)
    assert argv == [
        str(BOARDWATCH), "--data-dir", str(arm / "data"), "run", "--project", "--top", "40",
        "--no-scan", "--no-check-liveness",
        "--queue-root", str(arm / "queue"), "--out", str(arm / "out"),
    ]


@pytest.mark.parametrize(
    "flag", ["--queue-root", "--out=/x", "--continue-scan", "--check-liveness", "--data-dir"]
)
def test_the_run_command_refuses_a_flag_that_would_leave_the_arm(tmp_path: Path, flag: str) -> None:
    with pytest.raises(Refused, match="sets this itself"):
        replay.run_command(tmp_path, [flag], BOARDWATCH)


def test_the_run_environment_carries_no_boardwatch_variable_but_the_arm_config(
    tmp_path: Path,
) -> None:
    env = replay.run_env(
        tmp_path,
        {"PATH": "/bin", "BOARDWATCH_HEARTBEAT_URL": "https://hc", "BOARDWATCH_ALERT_URL": "x",
         "BOARDWATCH_DATA_DIR": "/live", "BOARDWATCH_CONFIG_DIR": "/live-config"},
    )
    assert env == {"PATH": "/bin", "BOARDWATCH_CONFIG_DIR": str(tmp_path / "config")}


def _funnel(leads: list[int], dropped: list[int], *, seconds: float = 1.0) -> dict[str, Any]:
    return {
        "run_id": 7, "started_at": "2026-11-28T19:54:08.898837",
        "leads": [{"posting_id": p, "out_dir": f"/scratch/arm/out/x-{p}"} for p in leads],
        "direct_share": {"dropped_ids": dropped},
        "stage_durations": [{"name": "eligibility", "seconds": seconds}],
    }


def _arm_with(tmp_path: Path, name: str, funnel: dict[str, Any]) -> Path:
    arm = tmp_path / name
    (arm / "out" / "2026-11-28").mkdir(parents=True)
    text = json.dumps(funnel).replace("/scratch/arm", str(arm))
    (arm / "out" / "2026-11-28" / f"funnel-{funnel['run_id']}.json").write_text(text)
    return arm


def test_diff_ignores_clocks_run_ids_arm_paths_and_the_order_of_tied_ids(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    a = _arm_with(tmp_path, "a", _funnel([1, 2], [5, 6, 7], seconds=130.0))
    other = _funnel([1, 2], [7, 5, 6], seconds=126.0)
    other["run_id"], other["started_at"] = 8, "2026-11-28T20:06:00.000000"
    b = _arm_with(tmp_path, "b", other)

    assert replay.diff_arms(a, b) == 0
    out = capsys.readouterr().out
    assert "0 differing paths" in out and "same leads in the same order: True" in out
    assert "130.0" in out and "126.0" in out


@pytest.mark.parametrize(
    ("leads", "dropped", "expect"),
    [
        ([2, 1], [5, 6, 7], "same leads in the same order: False"),
        ([1, 2], [5, 6, 8], "members differ"),
        ([1, 2, 3], [5, 6, 7], "2 vs 3 items"),
    ],
)
def test_diff_reports_a_changed_slate_or_a_changed_membership(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
    leads: list[int], dropped: list[int], expect: str,
) -> None:
    a = _arm_with(tmp_path, "a", _funnel([1, 2], [5, 6, 7]))
    b = _arm_with(tmp_path, "b", _funnel(leads, dropped))
    assert replay.diff_arms(a, b) == 1
    assert expect in capsys.readouterr().out


def test_the_post_run_check_sees_a_leaked_run_that_is_still_in_the_wal(tmp_path: Path) -> None:
    """The check that a replay left no row in the source must read the WAL: a leaked run's rows
    sit there until a checkpoint, and `immutable=1` reads them as absent."""
    db_path = tmp_path / "boardwatch.db"
    writer = sqlite3.connect(db_path)
    writer.execute("pragma journal_mode=wal")
    writer.execute("pragma wal_autocheckpoint=0")
    writer.execute("create table runs (id integer primary key, started_at text)")
    writer.commit()
    writer.execute("pragma wal_checkpoint(TRUNCATE)")
    writer.execute("insert into runs values (2923, '2026-11-28 19:54:08.898837')")
    writer.commit()
    assert (tmp_path / "boardwatch.db-wal").stat().st_size > 0, "the row never reached the WAL"
    try:
        assert replay.source_has_run(tmp_path, 2923, "2026-11-28T19:54:08.898837")
        assert not replay.source_has_run(tmp_path, 2923, "2026-11-28T20:00:00.000000")
    finally:
        writer.close()


def test_a_wal_store_whose_last_connection_closed_is_still_readable(tmp_path: Path) -> None:
    """The live store between runs: WAL mode, no `-wal` or `-shm` left, so `mode=ro` cannot open."""
    db = sqlite3.connect(tmp_path / "boardwatch.db")
    db.execute("pragma journal_mode=wal")
    db.execute("create table runs (id integer primary key, started_at text)")
    db.execute("insert into runs values (1, '2026-11-28 10:00:00')")
    db.commit()
    db.close()
    assert not (tmp_path / "boardwatch.db-shm").exists(), "the sidecars outlived the connection"
    # Where `mode=ro` cannot create the `-shm` it needs (the live store refused it on 2026-11-28).
    tmp_path.chmod(0o555)
    try:
        with pytest.raises(sqlite3.OperationalError):
            sqlite3.connect(f"file:{tmp_path / 'boardwatch.db'}?mode=ro", uri=True).execute(
                "select 1 from sqlite_master"
            )
        assert replay.source_has_run(tmp_path, 1, "2026-11-28T10:00:00")
    finally:
        tmp_path.chmod(0o755)


@pytest.mark.parametrize(
    ("source_started_at", "expect_code", "expect"),
    [("2026-11-28 19:54:08.898837", 3, "BROKEN"), ("2026-11-28 19:57:14.936050", 0, "ok")],
)
def test_run_arm_fails_when_the_source_store_holds_the_arms_run_row(
    tmp_path: Path, source_started_at: str, expect_code: int, expect: str
) -> None:
    """A run id alone is not a leak: a peer's CLI row can take the same id in the live store.
    The same id AND start time is the arm's own row, written to the wrong store."""
    source = _source(tmp_path)
    (arm,) = replay.clone(source, tmp_path / "scratch", ["base"])
    with sqlite3.connect(source.data_dir / "boardwatch.db") as db:
        db.execute("insert into runs values (2925, ?)", (source_started_at,))

    def fake_run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        day = arm / "out" / "2026-11-28"
        day.mkdir(parents=True)
        (day / "funnel-2925.json").write_text(
            json.dumps({"run_id": 2925, "started_at": "2026-11-28T19:54:08.898837", "leads": []})
        )
        return subprocess.CompletedProcess(argv, 0)

    code = replay.run_arm(arm, ["--top", "40"], boardwatch=BOARDWATCH, runner=fake_run)

    assert code == expect_code
    assert json.loads((arm / "result.json").read_text())["isolation"].startswith(expect)
