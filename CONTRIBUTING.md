# Contributing

Thank you for improving AQA AI Workflows Public Edition.

## Before opening work

Read [Architecture](docs/ARCHITECTURE.md), [Security and privacy](docs/SECURITY_AND_PRIVACY.md), [Threat model](docs/THREAT_MODEL.md), and [Development](docs/DEVELOPMENT.md). [Open an issue](https://github.com/aqamasters/ai-workflows-pe/issues/new/choose) before large provider, schema, UI-flow, Git safety, or context-selection changes.

## Pull requests

- Keep the Public Edition local, read-only, analysis-only, and independent of AQA runtime services.
- Add tests for changed behavior and security boundaries.
- Update versioned schemas/method docs when semantics change.
- Use synthetic fixtures only; never commit client source, keys, private Context Packs, or provider payloads.
- Run all quality commands in `docs/DEVELOPMENT.md`.
- Explain privacy/network changes explicitly in the PR description.

## Commit and review expectations

Prefer small, reviewable commits. Security-sensitive code—Git commands, credentials, URL parsing, browser middleware, provider payloads, redaction, and evidence validation—requires focused maintainer review.

Contributions are licensed under Apache 2.0. By submitting a contribution, you agree it may be distributed under that license.
