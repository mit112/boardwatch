# Security Policy

Report vulnerabilities privately via GitHub Security Advisories on this
repository. Do not open public issues for security reports.

## Threat model

boardwatch is local-first. It has no server component, no accounts, and no telemetry.
Its primary store is one SQLite database in your platform data directory; the opt-in
LLM tier also caches raw responses there as plain files on disk. `boardwatch run` also writes
the day's résumé PDFs and reports under `~/boardwatch-applications/` and one folder per lead
under `~/boardwatch-queue/`.

The default path talks only to official, public ATS endpoints and needs no credentials
of any kind.

The review app, `boardwatch web`, refuses to bind anything but a loopback address, and its API
answers only requests that carry its bearer token, kept at mode 0600 in
`{config_dir}/web-token`: what it serves includes your résumé, your answers panel and
third-party job text.

## Secrets

boardwatch's secrets are all opt-in and all read from the environment only: the LLM API key
(`BOARDWATCH_LLM_API_KEY`), the notification webhook URL (`BOARDWATCH_NOTIFY_WEBHOOK_URL`), and
an unattended run's two monitor URLs (`BOARDWATCH_HEARTBEAT_URL`, `BOARDWATCH_ALERT_URL`). None
is ever written to the database, written to your config file, or printed.

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

## What leaves your machine when tailoring a résumé

`boardwatch tailor` is Tier A: local-only, deterministic, and involves no LLM of any kind. It
reads your authored `{config_dir}/resume.yaml` and the JD skills already extracted from a
posting you're watching, does bullet selection and whole-token synonym substitution entirely
in-process, and writes rendered LaTeX source to `{data_dir}/tailored/`, compiled to PDF by a
local `tectonic` binary. No résumé content is sent anywhere; the one network request involved is
tectonic's own, fetching LaTeX packages from its package server the first time it needs them.

## What leaves your machine when Tier B résumé rewording is on

Tier B is a separate, **opt-in** lane on top of `tailor`, off by default. The Tier A path
above never calls out to a model, regardless of Tier B's settings — it is only reached
when `llm.enabled` and `llm.resume_tailoring` are both `true` in `config.toml`,
`BOARDWATCH_LLM_API_KEY` is set, and `boardwatch tailor run` is invoked with `--tier-b`.
When all of that is true, boardwatch sends each candidate bullet's text plus the JD skill
names already extracted from the posting to the configured provider, asking it to reword
the bullet and, separately, to judge whether the reworded bullet is entailed by the
original — that judge call receives only the two bullet texts, never the job description.
Your `profile` text, eligibility facts, and application history are never sent. A reworded
bullet is kept only if it passes a local, deterministic overmatch filter and that
entailment judge; it is not structurally proven the way Tier A's output is, and the plain
Tier A file is always written alongside it for comparison. Responses are cached as plain
files under `{data_dir}/llm-cache/`, same as the eligibility-extraction tier.

## What leaves your machine when the final-eligibility gate is on

The gate is **disabled by default** (`gate.enabled = false`). When you arm it, `boardwatch run`
sends each judged lead's job-description text, together with your eligibility facts (the answers
stored by `boardwatch eligibility facts`, such as work authorization, degree and years of
experience) and fixed judging instructions that name your target seniority band, to the `claude`
CLI on your `PATH`, which sends them to Anthropic under your own Claude account; `gate.claude_config_dir`
chooses which account. Your résumé, your profile text and your application history are not sent.
The gate takes no API key and boardwatch stores no credential for it.

## What leaves your machine for an unattended run's monitors

Both are off unless their variable is set. `BOARDWATCH_HEARTBEAT_URL` receives a plain `GET` with
no body after each clean run. `BOARDWATCH_ALERT_URL` receives a `POST` whose text body is the run
id and its warning lines, the same text the run's morning report shows.

## What leaves your machine when notifications are on

Notifications are disabled by default (`notify.desktop_enabled` and
`notify.webhook_enabled` are both `false`). When `notify.webhook_enabled` is turned on and
`BOARDWATCH_NOTIFY_WEBHOOK_URL` is set, `boardwatch notify` POSTs to that URL only the
public job facts already shown by `top`: title, company, the public posting URL, score,
and a one-token eligibility verdict. It never sends your profile text, résumé, or
eligibility evidence. The webhook URL is read only from the environment; it is never
stored in `config.toml`. Desktop notifications send only a short local summary (best-effort
via the OS's own notifier) and make no network request at all.
