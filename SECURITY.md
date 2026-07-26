# Security policy

## Supported versions

The latest tagged major/minor release receives security fixes. Older releases may not.

## Report a vulnerability

Use [GitHub private vulnerability reporting](https://github.com/aqamasters/ai-workflows-pe/security/advisories/new). Do not open a public issue for a vulnerability and do not include real credentials, client source, private PR links, or sensitive Context Packs.

Include:

- affected version and operating system;
- minimal synthetic reproduction;
- impact and required attacker position;
- whether credentials/source left the expected boundary;
- suggested mitigation if known.

Maintainers should acknowledge a complete report within five business days, validate severity, coordinate a fix and advisory, and credit the reporter unless anonymity is requested. This is a best-effort open-source policy, not a service-level agreement.

## Secrets already exposed

Revoke and rotate the credential immediately at GitHub or the AI provider. Deleting a local assessment cannot revoke a key or delete provider-side records.
