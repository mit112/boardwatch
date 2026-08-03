from __future__ import annotations

import random
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import pytest

from boardwatch.extract.taxonomy import load_taxonomy
from boardwatch.tailor.apply import apply_plan
from boardwatch.tailor.equivalences import load_equivalences
from boardwatch.tailor.model import Bullet, Entry, Resume, SkillGroup
from boardwatch.tailor.plan import (
    Delete,
    EquivalenceSwap,
    Op,
    Reorder,
    Select,
    TailorPlan,
    build_plan,
)
from boardwatch.tailor.safety import (
    TierASafetyError,
    enforce_tier_a,
    output_is_entailed,
    plan_is_structurally_safe,
)
from boardwatch.tailor.tokens import has_whole_token, toks, whole_token_sub

TBL = load_equivalences()
TAX = load_taxonomy(Path("/nonexistent"))


def M() -> Resume:
    return Resume(
        header=["h"],
        education=[],
        skill_groups=[],
        entries=[
            Entry(
                entry_id="e1",
                heading="H",
                bullets=[
                    Bullet(bullet_id="b1", text="Shipped JS"),
                    Bullet(bullet_id="b2", text="Built Python service"),
                ],
            )
        ],
    )


def test_legit_tailoring_is_entailed() -> None:
    m = M()
    plan = build_plan(m, {"JavaScript", "Python"}, TBL, TAX)
    t = apply_plan(m, plan, TBL)
    assert output_is_entailed(m, t, TBL)
    enforce_tier_a(m, t, plan, TBL)  # no raise


def test_added_token_rejected() -> None:
    m = M()
    bad = m.model_copy(
        update={
            "entries": [
                m.entries[0].model_copy(
                    update={
                        "bullets": [
                            m.entries[0].bullets[0].model_copy(
                                update={"text": "Shipped JS at massive scale"}
                            )
                        ],
                    }
                )
            ]
        }
    )
    assert not output_is_entailed(m, bad, TBL)


def test_non_table_swap_rejected_by_output_check() -> None:
    m = M()
    bad = m.model_copy(
        update={
            "entries": [
                m.entries[0].model_copy(
                    update={
                        "bullets": [
                            m.entries[0].bullets[0].model_copy(
                                update={"text": "Shipped Golang"}
                            )
                        ]
                    }
                )
            ]
        }
    )
    assert not output_is_entailed(m, bad, TBL)


def test_altered_non_bullet_region_rejected() -> None:
    m = M()
    plan = build_plan(m, {"Python"}, TBL, TAX)
    t = apply_plan(m, plan, TBL)
    tampered = t.model_copy(update={"header": ["different"]})
    with pytest.raises(TierASafetyError):
        enforce_tier_a(m, tampered, plan, TBL)


# --- plan_is_structurally_safe branch coverage ---


def test_structurally_safe_accepts_valid_plan() -> None:
    m = M()
    plan = build_plan(m, {"JavaScript", "Python"}, TBL, TAX)
    assert plan_is_structurally_safe(m, plan, TBL)


def test_structural_unknown_bullet_id_rejected() -> None:
    m = M()
    plan = TailorPlan(ops=(Delete(bullet_id="nope"),))
    assert not plan_is_structurally_safe(m, plan, TBL)


def test_structural_unknown_entry_id_rejected() -> None:
    m = M()
    plan = TailorPlan(ops=(Reorder(entry_id="nope", order=("b1",)),))
    assert not plan_is_structurally_safe(m, plan, TBL)


def test_structural_non_table_pair_rejected() -> None:
    m = M()
    plan = TailorPlan(
        ops=(EquivalenceSwap(bullet_id="b1", from_phrase="JS", to_phrase="Golang"),)
    )
    assert not plan_is_structurally_safe(m, plan, TBL)


def test_structural_swap_from_phrase_not_whole_token_rejected() -> None:
    # AM-4: from_phrase must appear as a whole token in the referenced master bullet.
    # b2 = "Built Python service" does not contain "JS" as a whole token.
    m = M()
    plan = TailorPlan(
        ops=(EquivalenceSwap(bullet_id="b2", from_phrase="JS", to_phrase="JavaScript"),)
    )
    assert not plan_is_structurally_safe(m, plan, TBL)


