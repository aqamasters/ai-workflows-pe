from __future__ import annotations

import asyncio
import logging
import secrets
from collections.abc import Coroutine
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape

from .adapters.artifacts import ArtifactStore
from .adapters.credentials import (
    GitHubCredentialCache,
    delete_profile_key,
    persist_profile_key,
    profile_key_is_configured,
    resolve_github_token,
    resolve_profile_key,
)
from .adapters.persistence import AssessmentStore
from .config import Settings
from .domain.errors import AQAReviewError, InputError
from .domain.models import (
    AIModelProfile,
    AssessmentStatus,
    ProviderConfig,
    ProviderName,
    RelatedSourceInput,
    ReviewRequest,
    utc_now,
)
from .service import AnalysisSecrets, AnalysisService
from .version import __version__

LOGGER = logging.getLogger(__name__)
PACKAGE_ROOT = Path(__file__).resolve().parent
SAFE_DOWNLOADS = {
    "product-report.md",
    "qa-report.md",
    "review.html",
    "canonical-review.json",
    "transmission-manifest.json",
}
PROVIDER_LABELS = {
    ProviderName.OPENAI: "OpenAI",
    ProviderName.ANTHROPIC: "Anthropic",
    ProviderName.GOOGLE: "Google Gemini",
    ProviderName.COMPATIBLE: "OpenAI-compatible",
    ProviderName.FAKE: "Offline demo",
}
PROFILE_NOTICES = {
    "created": "AI model configured and ready to use.",
    "updated": "AI model configuration updated.",
    "default": "Default AI model updated.",
    "credential_removed": "API key removed from the OS credential manager.",
    "deleted": "AI model configuration and its stored API key were deleted.",
}


class WebState:
    def __init__(self, settings: Settings) -> None:
        settings.paths.ensure()
        self.settings = settings
        self.store = AssessmentStore(settings.paths.database)
        self.artifacts = ArtifactStore(settings.paths.artifacts)
        self.service = AnalysisService(settings, self.store, self.artifacts)
        self.github_credentials = GitHubCredentialCache()
        self.launch_secret = secrets.token_urlsafe(32)
        self.csrf_token = secrets.token_urlsafe(32)
        self.jobs: dict[str, asyncio.Task[Any]] = {}

    def start_job(self, assessment_id: str, coroutine: Coroutine[Any, Any, Any]) -> None:
        current = self.jobs.get(assessment_id)
        if current and not current.done():
            coroutine.close()
            raise RuntimeError("This assessment already has a running local task.")
        task = asyncio.create_task(coroutine)
        self.jobs[assessment_id] = task

        def discard(completed: asyncio.Task[Any]) -> None:
            if self.jobs.get(assessment_id) is completed:
                self.jobs.pop(assessment_id, None)

        task.add_done_callback(discard)

    async def cancel_job(self, assessment_id: str) -> None:
        task = self.jobs.pop(assessment_id, None)
        if not task or task.done():
            return
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    async def close(self) -> None:
        for assessment_id in list(self.jobs):
            await self.cancel_job(assessment_id)


