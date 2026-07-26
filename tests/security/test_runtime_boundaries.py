from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ALLOWED_AQA_CLICKTHROUGHS = {
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


def test_runtime_has_no_automatic_aqa_endpoint() -> None:
    violations = []
    for path in (ROOT / "src").rglob("*"):
        if not path.is_file() or path.suffix not in {".py", ".js", ".css", ".html"}:
            continue
        source = path.read_text(encoding="utf-8", errors="ignore")
        for allowed_href in ALLOWED_AQA_CLICKTHROUGHS.get(path.relative_to(ROOT), ()):
            source = source.replace(allowed_href, "")
        if "https://aqamasters.com" in source:
            violations.append(path)
    assert violations == []


def test_no_target_execution_commands_in_git_adapter() -> None:
    source = (ROOT / "src/aqa_ai_workflows_pe/adapters/git.py").read_text(encoding="utf-8")
    for command in ("checkout", "submodule", "lfs pull", "npm", "pytest", "docker"):
        assert f'"{command}"' not in source


def test_no_github_mutation_methods() -> None:
    source = (ROOT / "src/aqa_ai_workflows_pe/adapters/github.py").read_text(encoding="utf-8")
    assert "client.post" not in source
    assert "client.patch" not in source
    assert "client.delete" not in source