# ---------------------------------------------------------------------------
# Seeded generated-case safety sweep (design §8 "Guarantee (headline)":
# "A seeded generated-case sweep (no Hypothesis in-repo) composes random valid
# plans over random masters").
#
# One fixed seed => one fixed corpus, so any failure is reproducible verbatim;
# every assertion prints the offending master/plan/tailored triple. The sweep
# asserts BOTH directions of the L6 guarantee: enforce_tier_a accepts every
# generated legitimate Tier A tailoring, and rejects every generated
# illegitimate mutation of one.
# ---------------------------------------------------------------------------

SWEEP_SEED = 20260802
SWEEP_CASES = 200

_PAIRS = TBL.as_pairs()
_FROMS = tuple(p.from_phrase for p in _PAIRS)
_IMAGES = tuple(p.to_phrase for p in _PAIRS)
# Both casings: the whole-token matcher is case-insensitive, the image is canonical.
_SWAPPABLE = _FROMS + tuple(f.lower() for f in _FROMS)
_WORDS = (
    "Shipped", "Built", "Owned", "Reduced", "latency", "service", "pipeline",
    "Python", "Kubernetes", "Docker", "Kafka", "team",
)
_PUNCT = (
    '"', "\\", "#", "{", "}", "(", ")", "[", "]", "<", ">", ",", ".", ";", ":",
    "!", "?", "%", "+", "-", "*", "/", "&", "|", "~", "`", "'", "$", "@", "=",
)
_NUMBERS = ("3", "42", "10x", "99")
_POOL = _WORDS + _SWAPPABLE + _IMAGES + _PUNCT + _NUMBERS
# Single \w tokens that are in neither the pool nor the table: any of these in an
# output is, by construction, fabrication.
_FABRICATED = ("Golang", "Elixir", "Fabricated", "1000x")
_JD_VOCAB = list(_IMAGES) + ["Python", "Kubernetes", "Docker", "Kafka"]

_MUTATION_CLASSES = (
    "fabricated_token_inserted",
    "token_deleted",
    "swap_not_in_table",
    "swap_from_not_whole_token",
    "cross_bullet_text_move",
    "non_permutation_reorder",
    "reorder_order_ids_not_in_entry",
    "unknown_bullet_id_in_plan",
    "orphan_bullet_in_output",
    "entry_dropped_from_output",
    "heading_rewritten",
)


def _anchor(bullet_id: str) -> str:
    """A \\w token unique to one bullet: never swappable, never a table image.

    Every generated bullet carries exactly one. It gives the mutations airtight
    preconditions: it survives any legitimate swap, so replacing it (or moving it
    to another bullet) is unambiguously not derivable from the master.
    """
    return f"proj_{bullet_id}"


def _bullet_text(rng: random.Random, bullet_id: str) -> str:
    tokens = [rng.choice(_POOL) for _ in range(rng.randint(2, 7))]
    tokens.insert(rng.randint(0, len(tokens)), _anchor(bullet_id))
    return " ".join(tokens)


def _random_master(rng: random.Random) -> Resume:
    entries = []
    for ei in range(rng.randint(2, 3)):  # >= 2 entries so cross-entry mutations exist
        bullets = []
        for bi in range(rng.randint(1, 8)):  # spans the MAX_BULLETS_PER_ENTRY=6 cut-line
            bid = f"e{ei}b{bi}"
            bullets.append(Bullet(bullet_id=bid, text=_bullet_text(rng, bid)))
        entries.append(Entry(entry_id=f"e{ei}", heading=f"Role {ei}", bullets=bullets))
    return Resume(
        header=["Ada Lovelace", "ada@example.com"],
        education=["Some School — BS"],
        skill_groups=[SkillGroup(label="Languages", items=["Python", "JS"])],
        entries=entries,
    )


