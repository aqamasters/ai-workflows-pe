# Changelog

All notable changes follow Keep a Changelog and Semantic Versioning.

## 1.2.0 - 2026-07-20

### Changed

- Renamed the product, Python distribution and import package, CLI, runtime identifiers, schemas, documentation paths, and showcase asset to AQA AI Workflows Public Edition.
- Local data, cache, log, session-cookie, and OS-keyring entries use only the AQA AI Workflows Public Edition namespaces.
- Updated Gemini structured-output requests to the current `responseFormat` contract.

## 1.1.0 - 2026-07-19

### Added

- Local Profile page for named AI-model configurations, default selection, secure API-key replacement/removal, and configuration deletion.
- Full-width website-aligned frontend system and an end-to-end workflow demonstration.
- Automated architecture-boundary verification, browser security/profile integration tests, credential rollback tests, and production-readiness documentation.

### Changed

- New reviews can select only models configured in Profile; provider, model, endpoint, and credential fields are no longer accepted from the assessment form.
- Prepared legacy assessments can resolve credentials from an exact matching configured profile during approval without changing their provider, model, or endpoint.
- AI provider credentials are resolved from Profile entries backed by the operating-system credential manager.
- Provider keys are resolved only after Context Pack approval, provider responses are size-bounded, and untrusted provider error bodies are no longer reflected into the UI.
- Background work is owned by assessment ID and cancelled before deletion or application shutdown.
- Local directories, SQLite state, and assessment artifacts use stricter permissions and lifecycle validation.

### Fixed

- First launch keeps dependency-installation output separate from the machine-readable virtual-environment Python path.
- Provider responses request identity encoding and tolerate safely bounded, mislabelled gzip/deflate bodies instead of failing during automatic decompression.

## 1.0.0 - 2026-07-18

### Added

- Local-only browser application and CLI for GitHub pull-request review.
- Bounded primary and related-repository context with exact commit pins.
- Direct OpenAI, Anthropic, Google Gemini, and OpenAI-compatible adapters.
- Deterministic fake provider for the included demo and offline verification.
- Evidence-backed Product, QA, service-impact, and provenance reports.
- Session, GitHub CLI, and optional OS-keyring credentials.
- Loopback, host, session, CSRF, CSP, secret-redaction, and no-execution controls.
- Exact user approval before the initial AI call and every model-requested context expansion.
