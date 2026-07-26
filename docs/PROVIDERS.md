# AI provider setup

The Public Edition uses direct provider APIs over HTTPS. It contains no AQA proxy and no third-party model gateway. Provider, model, endpoint, and credential settings are configured as named entries on the local **Profile** page. The new-review form accepts only configurations saved there.

## OpenAI

- Endpoint: Responses API `/v1/responses`.
- Structured output: `text.format` with strict JSON Schema.
- Storage request: `store: false`.
- Default profile: `gpt-5.6-sol`; choose another structured-output model when cost, access, or latency makes it more appropriate.
- Credential: entered in the local **Profile** and stored by the operating-system credential manager.

Official references: [Responses API quickstart](https://platform.openai.com/docs/quickstart/make-your-first-api-request), [model catalog](https://developers.openai.com/api/docs/models), and [data controls](https://platform.openai.com/docs/models/default-usage-policies-by-endpoint).

Setting `store: false` is an API request control, not a promise about all provider processing or legal retention. Review your organization and provider data controls.

## Anthropic

- Endpoint: Messages API `/v1/messages`.
- API version header: `2023-06-01`.
- Structured output: `output_config.format` with JSON Schema.
- Default profile: `claude-sonnet-5`.
- Credential: entered in the local **Profile** and stored by the operating-system credential manager.

Official references: [Create a Message](https://platform.claude.com/docs/en/api/messages/create), [structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs), and [API/data retention](https://platform.claude.com/docs/en/manage-claude/api-and-data-retention).

## Google Gemini

- Endpoint: Gemini `generateContent` REST API.
- Structured output: `generationConfig.responseFormat.text` with JSON MIME type and schema.
- Default profile: `gemini-3.5-flash`.
- Credential: entered in the local **Profile** and stored by the operating-system credential manager.

Official references: [generateContent structured outputs](https://ai.google.dev/gemini-api/docs/generate-content/structured-output) and [Generate Content API](https://ai.google.dev/api/generate-content).

Google now documents a newer Interactions API as well. The public adapter deliberately uses the widely available `generateContent` contract and isolates it behind the provider port so a future migration does not change the domain/report layers.

## OpenAI-compatible or local

- Default base URL: `http://127.0.0.1:11434/v1`.
- Endpoint: `{base_url}/chat/completions`.
- Required behavior: OpenAI-compatible messages and strict `json_schema` response format.
- Credential: optionally entered in the local **Profile** when the endpoint requires authentication.

Loopback HTTP is accepted. Non-loopback endpoints must use HTTPS and are labeled a custom destination. URLs may not contain credentials, query strings, or fragments.

Local model quality and context capacity vary substantially. A model must understand the full supplied Context Pack and reliably produce the schema; the app fails honestly instead of silently switching to unstructured JSON.

## Offline demo

The deterministic fake provider makes no AI call. It exercises context, validation, risk scoring, reports, exports, browser flow, and tests. Its analysis is a functional demonstration, not a model-quality example.

## Credentials

API keys entered in Profile are passed directly to the operating-system credential manager through the Python `keyring` abstraction. The current key is never displayed; entering another value replaces it, and the user can remove the key or delete the complete configuration at any time. SQLite stores only the configuration name, provider, model ID, compatible base URL, destination class, default flag, and an opaque profile identifier.

The Profile is the configuration path for cloud and compatible model credentials, keeping model selection, destination disclosure, and credential ownership aligned in one auditable workflow.

Credentials are never included in local assessment state, prompts, transmissions, provider errors, logs, Git URLs, or command arguments. Cloud configurations require a stored key before they can be selected. Compatible endpoints may be configured without a key, and offline demo mode never uses one.