def _swaps_for(rng: random.Random, text: str) -> list[tuple[str, str]]:
    """Legitimate table swaps for `text`, in table order, with no swap chaining."""
    chosen: list[tuple[str, str]] = []
    used: set[str] = set()
    for p in _PAIRS:
        if not has_whole_token(text, p.from_phrase) or rng.random() < 0.3:
            continue
        # Never let one swap's image feed another swap's input: only swaps whose
        # `from` is a whole token of the *master* are legitimate (L6a).
        if p.from_phrase.lower() in used or p.to_phrase.lower() in used:
            continue
        used |= {p.from_phrase.lower(), p.to_phrase.lower()}
        chosen.append((p.from_phrase, p.to_phrase))
    return chosen


def _random_legit_plan(rng: random.Random, master: Resume) -> TailorPlan:
    """A random plan using only Tier A ops, keeping >= 1 bullet per entry."""
    ops: list[Op] = []
    for e in master.entries:
        n = len(e.bullets)
        dropped = set(rng.sample(range(n), rng.randint(0, n - 1)))
        for i in sorted(dropped):
            bid = e.bullets[i].bullet_id
            ops.append(
                Delete(bullet_id=bid)
                if rng.random() < 0.5
                else Select(bullet_id=bid, keep=False)
            )
        kept = [b for i, b in enumerate(e.bullets) if i not in dropped]
        if rng.random() < 0.85:
            rng.shuffle(kept)
            ops.append(Reorder(entry_id=e.entry_id, order=tuple(b.bullet_id for b in kept)))
        for b in kept:
            if rng.random() < 0.25:
                ops.append(Select(bullet_id=b.bullet_id, keep=True))
            for frm, to in _swaps_for(rng, b.text):
                ops.append(
                    EquivalenceSwap(bullet_id=b.bullet_id, from_phrase=frm, to_phrase=to)
                )
    return TailorPlan(ops=tuple(ops))


def _set_bullets(resume: Resume, entry_idx: int, bullets: list[Bullet]) -> Resume:
    entries = list(resume.entries)
    entries[entry_idx] = entries[entry_idx].model_copy(update={"bullets": bullets})
    return resume.model_copy(update={"entries": entries})


def _retext(resume: Resume, entry_idx: int, bullet_idx: int, text: str) -> Resume:
    bullets = list(resume.entries[entry_idx].bullets)
    bullets[bullet_idx] = bullets[bullet_idx].model_copy(update={"text": text})
    return _set_bullets(resume, entry_idx, bullets)


