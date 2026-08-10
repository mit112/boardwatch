"""The canonical career-profile bundle: a private, revisioned, filesystem-only knowledge source.

Gate A ships the generalized mechanism only. This package is deliberately isolated:

- it never imports `boardwatch.store`, so it adds no SQL schema and no Alembic migration;
- it never imports `boardwatch.tailor`, and nothing in the tailor path imports it, so the
  existing `tailor` commands keep reading `settings.config_dir / "resume.yaml"` untouched;
- it ships its own canonical serializer rather than reusing `eligibility.hashing` or the three
  `_version_of` helpers, because those feed stored identities and `policy_version`, and changing
  their bytes would silently re-key ledger staleness.

The bundle root is resolved at the command boundary as `settings.config_dir / "career-profile"`
and is not a `Settings` field: it is machine-local and does not participate in lead selection.
"""
