"""Filesystem names for the delivery queue (design §4.1).

Pure by construction: no filesystem access, no clock, no database. `root` is read for its
*length* only, so a name can be planned -- and tested -- without a queue existing.
`tests/unit/test_delivery_names.py` asserts this module's import list, so an accidental
`import time` or `from boardwatch.store import ...` fails the suite instead of the review.

Two boundaries this module deliberately does NOT own:

- Disambiguating a name that collides with a *different* posting. That needs to know what is
  already on disk, which is I/O; `delivery/queue.py` owns it. What is guaranteed here is only
  that different input text yields different names.
- Keeping the unslugged company and title. Slugging is lossy on purpose, and `details.json`
  carries the originals.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

#: Per-name byte cap. Both the folder and the PDF stay within it.
COMPONENT_BYTE_CAP = 200
#: Cap on the whole `<root>/<drain>/<folder>/<pdf>` destination, in UTF-8 bytes. Windows
#: MAX_PATH is 260; the 20 bytes of headroom absorb a `.tmp` staging suffix.
DESTINATION_BYTE_CAP = 240
#: Where a lead ends up once it leaves the queue. The budget is computed against the longest
#: of these, so a name that is legal in the queue is still legal after it drains.
#:
#: THE single source of truth for the drain set: `delivery/queue.py` derives `_LOCATIONS` from
#: this rather than keeping its own list. The dependency has to run this way round because this
#: module is pure and `queue.py` is not. Adding a drain here and nowhere else is the whole point
#: -- `_ineligible` is 11 bytes against the others' 8, and while it was listed only in
#: `queue.py` every planned name was under-priced by 3 bytes, so `NameBudgetError` accepted
#: names whose drained destination it had promised to refuse.
DRAIN_DIRS: tuple[str, ...] = ("_applied", "_skipped", "_ineligible", "_review")

PDF_SUFFIX = ".pdf"

#: Reserved on Windows with or without an extension, in any case. A closed catalog: an
#: out-of-catalog name is a normal name, never a new bucket.
RESERVED_DEVICE_NAMES: frozenset[str] = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{index}" for index in range(1, 10)}
    | {f"LPT{index}" for index in range(1, 10)}
)

_SEPARATOR = "_"
_FALLBACK_STEM = "posting"
_HASH_LEN = 8
# The folder's "_", the path separator between folder and file, and the PDF's two "_".
_SEPARATOR_BYTES = 4
_FIXED_BYTES = _SEPARATOR_BYTES + len(PDF_SUFFIX)
_SEPARATOR_RUN = re.compile(r"_+")
# Windows rejects a trailing dot or space; a leading one is legal but invisible.
_STRIPPED_EDGES = "_. "


class NameBudgetError(ValueError):
    """The queue root is so long that no name can fit the destination cap.

    Raised before anything is created, and only when even the shortest possible names
    overflow. Letting it through instead would surface as an unexplained write failure on
    Windows, far from the choice that caused it.
    """


@dataclass(frozen=True)
class LeadNames:
    """One lead's queue folder and the résumé filename inside it."""

    folder: str
    pdf: str


def slug(value: str) -> str:
    """A single filesystem-safe path component, or `""` when `value` yields no usable name.

    `""` is the one rejection channel, and it means either "nothing survived" or "what
    survived is a Windows reserved device name". Callers substitute their own fallback --
    see `plan_lead_names`. Non-ASCII letters survive: a real title may be French or
    Japanese, and transliterating it would be a worse name, not a safer one.
    """
    normalized = unicodedata.normalize("NFC", value)
    swapped = "".join(char if _is_name_char(char) else _SEPARATOR for char in normalized)
    collapsed = _SEPARATOR_RUN.sub(_SEPARATOR, swapped).strip(_STRIPPED_EDGES)
    if not collapsed or collapsed.upper() in RESERVED_DEVICE_NAMES:
        return ""
    return collapsed


def plan_lead_names(
    *,
    root: Path,
    owner_name: str,
    company: str,
    title: str,
    identity_hash: str,
) -> LeadNames:
    """Plan `<root>/<folder>/<pdf>` for one lead. Deterministic in its arguments alone.

    The budget is taken against the longest final destination rather than the queue path,
    and in UTF-8 bytes rather than characters, because both caps are filesystem limits and
    a filesystem counts bytes.

    `root` must already be resolved: the budget is only as honest as the root it is given,
    and a relative root would price a path shorter than the one that gets written.

    Raises `NameBudgetError` when `root` is so long that no name can fit.
    """
    prefix = _prefix_bytes(root)
    owner = _component(owner_name, identity_hash)
    org = _component(company, identity_hash)
    role = _component(title, identity_hash)

    # The title gives way first, then the company, and the owner's own name last.
    role = _fit(role, _paired_cap(prefix, single=owner, paired=org), identity_hash)
    org = _fit(org, _paired_cap(prefix, single=owner, paired=role), identity_hash)
    owner = _fit(owner, _single_cap(prefix, paired_a=org, paired_b=role), identity_hash)

    names = LeadNames(
        folder=f"{org}{_SEPARATOR}{role}",
        pdf=f"{owner}{_SEPARATOR}{org}{_SEPARATOR}{role}{PDF_SUFFIX}",
    )
    overflow = _destination_bytes(prefix, names) - DESTINATION_BYTE_CAP
    if overflow > 0:
        raise NameBudgetError(
            f"queue root is {overflow} bytes too long: the shortest possible names still "
            f"need {_destination_bytes(prefix, names)} bytes of destination path against a "
            f"cap of {DESTINATION_BYTE_CAP}"
        )
    return names