def _mutations(
    rng: random.Random, master: Resume, plan: TailorPlan, tailored: Resume
) -> list[tuple[str, TailorPlan, Resume]]:
    """Illegitimate (plan, tailored) pairs derived from a legitimate one."""
    m_text = {b.bullet_id: b.text for e in master.entries for b in e.bullets}
    pos = [(ei, bi) for ei, e in enumerate(tailored.entries) for bi in range(len(e.bullets))]
    out: list[tuple[str, TailorPlan, Resume]] = []

    # (1) a fabricated token appears in an output bullet
    ei, bi = rng.choice(pos)
    tokens = toks(tailored.entries[ei].bullets[bi].text)
    tokens.insert(rng.randint(0, len(tokens)), rng.choice(_FABRICATED))
    out.append(("fabricated_token_inserted", plan, _retext(tailored, ei, bi, " ".join(tokens))))

    # (2) a master token is silently dropped from an output bullet
    ei, bi = rng.choice(pos)
    tokens = toks(tailored.entries[ei].bullets[bi].text)
    del tokens[rng.randrange(len(tokens))]
    out.append(("token_deleted", plan, _retext(tailored, ei, bi, " ".join(tokens))))

    # (3) a swap that is NOT in the frozen table, applied as a real whole-token sub
    ei, bi = rng.choice(pos)
    tb = tailored.entries[ei].bullets[bi]
    frm, to = _anchor(tb.bullet_id), rng.choice(_FABRICATED)
    swapped = whole_token_sub(tb.text, frm, to)
    assert swapped is not None, f"anchor {frm!r} vanished from {tb.text!r}"
    out.append((
        "swap_not_in_table",
        TailorPlan(ops=(
            *plan.ops,
            EquivalenceSwap(bullet_id=tb.bullet_id, from_phrase=frm, to_phrase=to),
        )),
        _retext(tailored, ei, bi, swapped),
    ))

    # (4) a real table pair, but `from` is not a whole token of the master bullet
    combos = [
        (tailored.entries[e_i].bullets[b_i].bullet_id, p.from_phrase, p.to_phrase)
        for e_i, b_i in pos
        for p in _PAIRS
        if not has_whole_token(m_text[tailored.entries[e_i].bullets[b_i].bullet_id], p.from_phrase)
    ]
    if combos:
        bid, frm, to = rng.choice(combos)
        out.append((
            "swap_from_not_whole_token",
            TailorPlan(ops=(
                *plan.ops,
                EquivalenceSwap(bullet_id=bid, from_phrase=frm, to_phrase=to),
            )),
            tailored,  # output is the legitimate one: only the plan check can catch this
        ))

    # (5) text moved between two bullets (each bullet must stand on its own master)
    (e1, b1), (e2, b2) = rng.sample(pos, 2)
    src, dst = tailored.entries[e1].bullets[b1], tailored.entries[e2].bullets[b2]
    t1, t2 = toks(src.text), toks(dst.text)
    if rng.random() < 0.5:
        # length-preserving: exchange the two bullets' unique anchor tokens
        a1, a2 = _anchor(src.bullet_id), _anchor(dst.bullet_id)
        t1 = [a2 if tok == a1 else tok for tok in t1]
        t2 = [a1 if tok == a2 else tok for tok in t2]
    else:
        t2.insert(rng.randint(0, len(t2)), t1.pop(rng.randrange(len(t1))))
    moved = _retext(_retext(tailored, e1, b1, " ".join(t1)), e2, b2, " ".join(t2))
    out.append(("cross_bullet_text_move", plan, moved))

    # (6) a Reorder that is not a permutation of its entry: it pulls in a bullet
    #     belonging to another entry, and the output follows the plan.
    ea, eb = rng.sample(range(len(tailored.entries)), 2)
    stolen = rng.choice(tailored.entries[eb].bullets)
    new_a = [*tailored.entries[ea].bullets, stolen]
    new_b = [b for b in tailored.entries[eb].bullets if b.bullet_id != stolen.bullet_id]
    out.append((
        "non_permutation_reorder",
        TailorPlan(ops=(
            *plan.ops,
            Reorder(
                entry_id=tailored.entries[ea].entry_id,
                order=tuple(b.bullet_id for b in new_a),
            ),
        )),
        _set_bullets(_set_bullets(tailored, ea, new_a), eb, new_b),
    ))

    # (6b) the *incoherent* variant: the output is perfectly legitimate, but the plan
    #      carries a Reorder whose order names ids from another entry and ids that exist
    #      nowhere. apply_plan would refuse this pairing, so only plan_is_structurally_safe
    #      can catch it — this is the regression guard for that limb standing on its own.
    other = [b.bullet_id for b in tailored.entries[eb].bullets]
    out.append((
        "reorder_order_ids_not_in_entry",
        TailorPlan(ops=(
            *plan.ops,
            Reorder(
                entry_id=tailored.entries[ea].entry_id,
                order=(*other, f"nowhere-{rng.randrange(10**6)}"),
            ),
        )),
        tailored,
    ))

    # (7) an op referencing a bullet that does not exist in the master
    ghost = f"ghost-{rng.randrange(10**6)}"
    ghost_ops: list[Op] = [
        Delete(bullet_id=ghost),
        Select(bullet_id=ghost, keep=True),
        EquivalenceSwap(
            bullet_id=ghost, from_phrase=_PAIRS[0].from_phrase, to_phrase=_PAIRS[0].to_phrase
        ),
    ]
    out.append((
        "unknown_bullet_id_in_plan",
        TailorPlan(ops=(*plan.ops, rng.choice(ghost_ops))),
        tailored,
    ))

    # (8) an output bullet that maps to no master bullet (§8 case iii)
    ei, bi = rng.choice(pos)
    bullets = list(tailored.entries[ei].bullets)
    bullets[bi] = bullets[bi].model_copy(update={"bullet_id": f"ghost-{rng.randrange(10**6)}"})
    out.append(("orphan_bullet_in_output", plan, _set_bullets(tailored, ei, bullets)))

    # (9) + (10) non-bullet regions must equal the master's (L6b)
    drop = rng.randrange(len(tailored.entries))
    dropped_entries = [e for i, e in enumerate(tailored.entries) if i != drop]
    out.append((
        "entry_dropped_from_output",
        plan,
        tailored.model_copy(update={"entries": dropped_entries}),
    ))

    touch = rng.randrange(len(tailored.entries))
    retitled = list(tailored.entries)
    retitled[touch] = retitled[touch].model_copy(update={"heading": "Chief Fabrication Officer"})
    out.append(("heading_rewritten", plan, tailored.model_copy(update={"entries": retitled})))

    return out


