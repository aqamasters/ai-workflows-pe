# Threat model

## Assets

- GitHub and AI provider credentials.
- Private repository source and metadata.
- Product/business notes entered by the user.
- Context Packs, reports, and local history.
- Integrity of evidence citations and risk ranking.

## Adversaries and failure sources

1. Malicious or compromised repository content.
2. Prompt injection embedded in code, docs, filenames, PR descriptions, or generated source.
3. Malicious model output or provider error content.
4. Another website targeting the local server through CSRF, rebinding, or browser embedding.
5. Local malware or another process running as the same operating-system user.
6. Accidental credential leakage through URLs, process lists, logs, reports, exceptions, or exports.
7. Excessive repository/model input causing disk, memory, time, token, or cost exhaustion.
8. Stale PR data or invented citations causing false confidence.

## Controls by threat

| Threat | Primary controls | Residual risk |
|---|---|---|
| Target code execution | Bare/no-checkout Git; object reads; hooks/filters/submodules disabled; no build/test commands | Native Git vulnerabilities; keep Git patched |
| Prompt injection | System boundary says repository is untrusted; no model tools; request schema cannot express commands/URLs; citations validated | Model may still misinterpret evidence |
| Browser attack | Loopback bind, private launch session, Host/Origin/CSRF/CSP/frame controls, no CORS | Same-user local malware can access loopback and process memory |
| Credential leak | AI keys isolated in the OS credential manager, GitHub askpass env, sanitization, no payload logs | OS keychain/process security depends on workstation |
| Data over-sharing | Deterministic bounded selection, denied paths, redaction, exact preflight approval, receipts | Secret scanning and relevance selection are not perfect |
| Resource exhaustion | Tree/blob/diff/evidence/token/round/related-repo/time bounds | Large but allowed inputs may still be slow/costly |
| Hallucination | Structured contracts, evidence IDs, citation filtering, local risk policy, analysis-only language | Cited evidence does not guarantee correct interpretation |
| Staleness | Exact base/head pins and head recheck before result | External state after report generation can still change |
| AQA data collection | No automatic AQA request, telemetry, license/update service; exact click-through links are statically allowlisted | User may explicitly open a Managed Delivery website link |

## Out of scope

- A workstation already compromised at the OS/admin level.
- Security guarantees of GitHub, the selected provider, Git, Python, the browser, OS keyring, or installed dependencies.
- Provider legal/compliance suitability for the user's source.
- Malicious modifications made after the user publishes a fork of this project.
- Multi-user or remote-hosted deployment; this architecture must not be exposed beyond loopback.

## Security review checklist

- Fuzz strict URL parsing and path/object validation.
- Assert Git tokens are absent from args, stderr, database, artifacts, and logs.
- Assert no target execution or GitHub mutation verbs appear in runtime Git/API adapters.
- Test host, session, Origin, CSRF, CSP, and traversal rejection.
- Test prompt injection fixtures and unknown evidence IDs.
- Run dependency vulnerability, license, secret, and static scans before release.
- Verify the no-AQA-runtime script.
