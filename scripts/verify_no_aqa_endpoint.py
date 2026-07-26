from __future__ import annotations

import re
import sys
from pathlib import Path

RUNTIME_SUFFIXES = {".py", ".js", ".css", ".html"}
FORBIDDEN = re.compile(r"https?://(?:www\.)?aqamasters\.com", re.IGNORECASE)
ALLOWED_CLICKTHROUGHS = {
    Path("src/aqa_ai_workflows_pe/templates/base.html"): (
        'href="https://aqamasters.com/solutions/ai-qa-enablement"',
    ),
    Path("src/aqa_ai_workflows_pe/templates/about.html"): (
        'href="https://aqamasters.com/solutions/ai-qa-enablement"',
    ),
    Path("src/aqa_ai_workflows_pe/templates/managed_cta.jinja"): (
        'href="https://aqamasters.com/how-we-engage/14-day-qa-pilot"',
    ),
}


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    failures: list[str] = []
    for path in (root / "src").rglob("*"):
        if not path.is_file() or path.suffix not in RUNTIME_SUFFIXES:
            continue
        relative = path.relative_to(root)
        source = path.read_text(encoding="utf-8", errors="ignore")
        for approved_href in ALLOWED_CLICKTHROUGHS.get(relative, ()):
            source = source.replace(approved_href, "")
        if FORBIDDEN.search(source):
            failures.append(str(relative))
    if failures:
        print("Forbidden AQA runtime endpoint references:", file=sys.stderr)
        print("\n".join(failures), file=sys.stderr)
        raise SystemExit(1)
    print("No AQA runtime endpoint references found.")


if __name__ == "__main__":
    main()
