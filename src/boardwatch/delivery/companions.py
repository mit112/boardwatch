"""Companion status documents: `<data_dir>/companions/<name>.json` (T294).

External tools (a nightly reviewer, an apply planner) report their own state by writing one small
versioned JSON document each. boardwatch never learns their paths or formats; it validates the
documents and serves them unchanged. The contract is in `docs/companions.md`.

An unreadable document is reported as `failed: unreadable status`, never dropped: a status that
cannot be read is a monitoring failure, not a silence.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

SCHEMA = "boardwatch.companion/1"
STATES = frozenset({"ok", "running", "failed", "stale"})
_ITEM_KEYS = frozenset({"label", "reason", "link", "needs_owner"})


class _Invalid(ValueError):
    pass


def _str(doc: dict[str, Any], key: str) -> str:
    value = doc.get(key)
    if not isinstance(value, str) or not value:
        raise _Invalid(f"{key} must be a non-empty string")
    return value


def _validate(doc: object, stem: str) -> dict[str, Any]:
    if not isinstance(doc, dict):
        raise _Invalid("not a JSON object")
    if doc.get("schema") != SCHEMA:
        raise _Invalid(f"schema must be {SCHEMA}")
    if _str(doc, "name") != stem:
        raise _Invalid("name must match the file name")
    try:
        stamp = datetime.fromisoformat(_str(doc, "updated_at"))
    except ValueError as exc:
        raise _Invalid("updated_at must be ISO 8601") from exc
    if stamp.tzinfo is None:
        raise _Invalid("updated_at must carry a UTC offset")
    if doc.get("state") not in STATES:
        raise _Invalid(f"state must be one of {sorted(STATES)}")
    _str(doc, "summary")
    counts = doc.get("counts", {})
    if not isinstance(counts, dict) or not all(
        isinstance(k, str) and type(v) is int for k, v in counts.items()
    ):
        raise _Invalid("counts must be a flat {label: int} object")
    items = doc.get("items", [])
    if not isinstance(items, list):
        raise _Invalid("items must be a list")
    for item in items:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("label"), str)
            or not set(item) <= _ITEM_KEYS
            or any(not isinstance(item.get(k, ""), str) for k in ("reason", "link"))
            or not isinstance(item.get("needs_owner", False), bool)
        ):
            raise _Invalid("each item needs a string label and only reason/link/needs_owner")
    return doc


def _unreadable(stem: str, why: str) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "name": stem,
        "updated_at": None,
        "state": "failed",
        "summary": f"unreadable status: {why}",
        "counts": {},
        "items": [],
    }


def read_companions(data_dir: Path) -> list[dict[str, Any]]:
    """Every companion document under `data_dir/companions`, sorted by name. No directory, no
    companions: an empty list."""
    folder = data_dir / "companions"
    if not folder.is_dir():
        return []
    out = []
    for path in sorted(folder.glob("*.json")):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
            out.append(_validate(doc, path.stem))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, _Invalid) as exc:
            out.append(_unreadable(path.stem, str(exc)))
    return out
