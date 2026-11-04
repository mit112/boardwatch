"""D-669: consecutive dead pipeline scans and opt-in watch repairs."""

from __future__ import annotations

from dataclasses import dataclass
from shlex import join

from sqlalchemy import Connection, Engine, func, select, update

from boardwatch.core.politeness import Fetcher
from boardwatch.core.settings import Settings
from boardwatch.providers.base import BoardHealth
from boardwatch.providers.registry import build_providers
from boardwatch.scan.board_migration import company_key, suggest_migrations
from boardwatch.store.queries import get_watched_companies, upsert_watch
from boardwatch.store.tables import board_scans, companies


@dataclass(frozen=True)
class DeadBoard:
    company_id: int
    provider: str
    slug: str
    name: str

    @property
    def label(self) -> str:
        return f"{self.name} ({self.provider}:{self.slug})"


def dead_for_three_scans(conn: Connection, run_id: int) -> list[DeadBoard]:
    """This run and the board's previous two PIPELINE board scans must all have failed dead.

    Filter before ranking: lanes, standalone scans and filtered CLI scans neither count nor
    reset a streak. Old rows lack typed evidence and deliberately cannot qualify.
    """
    history = select(
        board_scans.c.company_id, board_scans.c.run_id, board_scans.c.dead,
        board_scans.c.status,
        func.row_number().over(
            partition_by=board_scans.c.company_id,
            order_by=board_scans.c.run_id.desc(),
        ).label("position"),
    ).where(
        board_scans.c.scan_kind == "board", board_scans.c.pipeline_scan.is_(True),
        board_scans.c.run_id <= run_id,
    ).subquery()
    chronic = select(history.c.company_id).where(history.c.position <= 3).group_by(
        history.c.company_id
    ).having(
        func.count() == 3, func.min(history.c.dead) == 1,
        func.min(history.c.status == "failed") == 1, func.max(history.c.run_id) == run_id,
    )
    rows = conn.execute(select(
        companies.c.id, companies.c.provider, companies.c.slug, companies.c.name,
    ).where(companies.c.id.in_(chronic)).order_by(companies.c.provider, companies.c.slug))
    return [DeadBoard(r.id, r.provider, r.slug, r.name) for r in rows]


def dead_boards_alert(boards: list[DeadBoard]) -> str:
    names = ", ".join(b.label for b in boards[:10])
    rest = f"; {len(boards) - 10} more" if len(boards) > 10 else ""
    return f"{len(boards)} boards dead for 3+ scans: {names}{rest}; full list in the funnel"


def _unwatch_id(conn: Connection, company_id: int) -> None:
    """The evidenced row itself: `unwatch` resolves a slug and can land on a healthy alias."""
    conn.execute(update(companies).where(companies.c.id == company_id).values(watched=False))


def follow_board_moves(
    engine: Engine, settings: Settings, boards: list[DeadBoard],
) -> tuple[list[str], list[str]]:
    """At most four candidate health checks per dead board; no change on a probe error.

    Each watch replacement commits together. Unwatch never closes or deletes postings: the
    existing death sweep owns those once their company is unwatched.
    """
    providers = build_providers()
    fetcher = Fetcher(settings)
    actions: list[str] = []
    errors: list[str] = []

    def probe(targets: list[tuple[str, str]]) -> dict[tuple[str, str], BoardHealth]:
        results = {}
        for provider, slug in targets:
            health = providers[provider].healthcheck(fetcher, slug)
            if health in (BoardHealth.ERROR, BoardHealth.UNREACHABLE):
                raise BoardMoveProbeError(f"{provider}:{slug} returned {health.value}")
            results[(provider, slug)] = health
        return results

    dead_ids = {board.company_id for board in boards}
    for board in boards:
        try:
            with engine.connect() as conn:
                watched = get_watched_companies(conn)
            if not any(r.id == board.company_id for r in watched):
                continue
            covered = next((r for r in watched if r.provider != board.provider and
                            r.id not in dead_ids and
                            r.name.casefold() == board.name.casefold() and
                            company_key(r.provider, r.slug).casefold() ==
                            company_key(board.provider, board.slug).casefold()), None)
            undo = join(["boardwatch", "--data-dir", str(settings.data_dir),
                         "companies", "add", f"{board.provider}:{board.slug}"])
            if covered is not None:
                with engine.begin() as conn:
                    _unwatch_id(conn, board.company_id)
                actions.append(
                    f"Unwatched {board.provider}:{board.slug}; already watched on "
                    f"{covered.provider}:{covered.slug}. Undo: `{undo}`"
                )
                continue
            suggestions = suggest_migrations([(board.provider, board.slug)], probe)
            if not suggestions:
                continue
            move = suggestions[0]
            with engine.begin() as conn:
                # A stored board under another name is another employer's: never rename it.
                held = conn.execute(select(companies.c.name).where(
                    companies.c.provider == move.new_provider,
                    func.lower(companies.c.slug) == func.lower(move.new_slug),
                )).scalar()
                if held is not None and held.casefold() != board.name.casefold():
                    continue
                slug = upsert_watch(conn, provider=move.new_provider, slug=move.new_slug,
                                    name=board.name, source="user")
                _unwatch_id(conn, board.company_id)
            undo += " && " + join(["boardwatch", "--data-dir", str(settings.data_dir),
                                   "companies", "remove", f"{move.new_provider}:{slug}"])
            actions.append(
                f"Moved {board.provider}:{board.slug} to {move.new_provider}:{slug}. "
                f"Undo: `{undo}`"
            )
        except Exception as exc:  # a failed probe or transaction changes no watch
            errors.append(f"board moves: {board.provider}:{board.slug}: {exc}")
    return actions, errors


class BoardMoveProbeError(Exception):
    """A candidate could not be checked; leave this board's watches alone."""
