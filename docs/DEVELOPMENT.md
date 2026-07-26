# Development

## Setup

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
```

Windows uses `.venv\Scripts\python.exe`.

## Quality commands

```sh
.venv/bin/python -m pytest
.venv/bin/python -m ruff check .
.venv/bin/python -m ruff format --check .
.venv/bin/python scripts/verify_no_aqa_endpoint.py
.venv/bin/python scripts/verify_architecture.py
.venv/bin/python scripts/verify_documentation.py
.venv/bin/python -m build
```

Run the deterministic provider against a disposable public pull request as a manual integration smoke test:

```sh
AQA_AI_WORKFLOWS_DATA_DIR=/tmp/aqa-ai-workflows-smoke PYTHONPATH=src .venv/bin/python scripts/smoke_e2e.py https://github.com/encode/httpx/pull/3783
```

Run the local UI without opening a browser:

```sh
PYTHONPATH=src .venv/bin/python -m aqa_ai_workflows_pe.cli serve --no-browser
```

Use a temporary data directory during development:

```sh
AQA_AI_WORKFLOWS_DATA_DIR=/tmp/aqa-ai-workflows-dev PYTHONPATH=src .venv/bin/python -m aqa_ai_workflows_pe.cli serve
```

## Test layers

- Unit: URLs, redaction, selection, schema normalization, risk policy, challenge pass.
- Integration: synthetic Git repository, context pack, artifacts, SQLite lifecycle.
- Provider contract: mocked official HTTP shapes for all adapters.
- Web: launch session, Host/Origin/CSRF/CSP, form pages, progress and downloads.
- Security: no AQA endpoint, no credential persistence, Git argument safety, path traversal.

Network tests are opt-in and must use dedicated disposable public fixtures and provider accounts. Normal CI never requires a real API key.

## Design rules

- Domain models and risk policy do not import FastAPI, HTTPX, Git, keyring, SQLite, or provider types.
- Target repository content is always untrusted data.
- Outbound destinations must be explicit in an adapter and visible in the disclosure page.
- New provider features must preserve the canonical `ProviderReview` contract.
- New context retrieval must be deterministic, bounded, evidence-addressed, and disclosed.
- Do not add target code execution, GitHub writes, telemetry, AQA runtime calls, arbitrary URL ingestion, or a remote-server mode.
- Schema/method/risk changes require version increments and fixtures.
- Keep AI provider configuration owned by the Profile UI and its secrets in the OS credential manager.

## Dependency locking

The public launcher installs `requirements.lock`. Release maintainers regenerate it in a clean Python 3.12 environment, include all transitive runtime dependencies with exact versions, review licenses and vulnerabilities, test wheels on macOS/Windows/Linux and Python 3.12–3.14, then update the bootstrap fingerprint.

Developer-only tools belong in the `dev` optional dependency group and CI, not the public runtime lock.
