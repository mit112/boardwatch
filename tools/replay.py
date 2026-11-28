"""T371: replay a run's local stages on a clone of the store, offline, and diff two replays.

A change to eligibility, ranking, tailoring, the funnel or queue sync needs the store, not the
network, so it can be checked the same afternoon instead of on the next nightly. Three steps:

    python -m tools.replay clone --data-dir D --config-dir C --queue-root Q --root R base change \
        [--overlay change=DIR] [--with-llm]
    python -m tools.replay run R/base -- --project --top 40     # the operator's own run flags
    python -m tools.replay run R/change --boardwatch WT/.venv/bin/boardwatch -- --project --top 40
    python -m tools.replay diff R/base R/change

`clone` refuses while a live process holds the source's `scan.lock`, and discards its arms if the
store or its WAL changed while it copied: the main file and the WAL, unchanged across the copy, are
a consistent committed snapshot, so a WAL a writer left behind is copied with the store. Each arm
gets its own copy of the data dir, config dir and queue root (an APFS clone where the platform has
one; a symlink into a source dir is pointed at the arm's copy, any other is removed and named in
`replay.json`), and its `config.toml` is rewritten so the run cannot leave the arm or reach the
network: `data_dir` and `jobapps_queue_dir` point into the arm, `lanes_enabled = []` (on
`--no-scan` without `--fresh-hours` the lanes still run inline), `form_question_fetch_budget = 0`,
and the judge (`[gate]`) and `[llm]` tiers are off unless `--with-llm` keeps them as configured.
The rewrite is then checked by loading the arm's `Settings` through `load_settings`, the way the
CLI does.

`run` appends `--no-scan --no-check-liveness --queue-root --out` pointed into the arm, removes every
`BOARDWATCH_*` variable from the environment (so no heartbeat or alert is sent), and afterwards
checks that the source store holds no row of the arm's run. A code change runs from a worktree
with its own venv (`--boardwatch`), so the primary checkout never changes branch.

`diff` compares two arms' funnels with clocks, run ids and arm paths left out, every list of plain
values compared as a set (two replays of the same bytes order tied ids differently), and the
leads compared in order. It prints the stage seconds side by side and exits 1 on any difference.

What a replay is: a preview of the NEXT slate from the standing pool, minus the postings the next
scan would bring. Scan, lanes, liveness and the death probe stay network work for the nightly.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
import tomllib
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import tomli_w

from boardwatch.core.settings import Settings, load_settings

DB_NAME = "boardwatch.db"
LOCK_META = "scan.lock.meta"
#: Left out of a data-dir copy: the shared-memory index (rebuilt on open) and the source's lock.
SKIP_IN_DATA = re.compile(r"(-shm|^scan\.lock(\.meta)?|\.tmp)$")
ARM_NAME = re.compile(r"[a-z0-9][a-z0-9-]*")
#: Run flags the harness sets itself, so an operator cannot point an arm back at live paths.
FORBIDDEN_RUN_FLAGS = ("--data-dir", "--queue-root", "--out", "--continue-scan", "--check-liveness")
VOLATILE_KEY = re.compile(
    r"(^|_)(run_id|started_at|finished_at|at|seconds|elapsed|duration|durations|wall|ms)$"
)
TIMESTAMP = re.compile(r"\d{4}-\d\d-\d\d[T ][\d:.]+(\+00:00|Z)?")


class Refused(Exception):
    """The harness will not proceed; nothing was left behind."""


@dataclass(frozen=True)
class Source:
    data_dir: Path
    config_dir: Path
    queue_root: Path

    @classmethod
    def resolved(cls, data_dir: Path, config_dir: Path, queue_root: Path) -> Source:
        """Resolved, so a symlinked path (a queue root under `~`) is copied, not linked to."""
        return cls(data_dir.resolve(), config_dir.resolve(), queue_root.resolve())

    def dirs(self) -> tuple[Path, ...]:
        return (self.data_dir, self.config_dir, self.queue_root)


@dataclass(frozen=True)
class StoreState:
    """What must not move while an arm is copied: a write lands in the WAL or the main file.

    The WAL's mtime as well as its size: after a checkpoint a writer restarts the WAL from the
    top, so it can change without growing.
    """

    size: int
    mtime_ns: int
    wal_size: int
    wal_mtime_ns: int


def store_state(data_dir: Path) -> StoreState:
    db = data_dir / DB_NAME
    if not db.is_file():
        raise Refused(f"no store at {db}")
    wal = data_dir / f"{DB_NAME}-wal"
    st = db.stat()
    wst = wal.stat() if wal.exists() else None
    return StoreState(
        st.st_size, st.st_mtime_ns, wst.st_size if wst else 0, wst.st_mtime_ns if wst else 0
    )


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def check_quiet(data_dir: Path) -> StoreState:
    """Refuse a store that a live run or scan holds."""
    meta = data_dir / LOCK_META
    if meta.is_file():
        try:
            pid = int(json.loads(meta.read_text())["pid"])
        except (ValueError, KeyError, TypeError, json.JSONDecodeError):
            pid = None
        if pid is None or _pid_alive(pid):
            raise Refused(f"{meta} names a live holder (pid {pid}); a run or scan is active")
    return store_state(data_dir)


def _copy(src: Path, dst: Path) -> None:
    """An APFS clone on macOS (`cp -c`, instant for a 30 GB store); a plain copy elsewhere."""
    if sys.platform == "darwin":
        subprocess.run(["cp", "-cR", str(src), str(dst)], check=True)
    elif src.is_dir():
        shutil.copytree(src, dst, symlinks=True)
    else:
        shutil.copy2(src, dst)


def _is_within(path: Path, parent: Path) -> bool:
    return path.resolve().is_relative_to(parent.resolve())


def relink(arm: Path, source: Source) -> list[str]:
    """Keep every symlink in the arm inside it. `cp -R` copies a link as a link, so a link the
    operator keeps in a config dir (the maintainer's `tailored -> <data_dir>/tailored`) would
    reach the live path. A link into a source dir is pointed at the arm's copy of that path;
    any other is removed, and returned so the manifest names it."""
    copies = ((source.data_dir, arm / "data"), (source.config_dir, arm / "config"),
              (source.queue_root, arm / "queue"))
    removed = []
    for link in escaping_links(arm):
        target = link.resolve()
        inside = next(((s, c) for s, c in copies if target.is_relative_to(s)), None)
        link.unlink()
        if inside is not None:
            link.symlink_to(inside[1] / target.relative_to(inside[0]))
        else:
            removed.append(f"{link.relative_to(arm)} -> {target}")
    return removed


def escaping_links(arm: Path) -> list[Path]:
    """Every symlink inside the arm whose target lies outside it: a copied link to a live path."""
    found = []
    for directory, dirnames, filenames in os.walk(arm):
        for name in [*dirnames, *filenames]:
            path = Path(directory) / name
            if path.is_symlink() and not _is_within(path, arm):
                found.append(path)
    return found


@contextmanager
def _config_env(config_dir: Path) -> Iterator[None]:
    before = os.environ.get("BOARDWATCH_CONFIG_DIR")
    os.environ["BOARDWATCH_CONFIG_DIR"] = str(config_dir)
    try:
        yield
    finally:
        if before is None:
            del os.environ["BOARDWATCH_CONFIG_DIR"]
        else:
            os.environ["BOARDWATCH_CONFIG_DIR"] = before


def isolate_config(arm: Path, *, with_llm: bool) -> None:
    """Rewrite the arm's `config.toml` so a run stays inside the arm and off the network."""
    path = arm / "config" / "config.toml"
    raw: dict[str, Any] = tomllib.loads(path.read_text()) if path.is_file() else {}
    raw["data_dir"] = str(arm / "data")
    if raw.get("jobapps_queue_dir"):
        staging = Path(str(raw["jobapps_queue_dir"]))
        target = arm / "jobapps-staging"
        if staging.is_dir():
            _copy(staging, target)
        raw["jobapps_queue_dir"] = str(target)
    raw["lanes_enabled"] = []
    raw["form_question_fetch_budget"] = 0
    if not with_llm:
        for tier in ("gate", "llm"):
            section = raw.get(tier)
            if isinstance(section, dict):
                section["enabled"] = False
    path.write_text(tomli_w.dumps(raw))


def verify_isolation(arm: Path, source: Source, *, with_llm: bool) -> Settings:
    """Load the arm's settings the way the CLI does and check every value the rewrite set."""
    with _config_env(arm / "config"):
        settings = load_settings()
    problems = []
    if settings.data_dir != arm / "data":
        problems.append(f"data_dir is {settings.data_dir}")
    if settings.config_dir != arm / "config":
        problems.append(f"config_dir is {settings.config_dir}")
    if settings.lanes_enabled:
        problems.append(f"lanes_enabled is {settings.lanes_enabled}")
    if settings.form_question_fetch_budget:
        problems.append(f"form_question_fetch_budget is {settings.form_question_fetch_budget}")
    if not with_llm and (settings.gate.enabled or settings.llm.enabled):
        problems.append("the gate or llm tier is still enabled")
    queue_dir = settings.jobapps_queue_dir
    if queue_dir is not None and not _is_within(queue_dir, arm):
        problems.append(f"jobapps_queue_dir is {queue_dir}")
    for name, value in (("data_dir", settings.data_dir), ("config_dir", settings.config_dir)):
        if any(_is_within(value, d) for d in source.dirs()):
            problems.append(f"{name} resolves into a source directory: {value}")
    if problems:
        raise Refused(f"arm {arm.name} is not isolated: " + "; ".join(problems))
    return settings


def clone(
    source: Source,
    root: Path,
    arms: Sequence[str],
    *,
    overlays: Mapping[str, Path] | None = None,
    with_llm: bool = False,
    copy: Callable[[Path, Path], None] = _copy,
) -> list[Path]:
    """Make one isolated arm per name under `root`, all from the same store bytes."""
    overlays = dict(overlays or {})
    root = root.resolve()
    if not arms:
        raise Refused("name at least one arm")
    for name in arms:
        if not ARM_NAME.fullmatch(name):
            raise Refused(f"arm name {name!r}: use lowercase letters, digits and hyphens")
    if unknown := set(overlays) - set(arms):
        raise Refused(f"overlay for an arm not being made: {sorted(unknown)}")
    for d in source.dirs():
        if d.exists() and (_is_within(root, d) or _is_within(d, root)):
            raise Refused(f"the scratch root {root} and the source {d} overlap")
    paths = [root / name for name in arms]
    if existing := [p for p in paths if p.exists()]:
        raise Refused(f"already exists: {', '.join(map(str, existing))}")

    before = check_quiet(source.data_dir)
    root.mkdir(parents=True, exist_ok=True)
    made: list[Path] = []
    try:
        for arm in paths:
            arm.mkdir()
            made.append(arm)
            (arm / "data").mkdir()
            for entry in sorted(source.data_dir.iterdir()):
                if not SKIP_IN_DATA.search(entry.name):
                    copy(entry, arm / "data" / entry.name)
            copy(source.config_dir, arm / "config")
            if source.queue_root.is_dir():
                copy(source.queue_root, arm / "queue")
            else:
                (arm / "queue").mkdir()
            (arm / "out").mkdir()
        after = store_state(source.data_dir)
        if after != before:
            raise Refused(f"the source store changed while it was copied ({before} -> {after})")
        for arm in paths:
            if overlay := overlays.get(arm.name):
                shutil.copytree(overlay, arm / "config", dirs_exist_ok=True)
            isolate_config(arm, with_llm=with_llm)
            removed = relink(arm, source)
            if links := escaping_links(arm):
                raise Refused(f"arm {arm.name} holds links out of the arm: {links[:3]}")
            verify_isolation(arm, source, with_llm=with_llm)
            manifest = {
                "source": {k: str(v) for k, v in asdict(source).items()},
                "store_state": asdict(before),
                "overlay": str(overlays[arm.name]) if arm.name in overlays else None,
                "with_llm": with_llm,
                "links_removed": removed,
                "cloned_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            }
            (arm / "replay.json").write_text(json.dumps(manifest, indent=2) + "\n")
    except BaseException:
        for arm in made:
            shutil.rmtree(arm)
        raise
    return paths


def _manifest(arm: Path) -> dict[str, Any]:
    path = arm / "replay.json"
    if not path.is_file():
        raise Refused(f"{arm} is not an arm made by `clone` (no replay.json)")
    result: dict[str, Any] = json.loads(path.read_text())
    return result


def run_command(arm: Path, run_args: Sequence[str], boardwatch: Path) -> list[str]:
    for arg in run_args:
        if arg.split("=", 1)[0] in FORBIDDEN_RUN_FLAGS:
            raise Refused(f"{arg}: the harness sets this itself")
    return [
        str(boardwatch), "--data-dir", str(arm / "data"), "run", *run_args,
        "--no-scan", "--no-check-liveness",
        "--queue-root", str(arm / "queue"), "--out", str(arm / "out"),
    ]


def run_env(arm: Path, environ: Mapping[str, str]) -> dict[str, str]:
    env = {k: v for k, v in environ.items() if not k.startswith("BOARDWATCH_")}
    env["BOARDWATCH_CONFIG_DIR"] = str(arm / "config")
    return env


def funnel_path(arm: Path) -> Path:
    paths = glob.glob(str(arm / "out" / "*" / "funnel-*.json"))
    if len(paths) != 1:
        raise Refused(f"{arm}: expected one funnel file under out/, found {len(paths)}")
    return Path(paths[0])


def read_only(db: Path) -> sqlite3.Connection:
    """Read a store without writing it, INCLUDING what still sits in its WAL.

    `immutable=1` ignores the WAL, so a leaked run's rows would read as absent; `mode=ro` reads
    them, but fails where it cannot create the `-shm` it needs, and a store with no `-shm` has no
    open writer and no WAL to miss.
    """
    try:
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        conn.execute("select 1 from sqlite_master limit 1")
    except sqlite3.OperationalError:
        conn = sqlite3.connect(f"file:{db}?immutable=1", uri=True)
    return conn


def source_has_run(data_dir: Path, run_id: int, started_at: str) -> bool:
    db = read_only(data_dir / DB_NAME)
    try:
        row = db.execute("select started_at from runs where id = ?", (run_id,)).fetchone()
    finally:
        db.close()
    return row is not None and str(row[0]).replace(" ", "T") == started_at.replace(" ", "T")


def run_arm(
    arm: Path,
    run_args: Sequence[str],
    *,
    boardwatch: Path,
    runner: Callable[..., subprocess.CompletedProcess[bytes]] = subprocess.run,
) -> int:
    """Run one offline replay in the arm; write `run.log` and `result.json`; return its exit."""
    manifest = _manifest(arm)
    if (arm / "result.json").exists():
        raise Refused(f"{arm} has already run; clone a fresh arm")
    argv = run_command(arm, run_args, boardwatch)
    start = time.monotonic()
    with (arm / "run.log").open("wb") as log:
        code = runner(argv, env=run_env(arm, os.environ), stdout=log, stderr=subprocess.STDOUT,
                      check=False).returncode
    result: dict[str, Any] = {
        "argv": argv, "exit": code, "wall_seconds": round(time.monotonic() - start, 1)
    }
    if code == 0:
        funnel = json.loads(funnel_path(arm).read_text())
        result["run_id"] = funnel["run_id"]
        if source_has_run(Path(manifest["source"]["data_dir"]), funnel["run_id"],
                           funnel["started_at"]):
            result["isolation"] = "BROKEN: the source store holds this arm's run row"
            code = 3
        else:
            result["isolation"] = "ok: the source store holds no row of this run"
    (arm / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    return code


def normalise(value: Any, arm: Path) -> Any:
    if isinstance(value, dict):
        return {k: normalise(v, arm) for k, v in value.items() if not VOLATILE_KEY.search(k)}
    if isinstance(value, list):
        return [normalise(v, arm) for v in value]
    if isinstance(value, str):
        value = value.replace(str(arm), "<ARM>")
        return "<TS>" if TIMESTAMP.fullmatch(value) else value
    return value


def differences(a: Any, b: Any, path: str = "") -> list[str]:
    """Paths where two normalised funnels differ; lists of plain values compare as sets."""
    if type(a) is not type(b):
        return [f"{path}: {str(a)[:80]} != {str(b)[:80]}"]
    if isinstance(a, dict):
        out = []
        for key in sorted(set(a) | set(b)):
            if key not in a or key not in b:
                out.append(f"{path}.{key}: only in {'B' if key not in a else 'A'}")
            else:
                out.extend(differences(a[key], b[key], f"{path}.{key}"))
        return out
    if isinstance(a, list):
        if all(not isinstance(v, (dict, list)) for v in a + b):
            same = sorted(map(repr, a)) == sorted(map(repr, b))
            return [] if same else [f"{path}: members differ ({len(a)} vs {len(b)} items)"]
        out = [f"{path}: {len(a)} vs {len(b)} items"] if len(a) != len(b) else []
        for i, (x, y) in enumerate(zip(a, b, strict=False)):
            out.extend(differences(x, y, f"{path}[{i}]"))
        return out
    return [] if a == b else [f"{path}: {str(a)[:80]} != {str(b)[:80]}"]


def diff_arms(a: Path, b: Path, *, limit: int = 40) -> int:
    fa = json.loads(funnel_path(a).read_text())
    fb = json.loads(funnel_path(b).read_text())
    slate_a = [lead["posting_id"] for lead in fa["leads"]]
    slate_b = [lead["posting_id"] for lead in fb["leads"]]
    found = differences(normalise(fa, a), normalise(fb, b))
    print(f"slate: A {len(slate_a)} leads, B {len(slate_b)}; same leads in the same order: "
          f"{slate_a == slate_b}")
    print(f"{len(found)} differing paths (clocks, run ids and arm paths left out; "
          "lists of plain values compared as sets)")
    for line in found[:limit]:
        print("  ", line)
    if len(found) > limit:
        print(f"   … and {len(found) - limit} more")
    sa = {s["name"]: s["seconds"] for s in fa.get("stage_durations") or []}
    sb = {s["name"]: s["seconds"] for s in fb.get("stage_durations") or []}
    print(f"{'stage seconds':24} {'A':>10} {'B':>10}")
    for name in sorted(set(sa) | set(sb), key=lambda n: -(sa.get(n) or 0.0)):
        print(f"  {name:22} {sa.get(name, '-')!s:>10} {sb.get(name, '-')!s:>10}")
    for arm, label in ((a, "A"), (b, "B")):
        result = arm / "result.json"
        if result.is_file():
            print(f"{label} wall {json.loads(result.read_text()).get('wall_seconds')} s")
    return 0 if not found else 1  # the leads compare in order inside `found`


def _parse_overlays(pairs: Sequence[str]) -> dict[str, Path]:
    overlays: dict[str, Path] = {}
    for pair in pairs:
        name, sep, directory = pair.partition("=")
        if not sep or not Path(directory).is_dir():
            raise Refused(f"--overlay {pair!r}: expected ARM=DIRECTORY")
        overlays[name] = Path(directory)
    return overlays


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tools.replay", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    c = sub.add_parser("clone", help="make isolated arms from the same store bytes")
    c.add_argument("--data-dir", type=Path, required=True)
    c.add_argument("--config-dir", type=Path, required=True)
    c.add_argument("--queue-root", type=Path, required=True)
    c.add_argument("--root", type=Path, required=True, help="scratch directory for the arms")
    c.add_argument("--overlay", action="append", default=[], metavar="ARM=DIR",
                   help="copy DIR's files over that arm's config before isolating it")
    c.add_argument("--with-llm", action="store_true",
                   help="keep the judge and llm tiers as configured (they spend the operator's "
                        "own login or API key; a nightly's judge sends about 14 batches)")
    c.add_argument("arms", nargs="+")
    r = sub.add_parser("run", help="run one offline replay in an arm")
    r.add_argument("arm", type=Path)
    r.add_argument("--boardwatch", type=Path, default=Path(sys.executable).with_name("boardwatch"),
                   help="the boardwatch executable (a worktree's venv for a code change)")
    r.add_argument("run_args", nargs=argparse.REMAINDER,
                   help="after `--`: the operator's own run flags, e.g. --project --top 40")
    d = sub.add_parser("diff", help="compare two arms that have run")
    d.add_argument("a", type=Path)
    d.add_argument("b", type=Path)
    args = parser.parse_args(argv)
    if sys.platform == "win32":
        # `os.kill(pid, 0)` terminates the process on Windows instead of probing it.
        print("refused: the replay harness is POSIX-only", file=sys.stderr)
        return 2
    try:
        if args.command == "clone":
            source = Source.resolved(args.data_dir, args.config_dir, args.queue_root)
            for arm in clone(source, args.root, args.arms,
                             overlays=_parse_overlays(args.overlay), with_llm=args.with_llm):
                print(f"{arm.name}: ready at {arm}")
            return 0
        if args.command == "run":
            run_args = [a for a in args.run_args if a != "--"]
            code = run_arm(args.arm, run_args, boardwatch=args.boardwatch)
            print((args.arm / "result.json").read_text(), end="")
            return code
        return diff_arms(args.a, args.b)
    except Refused as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
