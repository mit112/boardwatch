"""T366: a value model learned from the judge's own readings — P(the judge clears this posting).

SHADOW ONLY. The score never becomes, changes or counts as a verdict or an abstain, and nothing
here is read by a rule, a lane, a disposition, a ledger row or a hash that routes work (the
keystone invariant): `pipeline/value_shadow.py` records it beside the gate's candidates and
that is all. Pure Python (the venv has no numpy), so the model is one logistic regression over
hashed features, fitted by SGD.

No user data lives here. Company names are hashed features the model learns at run time from
the user's own readings; a user with too few readings gets no model (`pipeline/value_shadow.py`
decides that), never a model that scores zeros.

The features and the label are the benchmark's (`docs/program/TICKETS-2026-09-22c.md`, T366):
title words and bigrams, a trailing level token, company, provider, JD regexes for years and
for the entry/senior vocabulary, and a body-length bucket.
"""

from __future__ import annotations

import math
import random
import re
import zlib
from array import array
from collections.abc import Sequence
from dataclasses import dataclass

#: Hash buckets. A collision only blurs two features; 2^20 keeps that rare at this vocabulary.
HASH_BUCKETS = 1 << 20
#: How much of a body the features read.
BODY_CHARS = 20_000
#: SGD settings. Fixed, so a fit is a function of the readings alone (the shuffle is seeded by
#: the epoch number).
EPOCHS = 8
LEARNING_RATE = 0.1
L2 = 1e-6

_YEARS = re.compile(r"(\d{1,2})\s*\+?\s*(?:-|–|to)?\s*(?:\d{1,2}\s*)?\+?\s*(?:years|yrs)", re.I)
_LEVEL = re.compile(r"\b(L[2-9]|P[1-6]|IV|III|II|I|[1-6])\b(?=\s*(?:$|[-,(–:/|]))")
_WORD = re.compile(r"[a-z0-9+#]+")
_KEYWORDS: dict[str, re.Pattern[str]] = {
    name: re.compile(pattern, re.I)
    for name, pattern in {
        "senior": r"\bsenior\b",
        "staff": r"\bstaff\b",
        "principal": r"\bprincipal\b",
        "lead": r"\blead\b",
        "newgrad": r"new[ -]?grad",
        "entry": r"entry[ -]level",
        "early": r"early[ -]career",
        "recentgrad": r"recent(?:ly)? grad",
        "univ": r"university grad",
        "intern": r"\bintern",
        "phd": r"\bph\.?d",
        "clear": r"clearance",
        "citizen": r"citizen",
        "sponsor": r"sponsor",
        "mentor": r"\bmentor",
        "bachelor": r"bachelor",
        "0-2": r"\b0\s*[-–]\s*[12]\s*years",
    }.items()
}
#: A four-digit year in the text, kept as its own feature per year (the benchmark's `2026` and
#: `2027` literals, without a year hardcoded that goes stale).
_YEAR = re.compile(r"\b(20\d\d)\b")


@dataclass(frozen=True)
class Document:
    """What the features read of one posting."""

    title: str
    company: str
    provider: str
    body: str


def _bucket(feature: str) -> int:
    return zlib.crc32(feature.encode()) % HASH_BUCKETS


def feature_indices(doc: Document) -> array[int]:
    """The hashed feature indices of `doc`. Repeats are kept: a word twice in a title is two
    contributions, as in the benchmark."""
    title = doc.title
    body = doc.body[:BODY_CHARS]
    features = ["b"]
    words = _WORD.findall(title.lower())
    features += ["t:" + w for w in words]
    features += ["tb:" + a + "_" + b for a, b in zip(words, words[1:], strict=False)]
    level = _LEVEL.search(title)
    if level:
        features += ["lvl:" + level.group(1), "colvl:" + doc.company + "|" + level.group(1)]
    features += ["co:" + doc.company, "pv:" + doc.provider]
    years = [int(y) for y in _YEARS.findall(body) if int(y) <= 20]
    if years:
        features += ["ymin:" + str(min(min(years), 8)), "ymax:" + str(min(max(years), 10))]
    else:
        features.append("ynone")
    for name, pattern in _KEYWORDS.items():
        if pattern.search(body):
            features.append("kw:" + name)
        if pattern.search(title):
            features.append("tkw:" + name)
    features += ["yr:" + year for year in sorted(set(_YEAR.findall(body)))]
    features.append("len:" + str(min(len(body) // 1500, 10)))
    return array("I", (_bucket(f) for f in features))


def _sigmoid(z: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, z))))


@dataclass(frozen=True)
class ValueModel:
    """Fitted weights. `score` is P(good) in (0, 1)."""

    weights: array[float]

    def score(self, indices: Sequence[int]) -> float:
        weights = self.weights
        return _sigmoid(sum(weights[j] for j in indices))


def train(examples: Sequence[Sequence[int]], labels: Sequence[bool]) -> ValueModel:
    """Logistic regression by SGD over hashed `examples`, `labels[i]` True for good."""
    if len(examples) != len(labels):
        raise ValueError("one label per example")
    weights = array("d", bytes(8 * HASH_BUCKETS))
    order = list(range(len(examples)))
    for epoch in range(EPOCHS):
        random.Random(epoch).shuffle(order)
        for i in order:
            indices = examples[i]
            gradient = _sigmoid(sum(weights[j] for j in indices)) - (1.0 if labels[i] else 0.0)
            for j in indices:
                weights[j] -= LEARNING_RATE * (gradient + L2 * weights[j])
    return ValueModel(weights)


def auc(scores: Sequence[float], labels: Sequence[bool]) -> float | None:
    """Area under the ROC curve, ties counted half. None when only one class is present."""
    positives = sum(labels)
    negatives = len(labels) - positives
    if not positives or not negatives:
        return None
    ordered = sorted(range(len(scores)), key=scores.__getitem__)
    rank_sum = 0.0
    i = 0
    while i < len(ordered):
        j = i
        while j + 1 < len(ordered) and scores[ordered[j + 1]] == scores[ordered[i]]:
            j += 1
        mean_rank = (i + j) / 2 + 1  # ranks are 1-based; a tie shares the mean of its ranks
        rank_sum += mean_rank * sum(labels[ordered[k]] for k in range(i, j + 1))
        i = j + 1
    return (rank_sum - positives * (positives + 1) / 2) / (positives * negatives)


def top_half_precision(
    scores: Sequence[float], labels: Sequence[bool], order: Sequence[int]
) -> tuple[float, float] | None:
    """(precision of the model's top half, precision of the existing order's first half) over
    one run's items, where `order[i]` is item i's position in the existing order (smaller is
    earlier). The half is `n // 2` items; None below two items."""
    n = len(scores)
    k = n // 2
    if k == 0:
        return None
    by_model = sorted(range(n), key=lambda i: (-scores[i], order[i]))[:k]
    by_order = sorted(range(n), key=order.__getitem__)[:k]
    return (
        sum(labels[i] for i in by_model) / k,
        sum(labels[i] for i in by_order) / k,
    )
