"""Which way the owner applies to each lead: an automatic fill, by hand, or not known yet.

A property of the lead's APPLY URL, not of `companies.provider`: the provider says where a posting
was found, and the URL says which form the owner lands on. The two questions differ on every lane
copy, which is why this lives apart from the `provider` field and never feeds it.

What the owner's fill tool can handle is theirs, not the product's, so every list here comes from
`<config_dir>/apply-routes.toml` and the repository ships none of them. No file means no routing:
`load_apply_routes` returns an unconfigured result and the page offers only its plain lists.

A label and nothing more. It decides which list a lead is shown in, and fills or submits nothing.
"""

from __future__ import annotations

import json
import tomllib
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

CONFIG_FILENAME = "apply-routes.toml"


class ApplyRoute(StrEnum):
    AUTO = "auto"
    HAND = "hand"
    UNRESOLVED = "unresolved"


class ApplyRoutesConfig(BaseModel):
    """The file's shape. `extra="forbid"` so a misspelled key is reported, never silently unused."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    # Hosts whose forms the owner's tool fills. A listed host also covers its subdomains.
    auto_hosts: tuple[str, ...]
    # Hosts that stand in front of the employer's form, so the URL alone cannot say which form it
    # reaches: job boards, aggregators and link shorteners.
    unresolved_hosts: tuple[str, ...] = ()
    # URL fragments with the same meaning on any host (a company page embedding an ATS).
    unresolved_url_markers: tuple[str, ...] = ()
    # The `unresolved_hosts` with a fillable form of their own, used when no employer link exists.
    native_fill_hosts: tuple[str, ...] = ()
    # Hosts whose application sits behind an account wall (a Workday tenant, a talent portal, an
    # employer careers site). They are applied to by hand like any other `hand` host; listing them
    # buys a reason the viewer can show and a conflict the loader refuses.
    account_wall_hosts: tuple[str, ...] = ()
    # JSON files, `{"<posting_id>": {"company_status": "..."}}`, recording each link check.
    link_ledgers: tuple[Path, ...] = ()
    # The `company_status` values meaning the check finished and found no employer link.
    no_employer_statuses: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _one_answer_per_host(self) -> ApplyRoutesConfig:
        """One host, one answer. A host listed as both walled and fillable is an ambiguity.

        The two readers would not agree about such a config: `route()` reads the wall list first,
        so the lead resolves as a wall and the other list's entry is dead; `is_direct_auto()` reads
        only the fill list, so the same lead still counts as a direct auto in the slate share. The
        overlap is therefore refused at load, naming the host, rather than ranked.
        """
        pairs = (("auto_hosts", self.auto_hosts), ("unresolved_hosts", self.unresolved_hosts))
        for name, other in pairs:
            clashes = sorted(
                wall
                for wall in self.account_wall_hosts
                if any(_covers(wall, entry) for entry in other)
            )
            if clashes:
                raise ValueError(
                    f"account_wall_hosts lists {', '.join(clashes)}, which {name} also covers; "
                    "a host has one route"
                )
        return self


@dataclass(frozen=True)
class ApplyRoutes:
    config: ApplyRoutesConfig | None
    link_status: dict[int, str]
    problem: str | None

    @property
    def configured(self) -> bool:
        return self.config is not None

    def route(self, *, posting_id: int, apply_url: str | None) -> ApplyRoute:
        config = self.config
        if config is None:
            return ApplyRoute.HAND
        host = _host(apply_url)
        # No usable link is not evidence of a form to fill by hand.
        if apply_url is None or host is None:
            return ApplyRoute.UNRESOLVED
        # A walled host is by hand whatever the link ledgers say: the wall is a property of the
        # employer's form, not of the check. Most wall hosts would land on the final `HAND` anyway;
        # this branch is what makes them HAND when the link also carries an embedding marker (the
        # one case where the marker branch below would answer UNRESOLVED). Validation keeps the
        # list clear of the two branches that follow.
        if _matches(host, config.account_wall_hosts):
            return ApplyRoute.HAND
        if _matches(host, config.unresolved_hosts):
            if self.link_status.get(posting_id) not in config.no_employer_statuses:
                return ApplyRoute.UNRESOLVED
            native = _matches(host, config.native_fill_hosts)
            return ApplyRoute.AUTO if native else ApplyRoute.HAND
        if _matches(host, config.auto_hosts):
            return ApplyRoute.AUTO
        lowered = apply_url.lower()
        if any(marker.lower() in lowered for marker in config.unresolved_url_markers):
            finished = self.link_status.get(posting_id) in config.no_employer_statuses
            return ApplyRoute.HAND if finished else ApplyRoute.UNRESOLVED
        return ApplyRoute.HAND

    def account_wall_host(self, *, apply_url: str | None) -> str | None:
        """The configured entry a walled host matches, or None. It is what the reason names."""
        config = self.config
        host = _host(apply_url)
        if config is None or host is None:
            return None
        for entry in config.account_wall_hosts:
            if _matches(host, (entry,)):
                return entry
        return None

    def reason(self, *, posting_id: int, apply_url: str | None) -> str | None:
        """Why this lead is by hand, when the config knows a reason. `None` is "no reason known"."""
        wall = self.account_wall_host(apply_url=apply_url)
        return None if wall is None else f"needs an account on {wall}"

    def is_direct_auto(self, apply_url: str | None) -> bool:
        """True only when the link itself goes straight to a form the fill tool handles.

        Stricter than `route(...) == AUTO`, which also returns AUTO for a board's own native form
        (`native_fill_hosts`) once its employer link check finished empty. Those are aggregator
        leads, and the slate's direct share must not count them. No config, no link, a listed
        aggregator host or an embedding marker all answer False, and no ledger is consulted.
        """
        config = self.config
        host = _host(apply_url)
        if config is None or apply_url is None or host is None:
            return False
        if _matches(host, config.unresolved_hosts) or not _matches(host, config.auto_hosts):
            return False
        lowered = apply_url.lower()
        return not any(marker.lower() in lowered for marker in config.unresolved_url_markers)


def _host(url: str | None) -> str | None:
    if url is None:
        return None
    try:
        return urlsplit(url).hostname or None
    except ValueError:
        return None


def _matches(host: str, hosts: Iterable[str]) -> bool:
    return any(host == entry or host.endswith(f".{entry}") for entry in hosts)


def _covers(a: str, b: str) -> bool:
    """One config entry answers for the other's host: equal, or either is the other's suffix.

    `_matches` only knows host-in-list, so an overlap between two LISTS has to be asked both ways:
    `careers.example.com` and `example.com` are one host's territory whichever list each is in.
    """
    return a == b or a.endswith(f".{b}") or b.endswith(f".{a}")


def _read_ledger(path: Path) -> dict[str, object]:
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("not a JSON object")
    return loaded


def load_apply_routes(config_dir: Path) -> ApplyRoutes:
    """Read the config and its ledgers. Never raises: the queue must draw with routing broken.

    A failure lands in `problem` for the page to say out loud. An unreadable link ledger leaves its
    leads UNRESOLVED, so a failure cannot read as a checked result.
    """
    path = config_dir / CONFIG_FILENAME
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return ApplyRoutes(config=None, link_status={}, problem=None)
    except OSError as exc:
        return _unconfigured(f"{path}: {exc}")
    try:
        config = ApplyRoutesConfig.model_validate(tomllib.loads(raw.decode("utf-8")))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError, ValidationError) as exc:
        return _unconfigured(f"{path}: {exc}")

    problems: list[str] = []
    link_status: dict[int, str] = {}
    for ledger in config.link_ledgers:
        try:
            entries = _read_ledger(ledger)
        except (OSError, ValueError) as exc:
            problems.append(f"{ledger}: {exc}")
            continue
        for key, entry in entries.items():
            status = entry.get("company_status") if isinstance(entry, dict) else None
            if key.isdecimal() and isinstance(status, str):
                link_status[int(key)] = status
    return ApplyRoutes(
        config=config,
        link_status=link_status,
        problem="; ".join(problems) or None,
    )


def _unconfigured(problem: str) -> ApplyRoutes:
    return ApplyRoutes(config=None, link_status={}, problem=problem)
