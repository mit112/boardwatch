"""Shipped, non-personal package data for the career-profile bundle.

Holds the generated JSON Schema an authoring agent reads without running the code. A parity test
asserts the committed bytes equal `schema.schema_json()`, and the repository's wheel-content check
asserts the file actually reaches an installed package rather than only the dev checkout.
"""
