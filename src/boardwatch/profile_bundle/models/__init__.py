"""Strict, immutable typed records for the canonical career-profile bundle.

Split by domain responsibility rather than by file: `base` owns IDs and shared scalars, and each
other module owns one part of the knowledge graph. Nothing here performs cross-record validation —
cardinality, evidence strength, effective state, surfaces, and conflict semantics all need the
whole tree and live under `validation/`.
"""
