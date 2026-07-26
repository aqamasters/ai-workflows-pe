from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import venv
from pathlib import Path

MIN_VERSION = (3, 12)
MAX_VERSION = (3, 15)


def _venv_python(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def _fingerprint(root: Path) -> str:
    digest = hashlib.sha256()
    for name in ("requirements.lock", "pyproject.toml"):
        digest.update((root / name).read_bytes())
    return digest.hexdigest()


def bootstrap(root: Path, *, print_only: bool = False) -> Path:
    if not (MIN_VERSION <= sys.version_info[:2] < MAX_VERSION):
        raise SystemExit(
            f"Python 3.12–3.14 is required; found {sys.version.split()[0]}. "
            "Install it from https://www.python.org/downloads/."
        )

    venv_dir = root / ".venv"
    python = _venv_python(venv_dir)
    if not python.exists():
        if print_only:
            raise SystemExit("The local environment is not ready. Run start first.")
        print("Creating an isolated local environment…", file=sys.stderr)
        venv.EnvBuilder(with_pip=True, clear=False).create(venv_dir)

    marker = venv_dir / ".aqa-requirements.sha256"
    expected = _fingerprint(root)
    current = marker.read_text(encoding="utf-8").strip() if marker.exists() else ""
    if current != expected and not print_only:
        print("Installing pinned Python dependencies…", file=sys.stderr)
        subprocess.run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "-r",
                str(root / "requirements.lock"),
            ],
            check=True,
        )
        marker.write_text(expected + "\n", encoding="utf-8")
    return python


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("usage: bootstrap.py PROJECT_ROOT [--print-python]")
    root = Path(sys.argv[1]).resolve()
    print_only = "--print-python" in sys.argv[2:]
    python = bootstrap(root, print_only=print_only)
    if print_only:
        print(python)


if __name__ == "__main__":
    main()
