# Frontend system

The browser UI is a local, server-rendered extension of the AQA Masters visual language. It deliberately uses no frontend framework, remote font, CDN asset, analytics script, or build step. This keeps installation small and preserves the product's Content Security Policy and local-only boundary.

## Architecture

| Layer | Location | Responsibility |
|---|---|---|
| Design tokens | `src/aqa_ai_workflows_pe/static/app.css` `:root` | Color, radius, shadow, width, focus, and surface values |
| Primitives | `app.css` typography and primitives | Buttons, cards, labels, pills, alerts, fields, and section headings |
| Patterns | `app.css` screen sections | Hero, review form, local AI profile, disclosure, progress, results, history, comparison, footer |
| Layout | Jinja templates | Semantic document structure and server-rendered data |
| Behavior | `src/aqa_ai_workflows_pe/static/app.js` | AI-profile forms and summaries, progress polling, tabs, deep links, and mobile navigation |
| Brand asset | `src/aqa_ai_workflows_pe/static/aqa-masters-logo.png` | Local official logo; no runtime request to AQA Masters |

Templates extend `base.html`, which owns the skip link, global navigation, page frame, alert region, shell, and footer. Screen templates should contain product-specific structure only.

## Tokens and extension rules

Use the existing custom properties before introducing a literal value. The main groups are:

- `--ink`, `--forest`, `--muted`: text and action hierarchy;
- `--canvas`, `--paper`, `--glass`: surfaces;
- `--mint`, `--lavender`, `--sand`, `--yellow`: semantic supporting surfaces;
- `--line`, `--line-strong`: borders and separators;
- `--radius-*`: shape hierarchy;
- `--shadow-*`: elevation hierarchy;
- `--content`: maximum application width;
- `--focus`: consistent keyboard focus treatment.

When adding a screen:

1. Extend `base.html` and provide a specific document title.
2. Start with an existing `page-header`, `result-hero`, or `progress-card` pattern.
3. Compose existing primitives before adding a page-specific class.
4. Keep server state understandable without JavaScript; JavaScript may enhance, not invent, critical content.
5. Add responsive behavior at the shared 980, 760, or 520 pixel breakpoints only when possible.
6. Test keyboard order, visible focus, narrow layouts, long repository paths, empty collections, failures, and large evidence payloads.

## Responsive behavior

- Above 980px, pages use the full information architecture: split hero, multi-column forms, sidebars, and four-column disclosure summaries.
- Below 980px, high-density layouts become single-column work surfaces while related controls stay grouped.
- Below 760px, the header becomes a button-controlled menu, actions stack, results lose the sidebar, and progress phases use two columns.
- Below 520px, spacing and form indexes contract, repository metadata wraps, and history actions move below their row.

Avoid hiding data merely to fit a viewport. Evidence tables scroll horizontally; long code blocks wrap or scroll within bounded containers.

## Accessibility contract

- The first focusable element is a skip link to `main`.
- Navigation exposes `aria-current` and the mobile control exposes `aria-expanded` and `aria-controls`.
- Result tabs implement `tablist`, `tab`, and `tabpanel` semantics, including arrow, Home, End, and Escape behavior where relevant.
- Form inputs retain visible labels, hints, native validation, and strong focus states.
- Progress uses the native progressbar ARIA contract and updates its value while polling.
- Alerts use an alert role; disclosure remains an explicit form submission.
- Motion respects `prefers-reduced-motion`.
- Meaning is never conveyed by color alone: status surfaces retain text labels.

## Privacy and security constraints

The frontend must continue to satisfy the local runtime boundary:

- no remote CSS, fonts, images, scripts, telemetry, or error reporting;
- no inline scripts because `script-src` is `self`;
- no automatic request to an AQA Masters endpoint;
- the only external AQA link is the explicit Managed Delivery action on the About page;
- credentials must never be reflected into the rendered document after submission;
- destructive actions remain CSRF-protected form posts.

Any new asset must be stored below `src/aqa_ai_workflows_pe/static` so it is included in the wheel by the existing Hatch artifact rule.

## Verification checklist

Before releasing a frontend change:

1. Run the complete Python suite.
2. Run Ruff lint and formatting checks.
3. Build the wheel and verify static assets and templates are present.
4. Exercise new review, disclosure, progress, complete result, history, error, and About routes.
5. Check desktop and narrow viewports with representative long content.
6. Navigate the menu, form, disclosure action, result tabs, citations, and delete action with a keyboard.
7. Confirm the Content Security Policy console remains clean and no unexpected network request appears.
