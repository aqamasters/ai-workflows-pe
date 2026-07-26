# Security and privacy

## Security posture

AQA AI Workflows Public Edition reads hostile repository and model content. It therefore treats source as data, keeps target code out of Python imports/templates/paths, never executes it, and validates every boundary.

## Local browser controls

- TCP bind is `127.0.0.1` only on a random port by default.
- A 256-bit private launch token establishes an HttpOnly, SameSite=Strict session cookie.
- Host is limited to loopback names to reduce DNS-rebinding risk.
- Unsafe cross-origin requests are blocked by Origin hostname.
- Every form mutation requires a high-entropy CSRF token.
- CSP allows only local scripts/styles/images; there are no remote assets.
- Framing, sniffing, referrer, opener, and cache behavior are restricted.
- FastAPI/OpenAPI developer endpoints and server/date headers are disabled.

Loopback is not a security boundary against malware already running as the same user. Protect the private launch URL and close the process when finished.

## Repository controls

- Bare filtered cache, no working checkout.
- Fixed Git argument arrays, no shell.
- HTTPS GitHub remotes only.
- No hooks, submodules, LFS filters, external diff, textconv, credential helpers, non-HTTPS protocols, or interactive prompts.
- Validated object IDs and repository paths.
- NUL-safe tree parsing.
- Bounded entries, blob/diff bytes, time, evidence, context, and related repositories.
- Secret-like paths excluded; high-confidence key/token/private-key patterns redacted.

Secret scanning is intentionally conservative and cannot guarantee that every secret is detected. Review the Context Pack before approval.

## Provider controls

- Direct calls only to the selected adapter destination.
- Named AI-profile metadata (provider/model/base URL and opaque profile ID) is stored; keys are kept only by the OS credential manager.
- AI provider keys are accepted through the local Profile UI and stored by the OS credential manager.
- Provider keys are loaded only after explicit Context Pack approval, not while repository context is prepared.
- Strict JSON Schema where the provider supports it.
- Unknown citations are removed; unsupported risks cannot enter canonical output.
- No silent provider or model fallback.
- Every model-requested context expansion requires a new exact user approval before transmission.
- Transmission receipt contains hashes and sizes but no key.

## Data at rest

Platform-standard per-user directories hold:

- named AI-model profile metadata, never API keys;
- SQLite assessment state;
- prepared Context Packs;
- selected-evidence reports and exports;
- bare Git object caches;
- local logs designed not to include payloads or credentials.

Local files inherit the user's operating-system account protections. This app does not add application-layer encryption. Use full-disk encryption and appropriate workstation policy for sensitive source.

## Deletion

Deleting an assessment removes its Context Pack and generated reports. Deleting an AI-model configuration removes both its SQLite metadata and its OS-keychain credential; removing only the key leaves the configuration visible as needing attention. Bare repository cache deletion is separate so future reviews can reuse objects. Provider-side deletion/retention is governed by the provider account and terms; this local app cannot perform it.

## No AQA runtime

The project includes a CI script that fails if AQA website endpoints appear in runtime source, except exact, user-clicked Managed Delivery links in rendered templates. There is no analytics, crash reporting, update beacon, license check, or remote support call.

## Reporting vulnerabilities

See the root [SECURITY.md](../SECURITY.md). Do not include real tokens, private source, or sensitive Context Packs in a public issue.
