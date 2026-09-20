"""The title-seniority band, resolved once and asked per title.

`rank/seniority_gate.seniority_verdict` is the gate; this is the four inputs it needs, bound
together so every caller derives them the same way. Those inputs are config- and profile-
dependent — the leveling catalog, the company's own level scheme, the operator's target band and
the field tier — which is why they do not belong inside `delivery/review_gate.classify` and are
passed to it as one bit instead (D-477 and `review_gate`'s own note on the T44 member).

It exists because that derivation had grown four copies. `cli/top_cmd.py`, `cli/show_cmd.py`,
`reports/notify.py` and `reports/stats.py` each build it inline for their own report, and
`pipeline/runner._lead_lanes` built a fifth for the lane. A report that disagrees with another
report is a nuisance; a LANE that disagrees with the lane the folder tree used is the second
opinion `_review` exists to prevent (D-332), so the two readers that decide a lane — the run's
pre-tailor split and the standing queue — share this one.

**The band is COMPUTED on every read and never persisted.** The case it exists for is a lead
delivered while `target_seniority_band` was `any` that must re-route the day the band narrows to
`entry`; a bit frozen at delivery time would answer for the target the operator has since
changed. The cost is one catalog parse per read, which is what every caller above already pays.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from boardwatch.core.settings import Settings
from boardwatch.rank.leveling import (
    DEFAULT_FIELD,
    LevelingCatalog,
    LevelScheme,
    load_leveling,
    resolve_schemes,
)
from boardwatch.rank.seniority_gate import TargetBand, seniority_verdict


@dataclass(frozen=True)
class TitleBandReader:
    """`seniority_verdict`'s three config-shaped arguments, bound once, asked per title."""

    catalog: LevelingCatalog
    #: Keyed by `(provider, slug)`, which is what `resolve_schemes` returns and what the company
    #: join supplies — so a company with its own ladder is read against THAT ladder.
    schemes: Mapping[tuple[str, str], LevelScheme]
    target_band: TargetBand

    def above_band(self, title: str, company: tuple[str, str] | None) -> bool:
        """The ONE bit the delivery lane acts on: is this title above the operator's target band?

        `uncertain` and `in_band` are deliberately indistinguishable here, matching
        `review_gate`'s member: only `above_band` ever moves a lead, and an abstain must not be
        spent as though it were a finding. The abstain is still reported — by `top`, which counts
        it — so this narrowing loses no monitoring.

        `company` is `None` for a lead whose board is unknown, which resolves to no scheme and
        makes every level token abstain. That is `resolve_schemes`' own fail direction: losing a
        binding can only show more, never hide a job.
        """
        band, _reason = seniority_verdict(
            title,
            None if company is None else self.schemes.get(company),
            self.target_band,
            self.catalog.fields[DEFAULT_FIELD],
            self.catalog,
        )
        return band == "above_band"


def title_band_reader(settings: Settings, target_band: TargetBand) -> TitleBandReader:
    """Build the reader from the operator's config. One catalog parse; call it once per pass.

    The bindings warning is dropped rather than returned: the four report call sites print it
    beside their own output, and the two lane readers have no console to print it on. Nothing is
    hidden by that — `resolve_schemes` degrades to no bindings, and no binding can ever drop a
    lead, only abstain.
    """
    catalog = load_leveling(settings.config_dir)
    schemes, _binding_warning = resolve_schemes(catalog, settings.config_dir)
    return TitleBandReader(catalog=catalog, schemes=schemes, target_band=target_band)


def profile_target_band(profile: object) -> TargetBand:
    """The operator's target band, read off a `profile` row, defaulting to the inert `any`.

    `any` is the right answer for all three absences — no profile row, a row from before the
    column existed, and a column left empty — because `seniority_verdict` makes the gate inert on
    it and says so. A missing target is not a narrow one.
    """
    return cast(TargetBand, str(getattr(profile, "target_seniority_band", None) or "any"))
