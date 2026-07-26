# Limitations

## The application does not prove behavior

It does not run code, tests, browsers, APIs, databases, containers, build tools, dependency managers, deployment systems, or production telemetry. Findings are hypotheses and test design direction.

## Repository understanding is bounded

The app selects relevant evidence under fixed size and token budgets. It can miss dynamic dispatch, reflection, generated code, runtime configuration, secrets-managed values, remote feature flags, infrastructure state, undocumented consumers, or business context outside the registered repositories.

Python changed symbols use the standard AST. Other languages use paths, manifests, tests, contracts, identifiers, and lexical/topology fallback in v1. Reports expose parser coverage and exclusions.

## GitHub scope

The primary source must be an open `github.com` pull request. GitHub Enterprise Server, GitLab, Bitbucket, arbitrary patches, local-only branches, and closed/merged PRs are outside v1. Related sources are limited to three explicitly supplied GitHub repositories or open PRs.

## AI limitations

Structured output makes data parseable, not necessarily correct. Models can misinterpret code or business meaning. The app filters unknown citations and unsupported duplicates but cannot validate semantic truth without humans or product execution.

Provider availability, model IDs, pricing, retention, regional processing, and account eligibility are controlled by the provider and may change. Review provider terms before sending sensitive source.

## Scale limits

Default limits include 100,000 tree entries per repository, 512 KB per blob, 8 MB diff, 1,500 theoretical evidence units (the normal public review selects at most 240), about 200,000 provider input tokens, and two additional user-approved context rounds.

## No managed support guarantee

This open-source Public Edition is provided as-is under Apache 2.0. AQA Managed Delivery is a separate professional service with a different operating and responsibility model.