def create_app(settings: Settings | None = None, state: WebState | None = None) -> FastAPI:
    settings = settings or Settings.load()
    state = state or WebState(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        try:
            yield
        finally:
            await state.close()

    templates = Environment(
        loader=FileSystemLoader(PACKAGE_ROOT / "templates"),
        autoescape=select_autoescape(("html", "xml")),
        enable_async=False,
    )
    app = FastAPI(
        title="AQA AI Workflows Public Edition",
        version=__version__,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.state.aqa = state
    app.state.templates = templates
    app.mount("/static", StaticFiles(directory=PACKAGE_ROOT / "static"), name="static")

    @app.middleware("http")
    async def local_security(request: Request, call_next: Any) -> Any:
        host = request.headers.get("host", "").split(":", 1)[0].strip("[]").casefold()
        if host not in {"127.0.0.1", "localhost", "::1", "testserver"}:
            return HTMLResponse("Invalid local host header.", status_code=400)
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            if origin and origin != "null":
                parsed = urlsplit(origin)
                if parsed.hostname not in {"127.0.0.1", "localhost", "::1", "testserver"}:
                    return HTMLResponse("Cross-origin request blocked.", status_code=403)
        launch = request.query_params.get("launch")
        authenticated = secrets.compare_digest(
            request.cookies.get("aqa_ai_workflows_session", ""), state.launch_secret
        )
        if launch and secrets.compare_digest(launch, state.launch_secret):
            response = RedirectResponse(request.url.replace(query=""), status_code=303)
            response.set_cookie(
                "aqa_ai_workflows_session",
                state.launch_secret,
                httponly=True,
                secure=False,
                samesite="strict",
                max_age=8 * 60 * 60,
            )
            return _secure(response)
        if request.url.path != "/healthz" and not authenticated:
            return _secure(
                HTMLResponse("Open the private URL printed by the launcher.", status_code=401)
            )
        return _secure(await call_next(request))

    @app.get("/healthz")
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.get("/", response_class=HTMLResponse)
    async def home(request: Request) -> HTMLResponse:
        return render(
            request,
            "home.html",
            assessments=state.store.list(5),
            ai_profile_views=_configured_ai_profile_views(state),
            provider_labels=PROVIDER_LABELS,
        )

    @app.get("/profile", response_class=HTMLResponse)
    async def profile(request: Request) -> HTMLResponse:
        notice = PROFILE_NOTICES.get(str(request.query_params.get("notice") or ""), "")
        return render_profile(request, notice=notice)

    @app.post("/profile/ai-models")
    async def create_ai_profile(request: Request) -> Response:
        form = await request.form()
        profile_id = str(uuid4())
        try:
            _check_csrf(form, state.csrf_token)
            configured, api_key = _ai_profile_from_form(profile_id, form)
            if api_key:
                persist_profile_key(profile_id, api_key)
            try:
                state.store.create_ai_profile(configured)
            except Exception:
                if api_key:
                    _restore_profile_key(profile_id, "")
                raise
            return RedirectResponse("/profile?notice=created", status_code=303)
        except Exception as exc:
            return render_profile(
                request,
                status_code=400,
                error=_safe_error(exc),
                profile_form=_safe_profile_form(form),
            )

    @app.post("/profile/ai-models/{profile_id}")
    async def update_ai_profile(request: Request, profile_id: str) -> Response:
        form = await request.form()
        try:
            _check_csrf(form, state.csrf_token)
            existing = state.store.get_ai_profile(profile_id)
            if not existing:
                raise InputError("That AI model configuration no longer exists.")
            configured, api_key = _ai_profile_from_form(profile_id, form, existing)
            previous_key = resolve_profile_key(profile_id)
            credential_changed = bool(api_key) or configured.provider == ProviderName.FAKE
            if api_key:
                persist_profile_key(profile_id, api_key)
            elif configured.provider == ProviderName.FAKE:
                delete_profile_key(profile_id)
            try:
                if not state.store.update_ai_profile(configured):
                    raise InputError("That AI model configuration no longer exists.")
            except Exception:
                if credential_changed:
                    _restore_profile_key(profile_id, previous_key)
                raise
            return RedirectResponse("/profile?notice=updated", status_code=303)
        except Exception as exc:
            return render_profile(request, status_code=400, error=_safe_error(exc))

    @app.post("/profile/ai-models/{profile_id}/default")
    async def set_default_ai_profile(request: Request, profile_id: str) -> Response:
        form = await request.form()
        try:
            _check_csrf(form, state.csrf_token)
            configured = state.store.get_ai_profile(profile_id)
            if not configured or not _ai_profile_is_configured(configured):
                raise InputError("Configure the API key before making this model the default.")
            if not state.store.set_default_ai_profile(profile_id):
                raise InputError("That AI model configuration no longer exists.")
            return RedirectResponse("/profile?notice=default", status_code=303)
        except Exception as exc:
            return render_profile(request, status_code=400, error=_safe_error(exc))

    @app.post("/profile/ai-models/{profile_id}/credential/delete")
    async def remove_ai_profile_credential(request: Request, profile_id: str) -> Response:
        form = await request.form()
        try:
            _check_csrf(form, state.csrf_token)
            configured = state.store.get_ai_profile(profile_id)
            if not configured:
                raise InputError("That AI model configuration no longer exists.")
            previous_key = resolve_profile_key(profile_id)
            delete_profile_key(profile_id)
            try:
                if configured.provider == ProviderName.COMPATIBLE:
                    configured = configured.model_copy(update={"credential_source": "none"})
                    if not state.store.update_ai_profile(configured):
                        raise InputError("That AI model configuration no longer exists.")
            except Exception:
                _restore_profile_key(profile_id, previous_key)
                raise
            return RedirectResponse("/profile?notice=credential_removed", status_code=303)
        except Exception as exc:
            return render_profile(request, status_code=400, error=_safe_error(exc))

    @app.post("/profile/ai-models/{profile_id}/delete")
    async def delete_ai_profile(request: Request, profile_id: str) -> Response:
        form = await request.form()
        try:
            _check_csrf(form, state.csrf_token)
            if not state.store.get_ai_profile(profile_id):
                raise InputError("That AI model configuration no longer exists.")
            previous_key = resolve_profile_key(profile_id)
            delete_profile_key(profile_id)
            try:
                if not state.store.delete_ai_profile(profile_id):
                    raise InputError("That AI model configuration no longer exists.")
            except Exception:
                _restore_profile_key(profile_id, previous_key)
                raise
            return RedirectResponse("/profile?notice=deleted", status_code=303)
        except Exception as exc:
            return render_profile(request, status_code=400, error=_safe_error(exc))

    @app.post("/assessments")
    async def create_assessment(request: Request) -> Response:
        form = await request.form()
        try:
            _check_csrf(form, state.csrf_token)
            ai_profile_id = str(form.get("ai_profile_id") or "").strip()
            ai_profile = state.store.get_ai_profile(ai_profile_id)
            if not ai_profile or not _ai_profile_is_configured(ai_profile):
                raise InputError("Choose an AI model configured in your local Profile.")
            provider_config = ai_profile.provider_config()
            github_token, _ = resolve_github_token(
                str(form.get("github_token") or "").strip(), state.github_credentials
            )
            related = []
            for index in range(1, 4):
                url = str(form.get(f"related_url_{index}") or "").strip()
                if not url:
                    continue
                related.append(
                    RelatedSourceInput.model_validate(
                        {
                            "url": url,
                            "label": str(
                                form.get(f"related_label_{index}") or f"Related service {index}"
                            ),
                            "relationship": str(
                                form.get(f"related_relationship_{index}") or "Related service"
                            ),
                            "ref": str(form.get(f"related_ref_{index}") or ""),
                        }
                    )
                )
            review_request = ReviewRequest.model_validate(
                {
                    "pull_request_url": str(form.get("pull_request_url") or "").strip(),
                    "related_sources": related,
                    "provider": provider_config,
                    "product_notes": str(form.get("product_notes") or "").strip(),
                }
            )
            summary = state.service.create(review_request)
            state.start_job(
                summary.id,
                _run_prepare(state, summary.id, AnalysisSecrets(github_token=github_token)),
            )
            return RedirectResponse(f"/assessments/{summary.id}/progress", status_code=303)
        except Exception as exc:
            return render(
                request,
                "home.html",
                status_code=400,
                error=_safe_error(exc),
                assessments=state.store.list(5),
                ai_profile_views=_configured_ai_profile_views(state),
                provider_labels=PROVIDER_LABELS,
                form=dict(form),
            )

    @app.get("/assessments/{assessment_id}/progress", response_class=HTMLResponse)
    async def progress(request: Request, assessment_id: str) -> HTMLResponse:
        summary = state.store.get(assessment_id)
        if not summary:
            return render(request, "error.html", status_code=404, error="Assessment not found.")
        return render(request, "progress.html", assessment=summary)

    @app.get("/api/assessments/{assessment_id}")
    async def assessment_status(assessment_id: str) -> JSONResponse:
        summary = state.store.get(assessment_id)
        if not summary:
            return JSONResponse({"error": "not found"}, status_code=404)
        next_url = ""
        if summary.status == AssessmentStatus.READY:
            next_url = f"/assessments/{assessment_id}/disclosure"
        elif summary.status == AssessmentStatus.COMPLETE:
            next_url = f"/assessments/{assessment_id}"
        return JSONResponse(
            {
                "id": summary.id,
                "status": summary.status.value,
                "progress": summary.progress,
                "message": summary.message,
                "error": summary.error,
                "next_url": next_url,
            }
        )

    @app.get("/assessments/{assessment_id}/disclosure", response_class=HTMLResponse)
    async def disclosure(request: Request, assessment_id: str) -> Response:
        summary = state.store.get(assessment_id)
        if not summary:
            return render(request, "error.html", status_code=404, error="Assessment not found.")
        if summary.status != AssessmentStatus.READY:
            return RedirectResponse(f"/assessments/{assessment_id}/progress", status_code=303)
        pack = state.artifacts.read_context(assessment_id)
        review_state = state.artifacts.read_review_state(assessment_id)
        previously_sent_ids = {
            evidence_id
            for transmission in (review_state.transmissions if review_state else [])
            for evidence_id in transmission.evidence_ids
        }
        approval_profile_views = _configured_ai_profile_views(state)
        return render(
            request,
            "disclosure.html",
            assessment=summary,
            pack=pack,
            content_bytes=sum(len(item.content.encode()) for item in pack.evidence),
            redactions=sum(item.redactions for item in pack.evidence),
            review_state=review_state,
            new_evidence=sum(item.id not in previously_sent_ids for item in pack.evidence),
            approval_profile_views=approval_profile_views,
            selected_ai_profile_id=_selected_ai_profile_id(
                summary.request.provider, approval_profile_views
            ),
        )

    @app.post("/assessments/{assessment_id}/confirm")
    async def confirm(request: Request, assessment_id: str) -> Response:
        form = await request.form()
        try:
            _check_csrf(form, state.csrf_token)
            summary = state.store.get(assessment_id)
            if not summary or summary.status != AssessmentStatus.READY:
                raise InputError("This assessment is not ready to send to the selected model.")
            ai_profile_id = str(form.get("ai_profile_id") or "").strip()
            ai_profile = state.store.get_ai_profile(ai_profile_id)
            if not ai_profile or not _ai_profile_is_configured(ai_profile):
                raise InputError("Choose an AI model configured in your local Profile.")
            provider_config = ai_profile.provider_config()
            provider_key = resolve_profile_key(ai_profile.id)
            if _provider_requires_key(provider_config.provider) and not provider_key:
                raise InputError("Add an API key to the selected model in your local Profile.")
            updated_request = summary.request.model_copy(update={"provider": provider_config})
            if not state.store.update_request(assessment_id, updated_request):
                raise InputError("This assessment is no longer waiting at the approval gate.")
            github_token, _ = resolve_github_token(
                str(form.get("github_token") or "").strip(), state.github_credentials
            )
            state.start_job(
                assessment_id,
                _run_review(
                    state,
                    assessment_id,
                    AnalysisSecrets(github_token=github_token, provider_key=provider_key),
                ),
            )
            return RedirectResponse(f"/assessments/{assessment_id}/progress", status_code=303)
        except Exception as exc:
            assessment = state.store.get(assessment_id)
            if not assessment:
                return render(request, "error.html", status_code=404, error="Assessment not found.")
            pack = state.artifacts.read_context(assessment_id)
            review_state = state.artifacts.read_review_state(assessment_id)
            previously_sent_ids = {
                evidence_id
                for transmission in (review_state.transmissions if review_state else [])
                for evidence_id in transmission.evidence_ids
            }
            approval_profile_views = _configured_ai_profile_views(state)
            return render(
                request,
                "disclosure.html",
                status_code=400,
                error=_safe_error(exc),
                assessment=assessment,
                pack=pack,
                content_bytes=sum(len(item.content.encode()) for item in pack.evidence),
                redactions=sum(item.redactions for item in pack.evidence),
                review_state=review_state,
                new_evidence=sum(item.id not in previously_sent_ids for item in pack.evidence),
                approval_profile_views=approval_profile_views,
                selected_ai_profile_id=(
                    str(form.get("ai_profile_id") or "").strip()
                    or _selected_ai_profile_id(assessment.request.provider, approval_profile_views)
                ),
            )

    @app.get("/assessments/{assessment_id}", response_class=HTMLResponse)
    async def result(request: Request, assessment_id: str) -> Response:
        summary = state.store.get(assessment_id)
        if not summary:
            return render(request, "error.html", status_code=404, error="Assessment not found.")
        if summary.status != AssessmentStatus.COMPLETE or not summary.result:
            return RedirectResponse(f"/assessments/{assessment_id}/progress", status_code=303)
        evidence = {item.id: item for item in summary.result.evidence}
        return render(request, "result.html", assessment=summary, evidence=evidence)

    @app.get("/assessments/{assessment_id}/downloads/{filename}")
    async def download(assessment_id: str, filename: str) -> FileResponse:
        if filename not in SAFE_DOWNLOADS:
            raise InputError("That export is not available.")
        path = state.artifacts.assessment_dir(assessment_id, create=False) / filename
        if not path.is_file():
            raise InputError("That export has not been generated.")
        return FileResponse(path, filename=filename, media_type="application/octet-stream")

    @app.post("/assessments/{assessment_id}/delete")
    async def delete(request: Request, assessment_id: str) -> RedirectResponse:
        form = await request.form()
        _check_csrf(form, state.csrf_token)
        await state.cancel_job(assessment_id)
        state.service.delete(assessment_id)
        return RedirectResponse("/history", status_code=303)

    @app.get("/history", response_class=HTMLResponse)
    async def history(request: Request) -> HTMLResponse:
        return render(request, "history.html", assessments=state.store.list(100))

    @app.get("/about", response_class=HTMLResponse)
    async def about(request: Request) -> HTMLResponse:
        return render(request, "about.html")

    def render_profile(
        request: Request,
        *,
        status_code: int = 200,
        error: str = "",
        notice: str = "",
        profile_form: dict[str, str] | None = None,
    ) -> HTMLResponse:
        return render(
            request,
            "profile.html",
            status_code=status_code,
            error=error,
            notice=notice,
            profile_views=_ai_profile_views(state),
            provider_labels=PROVIDER_LABELS,
            profile_form=profile_form or {},
        )

    def render(
        request: Request,
        template_name: str,
        *,
        status_code: int = 200,
        **context: Any,
    ) -> HTMLResponse:
        template = templates.get_template(template_name)
        content = template.render(
            request=request,
            csrf_token=state.csrf_token,
            version=__version__,
            **context,
        )
        return HTMLResponse(content, status_code=status_code)

    return app


async def _run_prepare(state: WebState, assessment_id: str, secrets_: AnalysisSecrets) -> None:
    try:
        await state.service.prepare(assessment_id, secrets_)
    except Exception as exc:
        LOGGER.error("Assessment preparation failed: %s (%s)", assessment_id, type(exc).__name__)


async def _run_review(state: WebState, assessment_id: str, secrets_: AnalysisSecrets) -> None:
    try:
        await state.service.review(assessment_id, secrets_)
    except Exception as exc:
        LOGGER.error("Assessment review failed: %s (%s)", assessment_id, type(exc).__name__)


def _restore_profile_key(profile_id: str, previous_key: str) -> None:
    try:
        if previous_key:
            persist_profile_key(profile_id, previous_key)
        else:
            delete_profile_key(profile_id)
    except RuntimeError:
        LOGGER.error("Could not restore OS credential state for AI profile %s", profile_id)


def _secure(response: Any) -> Any:
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
        "connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'none'; "
        "frame-ancestors 'none'; form-action 'self'"
    )
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    response.headers["Cache-Control"] = "no-store"
    return response


def _check_csrf(form: Any, expected: str) -> None:
    supplied = str(form.get("csrf_token") or "")
    if not secrets.compare_digest(supplied, expected):
        raise InputError("The local form expired. Refresh the page and try again.")


def _ai_profile_from_form(
    profile_id: str,
    form: Any,
    existing: AIModelProfile | None = None,
) -> tuple[AIModelProfile, str]:
    provider = ProviderName(str(form.get("provider") or ""))
    model = str(form.get("model") or "").strip()
    label = str(form.get("label") or "").strip()
    api_key = str(form.get("api_key") or "").strip()
    base_url = str(form.get("base_url") or "").strip()
    if not label:
        raise InputError("Enter a name for this AI model configuration.")
    if not model:
        raise InputError("Enter the model ID available in your provider account.")
    if provider == ProviderName.COMPATIBLE:
        base_url = _validate_compatible_profile_url(base_url)
    else:
        base_url = ""
    existing_has_key = bool(existing and profile_key_is_configured(profile_id))
    if provider == ProviderName.FAKE:
        credential_source = "none"
        api_key = ""
    elif provider == ProviderName.COMPATIBLE:
        credential_source = "keyring" if api_key or existing_has_key else "none"
    else:
        credential_source = "keyring"
        if not api_key and not existing_has_key:
            raise InputError("Enter an API key for this cloud AI model.")
    now = utc_now()
    configured = AIModelProfile.model_validate(
        {
            "id": profile_id,
            "label": label,
            "provider": provider,
            "model": model,
            "base_url": base_url,
            "credential_source": credential_source,
            "destination_class": _destination_class(provider, base_url),
            "is_default": existing.is_default if existing else bool(form.get("is_default")),
            "created_at": existing.created_at if existing else now,
            "updated_at": now,
        }
    )
    return configured, api_key


def _validate_compatible_profile_url(value: str) -> str:
    url = value.strip().rstrip("/") or "http://127.0.0.1:11434/v1"
    parsed = urlsplit(url)
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise InputError(
            "Compatible endpoint URLs cannot contain credentials, queries, or fragments."
        )
    if not parsed.hostname:
        raise InputError("Enter a valid OpenAI-compatible base URL ending in /v1.")
    if parsed.hostname in {"127.0.0.1", "localhost", "::1"}:
        if parsed.scheme != "http":
            raise InputError("Local compatible endpoints must use loopback HTTP.")
    elif parsed.scheme != "https":
        raise InputError("Non-local compatible endpoints must use HTTPS.")
    return url


def _provider_requires_key(provider: ProviderName) -> bool:
    return provider not in {ProviderName.FAKE, ProviderName.COMPATIBLE}


def _ai_profile_is_configured(profile: AIModelProfile) -> bool:
    if not _provider_requires_key(profile.provider):
        return True
    return profile.credential_source == "keyring" and profile_key_is_configured(profile.id)


def _ai_profile_views(state: WebState) -> list[dict[str, Any]]:
    views = []
    for profile in state.store.list_ai_profiles():
        has_key = profile_key_is_configured(profile.id)
        configured = not _provider_requires_key(profile.provider) or has_key
        if profile.provider == ProviderName.FAKE:
            credential_label = "No API key · runs locally"
        elif has_key:
            credential_label = "API key stored in OS credential manager"
        elif profile.provider == ProviderName.COMPATIBLE:
            credential_label = "No API key · endpoint must allow unauthenticated access"
        else:
            credential_label = "API key required"
        views.append(
            {
                "profile": profile,
                "configured": configured,
                "has_key": has_key,
                "credential_label": credential_label,
                "provider_label": PROVIDER_LABELS[profile.provider],
            }
        )
    return views


def _configured_ai_profile_views(state: WebState) -> list[dict[str, Any]]:
    return [view for view in _ai_profile_views(state) if bool(view["configured"])]


def _selected_ai_profile_id(
    provider_config: ProviderConfig,
    profile_views: list[dict[str, Any]],
) -> str:
    profiles = [view["profile"] for view in profile_views]
    if any(profile.id == provider_config.profile_id for profile in profiles):
        return provider_config.profile_id
    matching = [
        profile
        for profile in profiles
        if _ai_profile_matches_provider_config(profile, provider_config)
    ]
    if matching:
        default_match = next((profile for profile in matching if profile.is_default), None)
        return (default_match or matching[0]).id
    default_profile = next((profile for profile in profiles if profile.is_default), None)
    return (default_profile or profiles[0]).id if profiles else ""


def _ai_profile_matches_provider_config(
    profile: AIModelProfile,
    provider_config: ProviderConfig,
) -> bool:
    if profile.provider != provider_config.provider or profile.model != provider_config.model:
        return False
    if profile.provider != ProviderName.COMPATIBLE:
        return True
    profile_url = profile.base_url.rstrip("/") or "http://127.0.0.1:11434/v1"
    assessment_url = provider_config.base_url.rstrip("/") or "http://127.0.0.1:11434/v1"
    return profile_url == assessment_url


def _safe_profile_form(form: Any) -> dict[str, str]:
    return {name: str(form.get(name) or "") for name in ("label", "provider", "model", "base_url")}


def _destination_class(provider: ProviderName, base_url: str) -> str:
    if provider == ProviderName.COMPATIBLE:
        host = urlsplit(base_url or "http://127.0.0.1:11434/v1").hostname
        return "local" if host in {"127.0.0.1", "localhost", "::1"} else "custom"
    if provider == ProviderName.FAKE:
        return "local"
    return "cloud"


def _safe_error(exc: Exception) -> str:
    if isinstance(exc, (AQAReviewError, ValueError, RuntimeError)):
        return str(exc)[:2_000]
    return "The local application could not complete that request. Check the fields and try again."
