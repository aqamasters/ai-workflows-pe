from __future__ import annotations

import ast
import sys
from pathlib import Path

DOMAIN_ALLOWED_IMPORTS = set(sys.stdlib_module_names) | {"pydantic"}
APPLICATION_FORBIDDEN_IMPORTS = {
    "fastapi",
    "jinja2",
    "keyring",
    "sqlite3",
    "uvicorn",
}
ADAPTER_FORBIDDEN_IMPORTS = {"fastapi", "jinja2", "uvicorn"}


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imported.add(node.module.split(".", 1)[0])
    return imported


def violations(root: Path) -> list[str]:
    package = root / "src" / "aqa_ai_workflows_pe"
    failures: list[str] = []

    for path in (package / "domain").glob("*.py"):
        unexpected = _imports(path) - DOMAIN_ALLOWED_IMPORTS
        if unexpected:
            failures.append(
                f"{path.relative_to(root)} imports outside the domain boundary: "
                f"{', '.join(sorted(unexpected))}"
            )

    service_imports = _imports(package / "service.py")
    forbidden = service_imports & APPLICATION_FORBIDDEN_IMPORTS
    if forbidden:
        failures.append(
            "src/aqa_ai_workflows_pe/service.py depends on delivery/infrastructure frameworks: "
            + ", ".join(sorted(forbidden))
        )

    for path in (package / "adapters").rglob("*.py"):
        forbidden = _imports(path) & ADAPTER_FORBIDDEN_IMPORTS
        if forbidden:
            failures.append(
                f"{path.relative_to(root)} depends on the web delivery layer: "
                f"{', '.join(sorted(forbidden))}"
            )

    return failures


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    failures = violations(root)
    if failures:
        print("Architecture boundary violations:", file=sys.stderr)
        print("\n".join(f"- {failure}" for failure in failures), file=sys.stderr)
        raise SystemExit(1)
    print("Architecture boundaries verified.")


if __name__ == "__main__":
    main()
