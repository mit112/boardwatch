# Security Policy

Report vulnerabilities privately via GitHub Security Advisories on this
repository. Do not open public issues for security reports.

## Threat model

boardwatch is local-first. It has no server component, no accounts, and no telemetry.
Its primary store is one SQLite database in your platform data directory; the opt-in
LLM tier also caches raw responses there as plain files on disk.

The default path talks only to official, public ATS endpoints and needs no credentials
of any kind.

## Secrets

boardwatch has exactly one secret, and only if you opt in to it.

The LLM eligibility-extraction tier is **disabled by default**. The deterministic
eligibility engine is the default path and never contacts a model. When you enable the
LLM tier, boardwatch reads `BOARDWATCH_LLM_API_KEY` **from the environment only**. It is
never written to the database, never written to your config file, and never printed.

## What leaves your machine when the LLM tier is on

Only the job description text, which is the public body of a posting you are already
watching. Your profile, your eligibility facts, and your application history are never
sent to the model provider. Once the tier is enabled and `BOARDWATCH_LLM_API_KEY` is set,
`boardwatch eligibility extract --dry-run` previews the job description text and
destination for every open posting before any request is made.
