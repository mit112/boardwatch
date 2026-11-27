"""T366: the value model's pure parts — features, the fit, and the metrics it is judged by.

Expected values come from the construction of each fixture (a planted rule, a hand count) or
from the definition of the metric, never from running the implementation's own path again.
"""

from __future__ import annotations

import random
import zlib

import pytest

from boardwatch.rank.value_model import (
    HASH_BUCKETS,
    Document,
    auc,
    feature_indices,
    top_half_precision,
    train,
)


def bucket(feature: str) -> int:
    """The spec's hash: crc32 of the feature name, modulo 2^20 (stable across processes)."""
    return zlib.crc32(feature.encode()) % (1 << 20)


def test_features_are_hashed_crc32_buckets_of_named_features() -> None:
    doc = Document(
        title="Software Engineer II",
        company="Acme",
        provider="greenhouse",
        body="New grad welcome. Requires 3 years or a bachelor degree. Clearance not needed.",
    )
    got = set(feature_indices(doc))
    expected = {
        bucket(name)
        for name in (
            "b", "t:software", "t:engineer", "t:ii", "tb:software_engineer", "tb:engineer_ii",
            "lvl:II", "colvl:Acme|II", "co:Acme", "pv:greenhouse",
            "kw:newgrad", "kw:bachelor", "kw:clear",
            "ymin:3", "ymax:3", "len:0",
        )
    }
    assert got == expected
    assert HASH_BUCKETS == 1 << 20 and max(got) < HASH_BUCKETS


def test_a_body_without_a_years_figure_reads_ynone_and_a_title_keyword_is_its_own_feature() -> None:
    got = set(feature_indices(Document("Senior Data Engineer", "Acme", "lever", "Join us in 2027.")))
    assert bucket("ynone") in got
    assert {bucket("tkw:senior"), bucket("yr:2027")} <= got
    assert bucket("kw:senior") not in got  # the body does not say it


@pytest.mark.parametrize(
    ("title", "level"),
    [("Engineer 3", "3"), ("Engineer L5", "L5"), ("Engineer, III", "III"), ("Engineer - P2", "P2")],
)
def test_a_trailing_level_token_is_a_feature(title: str, level: str) -> None:
    assert bucket("lvl:" + level) in set(feature_indices(Document(title, "Acme", "x", "")))


def test_a_level_in_the_middle_of_a_title_is_not_a_level() -> None:
    assert bucket("lvl:3") not in set(feature_indices(Document("3 Engineer Roles", "A", "x", "")))


def test_auc_matches_the_pair_counting_definition() -> None:
    # The textbook example: positives 0.35 and 0.8 against negatives 0.1 and 0.4 — 3 of the 4
    # (positive, negative) pairs are ordered correctly.
    assert auc([0.1, 0.4, 0.35, 0.8], [False, False, True, True]) == 0.75
    assert auc([0.9, 0.8, 0.2, 0.1], [True, True, False, False]) == 1.0
    assert auc([0.9, 0.8, 0.2, 0.1], [False, False, True, True]) == 0.0
    assert auc([0.5, 0.5, 0.5, 0.5], [True, False, True, False]) == 0.5  # ties count half
    assert auc([0.3, 0.6], [True, True]) is None  # one class has no AUC


def test_top_half_precision_compares_the_models_half_to_the_existing_orders_half() -> None:
    # Six items in existing order 0..5; the good ones are items 3, 4, 5 — the existing order's
    # first half (0, 1, 2) holds none of them, and the model scores exactly those three highest.
    scores = [0.1, 0.2, 0.3, 0.9, 0.8, 0.7]
    labels = [False, False, False, True, True, True]
    assert top_half_precision(scores, labels, order=[0, 1, 2, 3, 4, 5]) == (1.0, 0.0)
    assert top_half_precision([0.5], [True], order=[0]) is None


def test_a_zero_to_two_years_phrase_is_its_own_feature() -> None:
    assert bucket("kw:0-2") in set(feature_indices(Document("Engineer", "A", "x", "Needs 0-2 years.")))


def _planted(n: int, seed: int) -> list[tuple[Document, bool]]:
    """Good exactly when the title holds one of 20 marker words (`w0`..`w19`) out of a
    200-word vocabulary. Many markers, so no one feature's chance weight decides the shuffled
    control below."""
    rng = random.Random(seed)
    out = []
    for _ in range(n):
        words = [f"w{rng.randrange(200)}" for _ in range(5)]
        out.append((Document(" ".join(words), "Acme", "greenhouse", ""),
                    any(int(w[1:]) < 20 for w in words)))
    return out


def _fit_and_score(rows: list[tuple[Document, bool]], labels: list[bool], cut: int) -> float | None:
    xs = [feature_indices(doc) for doc, _ in rows]
    model = train(xs[:cut], labels[:cut])
    return auc([model.score(x) for x in xs[cut:]], [label for _, label in rows[cut:]])


def test_a_feature_that_determines_the_label_is_learned() -> None:
    rows = _planted(20000, seed=1)
    area = _fit_and_score(rows, [label for _, label in rows], cut=8000)
    assert area is not None and area > 0.97


def test_shuffled_training_labels_read_chance_over_five_seeds() -> None:
    """The null control: the same fit on the same features with the labels' link to the rows cut
    reads 0.5, so the planted result above is the signal and not the apparatus."""
    rows = _planted(20000, seed=1)
    for seed in range(5):
        shuffled = [label for _, label in rows[:8000]]
        random.Random(100 + seed).shuffle(shuffled)
        area = _fit_and_score(rows, shuffled + [label for _, label in rows[8000:]], cut=8000)
        assert area is not None and abs(area - 0.5) < 0.05, (seed, area)


def test_a_fit_is_a_function_of_the_readings_alone() -> None:
    rows = _planted(300, seed=2)
    xs = [feature_indices(doc) for doc, _ in rows]
    labels = [label for _, label in rows]
    first, second = train(xs, labels), train(xs, labels)
    assert [first.score(x) for x in xs[:20]] == [second.score(x) for x in xs[:20]]


def test_train_refuses_mismatched_inputs() -> None:
    with pytest.raises(ValueError):
        train([feature_indices(Document("a", "b", "c", ""))], [True, False])