@dataclass(frozen=True)
class _Case:
    index: int
    master: Resume
    plan: TailorPlan
    tailored: Resume
    mutations: tuple[tuple[str, TailorPlan, Resume], ...]


def _build_case(rng: random.Random, index: int) -> _Case:
    master = _random_master(rng)
    if rng.random() < 0.25:
        # Also sweep the real selector's output, including the identity plan (jd empty).
        jd = set(rng.sample(_JD_VOCAB, rng.randint(0, 4)))
        plan = build_plan(master, jd, TBL, TAX)
    else:
        plan = _random_legit_plan(rng, master)
    tailored = apply_plan(master, plan, TBL)
    return _Case(index, master, plan, tailored, tuple(_mutations(rng, master, plan, tailored)))


def _build_corpus(n: int) -> tuple[_Case, ...]:
    rng = random.Random(SWEEP_SEED)
    return tuple(_build_case(rng, i) for i in range(n))


@lru_cache(maxsize=1)
def _sweep_cases() -> tuple[_Case, ...]:
    return _build_corpus(SWEEP_CASES)


def _show(case: _Case, label: str, plan: TailorPlan, tailored: Resume) -> str:
    def shown(r: Resume) -> list[list[str]]:
        return [[f"{b.bullet_id}={b.text!r}" for b in e.bullets] for e in r.entries]

    return (
        f"\n  seed={SWEEP_SEED} case={case.index} mutation={label}"
        f"\n  master  ={shown(case.master)}"
        f"\n  tailored={shown(tailored)}"
        f"\n  plan    ={[f'{type(op).__name__}{op.model_dump()}' for op in plan.ops]}"
    )


def test_sweep_accepts_generated_legitimate_plans() -> None:
    for case in _sweep_cases():
        assert output_is_entailed(case.master, case.tailored, TBL), _show(
            case, "legitimate", case.plan, case.tailored
        )
        try:
            enforce_tier_a(case.master, case.tailored, case.plan, TBL)
        except TierASafetyError as exc:  # pragma: no cover - only on regression
            pytest.fail(
                f"legitimate Tier A case REJECTED ({exc})"
                + _show(case, "legitimate", case.plan, case.tailored)
            )


def test_sweep_rejects_generated_illegitimate_mutations() -> None:
    for case in _sweep_cases():
        for label, plan, tailored in case.mutations:
            try:
                enforce_tier_a(case.master, tailored, plan, TBL)
            except TierASafetyError:
                continue
            pytest.fail(  # pragma: no cover - only on regression
                "illegitimate mutation ACCEPTED by enforce_tier_a"
                + _show(case, label, plan, tailored)
            )


def test_sweep_exercises_every_mutation_class() -> None:
    # A mutation whose preconditions stopped holding would otherwise vanish silently.
    counts = Counter(label for case in _sweep_cases() for label, _, _ in case.mutations)
    assert set(counts) == set(_MUTATION_CLASSES)
    for label in _MUTATION_CLASSES:
        assert counts[label] >= SWEEP_CASES // 2, f"{label} fired only {counts[label]}x"


def test_sweep_corpus_is_reproducible_for_a_fixed_seed() -> None:
    prefix = 25
    assert _build_corpus(prefix) == _sweep_cases()[:prefix]
