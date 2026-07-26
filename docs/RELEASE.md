# Release process

## Versioning

Use Semantic Versioning for the Python distribution. Version domain contracts independently through constants in `version.py`:

- method version;
- Context Pack schema;
- canonical report schema;
- risk policy.

Any change that could alter interpretation, citations, scoring, report fields, data disclosure, or privacy behavior must update the relevant version and changelog.

## Release gate

1. Review every dependency version, license, wheel, CVE, and transitive change.
2. Generate and verify the complete exact runtime lock.
3. Run unit, integration, provider-mock, web, security, and architecture tests.
4. Run Ruff, build wheel/sdist, install both into clean environments, and verify package assets.
5. Test one-step launch on current macOS, Windows 11, and Ubuntu LTS with Python 3.12, 3.13, and 3.14 where available.
6. Run `doctor`, first-run bootstrap, warm start, browser failure fallback, and local deletion.
7. Test public and private PR flows with disposable repositories.
8. Verify the exact Context Pack approval and all provider transmission receipts.
9. Search built runtime for credentials, private fixtures, remote assets, AQA endpoints, telemetry SDKs, mutation endpoints, and target execution commands.
10. Review README, security policy, limitations, provider API changes, screenshots/video, and changelog.
11. Create signed tag, checksums, provenance/SBOM, and GitHub release notes.

## Release artifacts

The `dist/` directory is disposable output, not a source of truth. It contains the wheel, source archive, SBOM, checksums, and any other files assembled for a release. Do not commit it. Build from a clean signed tag, verify the artifacts, then upload them to the matching [aqamasters/ai-workflows-pe release](https://github.com/aqamasters/ai-workflows-pe/releases) or package registry. The repository `.gitignore` excludes `dist/` and common package files created outside it.

## Compatibility policy

The runtime supports Python 3.12–3.14 and Git 2.42+. Provider adapters may require updates when an official API becomes unavailable; no silent model/provider migration is allowed. Deprecations must appear in release notes and friendly runtime errors.

## Rollback

Because there is no update service, users choose releases. Keep the prior tagged release and checksums available. Never migrate local state destructively without a backup/export path and an explicit schema migration.
