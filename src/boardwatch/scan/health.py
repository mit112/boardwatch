"""doctor's probe engine (§2.3). The SOLE local writer of last_health/last_ok_at.
One injected Fetcher paces the whole probe set. D27: per-board OK|EMPTY|DEAD|
ERROR|UNREACHABLE; last_ok_at advances on OK/EMPTY, preserved otherwise.
Per-provider connectivity = reachable iff ≥1 probe got an HTTP response
(OK|EMPTY|DEAD|ERROR), unreachable iff all UNREACHABLE."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import Engine, update

from boardwatch.core.clock import utcnow
from boardwatch.core.politeness import Fetcher
from boardwatch.core.settings import Settings
from boardwatch.providers.base import BoardHealth, Provider
from boardwatch.registry.loader import load_catalog, starter_entries
from boardwatch.scan.coordinator import default_providers
from boardwatch.store import tables
from boardwatch.store.queries import get_watched_companies

_HTTP_BACKED = {BoardHealth.OK, BoardHealth.EMPTY, BoardHealth.DEAD, BoardHealth.ERROR}
_ADVANCE_OK_AT = {BoardHealth.OK, BoardHealth.EMPTY}
_WATCHED_ACTIONABLE = {BoardHealth.DEAD, BoardHealth.ERROR, BoardHealth.UNREACHABLE}


@dataclass
class ProviderConnectivity:
    provider: str
    reachable: bool
    from_fallback: bool
    fallback_status: BoardHealth | None = None


@dataclass
class DoctorReport:
    board_health: dict[str, BoardHealth] = field(default_factory=dict)  # "provider:slug" -> status
    connectivity: list[ProviderConnectivity] = field(default_factory=list)
    actionable: bool = False  # drives the non-zero exit


def probe_health(
    engine: Engine,
    settings: Settings,
    *,
    fetcher: Fetcher | None = None,
    providers: dict[str, Provider] | None = None,
    offline: bool = False,
) -> DoctorReport:
    report = DoctorReport()
    if offline:
        return report  # connectivity "not checked"; caller renders stored columns, writes nothing
    fetcher = fetcher or Fetcher(settings)
    providers = providers or default_providers()
    with engine.connect() as conn:
        watched = get_watched_companies(conn)
    by_provider: dict[str, list[BoardHealth]] = {name: [] for name in providers}
    for row in watched:
        status = providers[row.provider].healthcheck(fetcher, row.slug)
        report.board_health[f"{row.provider}:{row.slug}"] = status
        by_provider.setdefault(row.provider, []).append(status)
        _write_board_health(engine, row.id, status)
        if status in _WATCHED_ACTIONABLE:
            report.actionable = True
    for name, results in by_provider.items():
        if results:
            reachable = any(s in _HTTP_BACKED for s in results)
            report.connectivity.append(ProviderConnectivity(name, reachable, from_fallback=False))
            if not reachable:
                report.actionable = True  # provider unreachable (all probes UNREACHABLE)
        else:
            report.connectivity.append(_fallback(fetcher, providers, name, report))
    return report


def _write_board_health(engine: Engine, company_id: int, status: BoardHealth) -> None:
    values: dict[str, object] = {"last_health": status.value}
    if status in _ADVANCE_OK_AT:
        values["last_ok_at"] = utcnow()  # advance on OK/EMPTY; preserved otherwise
    with engine.begin() as conn:
        conn.execute(
            update(tables.companies).where(tables.companies.c.id == company_id).values(**values)
        )


def _fallback(
    fetcher: Fetcher, providers: dict[str, Provider], name: str, report: DoctorReport
) -> ProviderConnectivity:
    # zero-watch provider: probe the first starter catalog entry — connectivity-only,
    # ZERO DB writes (no watched row exists). UNREACHABLE ⇒ unreachable + actionable;
    # DEAD/ERROR ⇒ reachable, informational (registry maintenance is #20's domain).
    entry = next(
        (e for e in starter_entries(load_catalog()) if e.provider == name), None
    )
    if entry is None:
        return ProviderConnectivity(name, reachable=False, from_fallback=True)
    status = providers[name].healthcheck(fetcher, entry.slug)
    reachable = status in _HTTP_BACKED
    if not reachable:
        report.actionable = True
    return ProviderConnectivity(name, reachable, from_fallback=True, fallback_status=status)