def _is_name_char(char: str) -> bool:
    """Letters, combining marks and decimal digits survive; everything else is a separator.

    Replacing rather than deleting is what makes `Backend/Infra` read as two words. It also
    subsumes the Windows-illegal set `< > : " / \\ | ? *`, every control character, and the
    dots and spaces Windows will not accept at an edge -- none of them is a letter, a mark
    or a digit, so none needs its own rule.
    """
    category = unicodedata.category(char)
    return category.startswith(("L", "M")) or category == "Nd"


def _component(value: str, identity_hash: str) -> str:
    """`value` slugged, or `posting_<hash>`. Never empty."""
    return slug(value) or f"{_FALLBACK_STEM}{_SEPARATOR}{_short_hash(identity_hash)}"


def _fit(text: str, cap: int, identity_hash: str) -> str:
    """`text` within `cap` bytes, never below the hash floor and never empty."""
    return _truncate(text, max(cap, _HASH_LEN), identity_hash)


def _truncate(text: str, cap: int, identity_hash: str) -> str:
    """`text` within `cap` UTF-8 bytes, with a stable hash suffix when it had to be cut."""
    if _byte_len(text) <= cap:
        return text
    # The suffix keys on the whole text as well as on the posting: two long titles for one
    # posting can share every retained byte, and an identity-only suffix would collide.
    suffix = _short_hash(identity_hash, text)
    head = _cut(text, cap - _HASH_LEN - len(_SEPARATOR))
    return f"{head}{_SEPARATOR}{suffix}" if head else suffix


def _cut(text: str, budget: int) -> str:
    """The longest prefix of `text` inside `budget` bytes that ends a whole grapheme.

    Cutting the encoded bytes is what makes the byte budget honest, but a blind cut splits
    a multi-byte character, and a cut that respects characters can still orphan a combining
    mark from its base. Both are backed off here.
    """
    if budget <= 0:
        return ""
    data = text.encode("utf-8")
    if len(data) <= budget:
        return text
    end = budget
    while end > 0 and (data[end] & 0xC0) == 0x80:  # a UTF-8 continuation byte
        end -= 1
    kept = data[:end].decode("utf-8")
    # A grapheme is a base plus the marks that follow it, so the cut is inside one exactly
    # when the first dropped character is a mark. Give back whole characters until it is not.
    while kept and unicodedata.category(text[len(kept)]).startswith("M"):
        kept = kept[:-1]
    return kept.rstrip(_STRIPPED_EDGES)


def _short_hash(*parts: str) -> str:
    """A stable short digest. `hashlib`, never `hash()`, which is salted per process."""
    joined = "\x00".join(parts).encode("utf-8")
    return hashlib.sha256(joined).hexdigest()[:_HASH_LEN]


def _byte_len(text: str) -> int:
    return len(text.encode("utf-8"))


def _prefix_bytes(root: Path) -> int:
    """Bytes of `<root>/<longest drain dir>/`, the fixed head of the longest destination.

    `Path` is used for its arithmetic only -- no member of `root` is ever consulted.
    """
    longest_drain = max(sorted(DRAIN_DIRS), key=len)
    return _byte_len(str(root / longest_drain)) + len("/")


def _destination_bytes(prefix: int, names: LeadNames) -> int:
    return prefix + _byte_len(names.folder) + len("/") + _byte_len(names.pdf)


def _paired_cap(prefix: int, *, single: str, paired: str) -> int:
    """The cap for a component that appears in both names (the company and the title).

    A byte saved here saves two bytes of destination, hence the halving.
    """
    one = _byte_len(single)
    two = _byte_len(paired)
    return min(
        COMPONENT_BYTE_CAP - two - 1,
        COMPONENT_BYTE_CAP - one - two - 2 - len(PDF_SUFFIX),
        (DESTINATION_BYTE_CAP - prefix - one - 2 * two - _FIXED_BYTES) // 2,
    )


def _single_cap(prefix: int, *, paired_a: str, paired_b: str) -> int:
    """The cap for the owner's name, which appears in the PDF filename only."""
    one = _byte_len(paired_a)
    two = _byte_len(paired_b)
    return min(
        COMPONENT_BYTE_CAP - one - two - 2 - len(PDF_SUFFIX),
        DESTINATION_BYTE_CAP - prefix - 2 * one - 2 * two - _FIXED_BYTES,
    )
