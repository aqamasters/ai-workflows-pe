from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field

KEYRING_SERVICE = "aqa-ai-workflows-pe"


@dataclass(slots=True)
class GitHubCredentialCache:
    _values: dict[str, str] = field(default_factory=dict, repr=False)

    def set(self, name: str, value: str) -> None:
        if value:
            self._values[name] = value

    def get(self, name: str) -> str:
        return self._values.get(name, "")

    def clear(self) -> None:
        self._values.clear()


def profile_credential_name(profile_id: str) -> str:
    return f"ai-profile:{profile_id}"


def persist_profile_key(profile_id: str, value: str) -> None:
    if not value:
        return
    _keyring_set(profile_credential_name(profile_id), value)


def resolve_profile_key(profile_id: str) -> str:
    return _keyring_get(profile_credential_name(profile_id))


def profile_key_is_configured(profile_id: str) -> bool:
    return bool(resolve_profile_key(profile_id))


def credential_manager_status() -> tuple[bool, str]:
    try:
        import keyring

        backend = keyring.get_keyring()
        priority = float(getattr(backend, "priority", 0))
        name = f"{backend.__class__.__module__}.{backend.__class__.__name__}"
        return priority > 0, name
    except Exception as exc:
        return False, f"unavailable ({type(exc).__name__})"


def delete_profile_key(profile_id: str) -> None:
    name = profile_credential_name(profile_id)
    try:
        import keyring

        if keyring.get_password(KEYRING_SERVICE, name) is None:
            return
        keyring.delete_password(KEYRING_SERVICE, name)
    except Exception as exc:
        try:
            from keyring.errors import PasswordDeleteError

            if isinstance(exc, PasswordDeleteError):
                return
        except ImportError:
            pass
        raise RuntimeError(
            "The OS credential manager could not delete this API key. Unlock it and try again."
        ) from exc


def resolve_github_token(session_value: str, session: GitHubCredentialCache) -> tuple[str, str]:
    if session_value:
        session.set("github", session_value)
        return session_value, "session"
    if session.get("github"):
        return session.get("github"), "session"
    if os.getenv("GITHUB_TOKEN"):
        return os.environ["GITHUB_TOKEN"], "environment"
    try:
        result = subprocess.run(
            ["gh", "auth", "token", "--hostname", "github.com"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip(), "github_cli"
    except (FileNotFoundError, subprocess.SubprocessError):
        pass
    value = _keyring_get("github")
    return (value, "keyring") if value else ("", "anonymous")


def _keyring_get(name: str) -> str:
    try:
        import keyring

        return keyring.get_password(KEYRING_SERVICE, name) or ""
    except Exception:
        return ""


def _keyring_set(name: str, value: str) -> None:
    try:
        import keyring

        keyring.set_password(KEYRING_SERVICE, name, value)
    except Exception as exc:
        raise RuntimeError(
            "The OS credential manager could not save this API key. Unlock it and try again."
        ) from exc
