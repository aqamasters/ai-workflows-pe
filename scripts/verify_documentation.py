from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote

MARKDOWN_LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")


def violations(root: Path) -> list[str]:
    failures: list[str] = []
    markdown_files = [root / "README.md", root / "CONTRIBUTING.md", root / "SECURITY.md"]
    markdown_files.extend((root / "docs").rglob("*.md"))

    for path in markdown_files:
        source = path.read_text(encoding="utf-8")
        for match in MARKDOWN_LINK.finditer(source):
            raw_target = match.group(1).strip().strip("<>")
            if not raw_target or raw_target.startswith(("#", "http://", "https://", "mailto:")):
                continue
            relative_target = unquote(raw_target.split("#", 1)[0])
            target = (path.parent / relative_target).resolve()
            if not target.exists():
                line = source.count("\n", 0, match.start()) + 1
                failures.append(
                    f"{path.relative_to(root)}:{line}: missing local target {raw_target}"
                )
    return failures


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    failures = violations(root)
    if failures:
        print("Documentation verification failed:", file=sys.stderr)
        print("\n".join(f"- {failure}" for failure in failures), file=sys.stderr)
        raise SystemExit(1)
    print("Documentation links verified.")


if __name__ == "__main__":
    main()
