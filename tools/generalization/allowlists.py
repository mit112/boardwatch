"""Reviewed exceptions and the shipped-data inventory.

Every entry carries a reason, so intent is visible in the diff that adds it. Every
table is checked bidirectionally: an unmatched entry is itself a violation, which
stops these tables from rotting into rubber stamps.

Nothing in here may name a person. Identity is matched by SHAPE only. A public repo
shipping a denylist of the maintainer's name, email and handles would be exactly the
disclosure these checks exist to prevent.
"""

from __future__ import annotations

# R1: exact matched text -> reason. Empty today; the tree uses no absolute home paths.
HOME_PATH_EXCEPTIONS: dict[str, str] = {}

# R2: exact email address -> reason. Reserved example domains never need an entry.
EMAIL_EXCEPTIONS: dict[str, str] = {}
