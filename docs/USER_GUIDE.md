# User guide

## Before you start

Install Python 3.12, 3.13, or 3.14 and Git 2.42 or newer. GitHub CLI is optional and helpful for private repositories. You do not need Node.js, Docker, a database server, a browser automation framework, or an AQA account.

## Start the app

macOS/Linux:

```sh
./start
```

Windows:

```bat
start.cmd
```

The first run downloads pinned Python packages into `.venv`. Later starts reuse it. The terminal prints a high-entropy private URL; keep it private while the app is running.

## Configure your AI profile

Open **Profile** before creating the first review:

1. Give the configuration a recognizable name.
2. Select OpenAI, Anthropic, Google Gemini, a local/OpenAI-compatible endpoint, or offline demo mode.
3. Enter the exact model ID enabled for your provider account.
4. For a compatible provider, enter its loopback HTTP or custom HTTPS base URL.
5. Paste the API key when the provider requires one. The local app sends it directly to the operating-system credential manager; it is never written to SQLite, settings, reports, logs, prompts, or exports.
6. Optionally make the configuration the default for new reviews.

Profile shows whether each model is **Configured** or **Needs API key**, plus its provider, exact model ID, destination class, and credential status. You can edit a configuration, replace or remove its API key, change the default, or delete the configuration and its stored credential.

Cloud configurations without an API key remain visible in Profile but cannot be selected for a new review. Offline demo and unauthenticated compatible endpoints do not require a key.

## Create a review

1. Paste an open GitHub PR URL.
2. Add a short product note when repository text does not explain the customer journey or outcome.
3. Choose one of the models already configured in your local Profile. The form displays its provider, exact model ID, destination, and credential status.
4. Add related repositories only when they can clarify a client, service, event, API, schema, or shared package.
5. For private repositories, prefer an existing `gh auth login` session. Otherwise paste a fine-grained read-only GitHub token.
6. Select **Build local context**.

## Approve the Context Pack

The approval page is the key privacy control. Check:

- the exact provider and model;
- every repository and commit;
- evidence count, selected bytes, and token estimate;
- secret-redaction count;
- evidence paths and why they were selected;
- exclusions and analysis limitations.

Select **Approve and create review** only when this scope is acceptable. The app never sends the full repository by default.

The model can request up to two small, bounded context expansions. The app resolves each request locally, then returns to the approval page. Review the revised evidence list and select **Approve additional context** only if the new scope is acceptable; the app never auto-sends newly selected source.

## Read the result

- **Product brief:** outcome, affected journeys/rules, ranked risks, and decision questions.
- **QA testing:** prioritized scenarios and exploratory charters.
- **Service impact:** possible cross-repository consequences and confidence label.
- **Evidence:** every source citation, exact commit, content, reason, and transmission receipt.

Open evidence IDs such as `E0012` to inspect the exact text supporting a claim. Treat “inferred” service matches and low-evidence risks as prompts for confirmation, not facts.

## Export and delete

Exports include Product Markdown, QA Markdown, standalone HTML, canonical JSON, and a provider transmission manifest. They never contain provider/GitHub credentials or full repository caches.

Delete an assessment from **Local history**. This deletes its Context Pack and reports. Bare repository caches remain for faster future reviews; they are stored under your platform-standard cache directory. Use the path printed by `aqa-ai-workflows repair` if you want to remove caches manually while the app is stopped.

## Troubleshooting

Run:

```sh
PYTHONPATH=src .venv/bin/python -m aqa_ai_workflows_pe.cli doctor
```

Common issues:

- **GitHub anonymous rate limit:** add a fine-grained read-only token.
- **Private repository not found:** grant Contents read and Pull requests read to the selected repository.
- **Provider rejects model:** use a model ID enabled for your account and supporting structured JSON output.
- **Compatible endpoint rejects schema:** enable OpenAI-compatible `json_schema` response format or choose another endpoint/model; the app does not silently downgrade.
- **Configured model is unavailable:** open **Profile** and replace its API key or confirm the exact model ID and endpoint.
- **PR moved:** the report shows a stale warning; create a new review for the latest head.
