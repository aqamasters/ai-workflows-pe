# Production readiness

## Supported production shape

AQA AI Workflows Public Edition is a single-user, local desktop-style application. Its production boundary is one loopback-only process owned by one operating-system account. It is not designed to be exposed on a LAN, hosted for multiple users, placed behind a reverse proxy, or operated as a shared service.

## Automated release gates

Every release must pass:

```sh
python -m pytest
python -m ruff check .
python -m ruff format --check .
python scripts/verify_architecture.py
python scripts/verify_no_aqa_endpoint.py
python scripts/verify_documentation.py
python -m pip check
python -m pip_audit -r requirements.lock
python -m build
```

CI runs the test suite and doctor command on macOS, Windows, and Ubuntu across Python 3.12, 3.13, and 3.14. The quality job verifies architecture and runtime boundaries, dependency health, formatting, distributions, installed package assets, and exported schemas.

## Architectural guarantees

- Domain models and deterministic risk policy do not depend on web, storage, Git, provider, or credential frameworks.
- Repository acquisition, context selection, provider calls, persistence, reporting, and delivery remain isolated adapters around the application service.
- AI provider credentials flow only from Profile to the OS credential manager and are resolved only after Context Pack approval.
- Repository content and model output are untrusted data: target code is never imported, templated as trusted markup, checked out, or executed.
- Every provider transmission is bounded, disclosed, approved, and recorded by evidence ID, hash, byte count, destination, model, and commit pin.
- SQLite connections are short-lived, serialized for mutations, integrity-checkable, and stored inside private per-user directories.
- Local artifacts use canonical assessment UUIDs, private directories, and atomic replacement.
- Provider response bodies are bounded; untrusted provider error bodies are not reflected into the UI.

## Manual release evidence

Before publishing a tag, maintainers still verify launch, Profile credential create/update/remove, public and private GitHub access, Context Pack approval, deletion, and a disposable live request against every provider advertised for that release. Cross-platform launcher checks and provider-live checks are operational release evidence and cannot be replaced by mocked CI.

See [Release process](RELEASE.md), [Security and privacy](SECURITY_AND_PRIVACY.md), and [Threat model](THREAT_MODEL.md).
