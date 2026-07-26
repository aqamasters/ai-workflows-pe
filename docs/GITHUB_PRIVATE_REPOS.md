# GitHub and private repositories

## Supported URLs

Primary:

```text
https://github.com/OWNER/REPOSITORY/pull/NUMBER
```

Related:

```text
https://github.com/OWNER/REPOSITORY
https://github.com/OWNER/REPOSITORY/pull/NUMBER
```

The parser rejects non-HTTPS URLs, non-`github.com` hosts, embedded credentials, custom ports, query strings, fragments, path traversal, and unsupported URL shapes.

## Fine-grained token permissions

Create a fine-grained personal access token restricted to the explicitly reviewed repositories. Grant:

- Repository contents: read-only.
- Pull requests: read-only.
- Metadata: GitHub includes read-only metadata automatically.

Do not grant write permissions. The app has no code path for comments, checks, labels, issues, commits, branches, merges, or repository settings.

## Credential order

1. Token entered for the current app process.
2. `GITHUB_TOKEN` environment variable.
3. Existing `gh auth token --hostname github.com` session.
4. Optional OS-keychain value.
5. Anonymous access for public repositories.

The UI-entered token is held in memory. Git receives it through `GIT_ASKPASS` and the process environment. It never appears in a remote URL or process arguments.

## Exact commit behavior

The primary PR is pinned to base and head SHAs. Related PRs are pinned to head SHA. Related repository links use an explicit ref when supplied or the repository default branch at preparation time. Before publishing a result, the app asks GitHub for the current primary head and marks the review stale if it moved.

## API and Git limits

GitHub's PR-files REST endpoint exposes at most 3,000 files. Very large repository trees, blobs, diffs, caches, or context budgets fail with an honest local limit message. Public anonymous API quotas are controlled by GitHub; authenticate when the quota is exhausted.

Official references: [Pull request REST endpoints](https://docs.github.com/en/rest/pulls/pulls) and [commit comparison](https://docs.github.com/en/rest/commits/commits).

