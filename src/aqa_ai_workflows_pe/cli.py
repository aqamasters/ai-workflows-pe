from __future__ import annotations

import argparse
import json
import logging
import shutil
import socket
import sys
import threading
import time
import webbrowser
from contextlib import suppress
from pathlib import Path

import uvicorn

from .adapters.ai.schema import provider_review_schema
from .adapters.credentials import credential_manager_status
from .adapters.persistence import AssessmentStore
from .config import Settings
from .domain.models import CanonicalReview, ContextPack
from .version import __version__
from .web import WebState, create_app


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aqa-ai-workflows",
        description="AQA AI Workflows Public Edition for evidence-backed Product and QA analysis.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)
    serve = subcommands.add_parser("serve", help="start the loopback browser application")
    serve.add_argument("--port", type=int, default=0, help="loopback port; 0 chooses a free port")
    serve.add_argument("--no-browser", action="store_true", help="print the URL without opening it")
    subcommands.add_parser("doctor", help="check local prerequisites and storage")
    subcommands.add_parser("repair", help="check local SQLite integrity and recreate directories")
    subcommands.add_parser("version", help="print the installed version")
    schemas = subcommands.add_parser("export-schemas", help="write public JSON schemas")
    schemas.add_argument("directory", nargs="?", default="schemas")
    return parser


def main(argv: list[str] | None = None) -> None:
    arguments = build_parser().parse_args(argv)
    if arguments.command == "serve":
        serve(arguments.port, arguments.no_browser)
    elif arguments.command == "doctor":
        raise SystemExit(doctor())
    elif arguments.command == "repair":
        raise SystemExit(repair())
    elif arguments.command == "version":
        print(__version__)
    elif arguments.command == "export-schemas":
        export_schemas(Path(arguments.directory))


def serve(port: int, no_browser: bool) -> None:
    settings = Settings.load()
    settings.paths.ensure()
    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    state = WebState(settings)
    app = create_app(settings, state)
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", port))
    listener.listen(2048)
    selected_port = int(listener.getsockname()[1])
    url = f"http://127.0.0.1:{selected_port}/?launch={state.launch_secret}"
    print("\nAQA AI Workflows Public Edition is running only on this machine.")
    print(f"Open: {url}\n")
    if not no_browser:
        threading.Thread(target=_open_browser, args=(url,), daemon=True).start()
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=selected_port,
        log_level=settings.log_level.casefold(),
        access_log=False,
        server_header=False,
        date_header=False,
    )
    server = uvicorn.Server(config)
    with suppress(KeyboardInterrupt):
        server.run(sockets=[listener])


def _open_browser(url: str) -> None:
    time.sleep(0.7)
    webbrowser.open(url, new=2)


def doctor() -> int:
    settings = Settings.load()
    checks: list[tuple[str, bool, str]] = []
    checks.append(
        (
            "Python",
            (3, 12) <= sys.version_info[:2] < (3, 15),
            sys.version.split()[0],
        )
    )
    git = shutil.which("git")
    checks.append(("Git", bool(git), git or "not found"))
    checks.append(("GitHub CLI", bool(shutil.which("gh")), shutil.which("gh") or "optional"))
    credential_manager_ready, credential_manager = credential_manager_status()
    checks.append(
        (
            "Credential store",
            credential_manager_ready,
            credential_manager
            if credential_manager_ready
            else f"{credential_manager}; offline only",
        )
    )
    try:
        settings.paths.ensure()
        test_path = settings.paths.data / ".write-test"
        test_path.write_text("ok", encoding="utf-8")
        test_path.unlink()
        checks.append(("Local storage", True, str(settings.paths.data)))
    except OSError as exc:
        checks.append(("Local storage", False, str(exc)))
    try:
        store = AssessmentStore(settings.paths.database)
        integrity = store.integrity_check()
        checks.append(("SQLite", integrity == "ok", integrity))
    except Exception as exc:
        checks.append(("SQLite", False, str(exc)))
    try:
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.bind(("127.0.0.1", 0))
        listener.close()
        checks.append(("Loopback", True, "127.0.0.1 available"))
    except OSError as exc:
        checks.append(("Loopback", False, str(exc)))
    print("AQA AI Workflows Public Edition doctor\n")
    for name, passed, detail in checks:
        print(f"{'PASS' if passed else 'FAIL':4}  {name:14} {detail}")
    print("\nOutbound destinations are GitHub plus only the AI provider you select.")
    optional = {"GitHub CLI", "Credential store"}
    return 0 if all(item[1] for item in checks if item[0] not in optional) else 1


def repair() -> int:
    settings = Settings.load()
    settings.paths.ensure()
    integrity = AssessmentStore(settings.paths.database).integrity_check()
    print(f"SQLite integrity: {integrity}")
    print(f"Local data: {settings.paths.data}")
    print(f"Repository cache: {settings.paths.repositories}")
    return 0 if integrity == "ok" else 1


def export_schemas(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    schemas = {
        "provider-review.schema.json": provider_review_schema(),
        "context-pack.schema.json": ContextPack.model_json_schema(),
        "canonical-review.schema.json": CanonicalReview.model_json_schema(),
    }
    for name, schema in schemas.items():
        (directory / name).write_text(
            json.dumps(schema, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(f"Wrote {len(schemas)} schemas to {directory.resolve()}")


if __name__ == "__main__":
    main()
