from __future__ import annotations

import ast
import hashlib
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import PurePosixPath

from ..config import Settings
from ..domain.models import (
    ContextPack,
    ContextRequest,
    EvidenceUnit,
    PullRequestMetadata,
    RepositoryManifest,
    RepositoryPin,
    SourceKind,
    utc_now,
)
from ..version import CONTEXT_SCHEMA_VERSION
from .git import BareRepository, TreeEntry

LANGUAGES = {
    ".py": "Python",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".mjs": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".java": "Java",
    ".kt": "Kotlin",
    ".kts": "Kotlin",
    ".cs": "C#",
    ".go": "Go",
    ".rb": "Ruby",
    ".php": "PHP",
    ".rs": "Rust",
    ".sql": "SQL",
    ".proto": "Protocol Buffers",
    ".graphql": "GraphQL",
    ".gql": "GraphQL",
}
TEXT_EXTENSIONS = set(LANGUAGES) | {
    ".md",
    ".txt",
    ".json",
    ".toml",
    ".yaml",
    ".yml",
    ".xml",
    ".ini",
    ".cfg",
    ".conf",
    ".properties",
    ".gradle",
    ".feature",
    ".sh",
}
MANIFEST_NAMES = {
    "pyproject.toml",
    "requirements.txt",
    "poetry.lock",
    "uv.lock",
    "package.json",
    "pnpm-workspace.yaml",
    "pnpm-lock.yaml",
    "yarn.lock",
    "package-lock.json",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "go.mod",
    "cargo.toml",
    "composer.json",
    "gemfile",
    "dockerfile",
}
DENIED_PATH = re.compile(
    r"(^|/)(?:\.[^/]+(?:/.*)?|secrets?(?:/.*|\..*|$)|"
    r"credentials?(?:/.*|\..*|$)|"
    r"id_(?:rsa|ed25519)|.*\.(?:pem|p12|pfx|key|keystore))$",
    re.IGNORECASE,
)
SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----[\s\S]*?-----END [^-]+-----"),
    re.compile(r"\bgh[opusr]_[A-Za-z0-9_]{30,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(
        r"(?im)^([ \t]*(?:api[_-]?key|secret|password|token)[ \t]*[:=][ \t]*)"
        r"([^\s#]{12,})"
    ),
)
TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9_.:/-]{2,80}")


@dataclass(slots=True)
class RepositorySnapshot:
    pin: RepositoryPin
    repository: BareRepository
    tree: list[TreeEntry]
    by_path: dict[str, TreeEntry]


class ContextEngine:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.snapshots: dict[str, RepositorySnapshot] = {}
        self._next_evidence = 1

    def register(self, pin: RepositoryPin, repository: BareRepository) -> None:
        tree = repository.tree(pin.commit_sha)
        self.snapshots[pin.alias] = RepositorySnapshot(
            pin=pin,
            repository=repository,
            tree=tree,
            by_path={entry.path: entry for entry in tree},
        )

    def build(
        self,
        assessment_id: str,
        pull_request: PullRequestMetadata,
        product_notes: str,
    ) -> ContextPack:
        if "primary" not in self.snapshots:
            raise RuntimeError("Primary repository was not registered.")
        tokens = _interest_tokens(pull_request, product_notes)
        evidence: list[EvidenceUnit] = []
        exclusions: list[str] = []
        notes: list[str] = []

        pr_text = (
            f"Title: {pull_request.title}\n"
            f"Author: {pull_request.author}\n"
            f"Draft: {pull_request.draft}\n\n"
            f"Description:\n{pull_request.body or '[No pull-request description]'}\n\n"
            f"User-provided product context:\n{product_notes or '[None provided]'}"
        )
        evidence.append(
            self._unit(
                self.snapshots["primary"].pin,
                SourceKind.PULL_REQUEST,
                ".github/PULL_REQUEST_CONTEXT.md",
                "Pull-request intent and user-provided context",
                pr_text,
            )
        )

        primary = self.snapshots["primary"]
        changed_paths = {item.path for item in pull_request.changed_files}
        for changed in pull_request.changed_files:
            patch = changed.patch
            if not patch:
                entry = primary.by_path.get(changed.path)
                content = primary.repository.read_blob(entry) if entry else ""
                patch = content[:64_000] if content else "[Binary, deleted, or diff unavailable]"
            evidence.append(
                self._unit(
                    primary.pin,
                    SourceKind.PULL_REQUEST,
                    changed.path,
                    f"Changed file ({changed.status}, +{changed.additions}/-{changed.deletions})",
                    patch[:64_000],
                )
            )

        manifests: list[RepositoryManifest] = []
        for alias, snapshot in self.snapshots.items():
            manifest, repo_exclusions = self._manifest(snapshot)
            manifests.append(manifest)
            exclusions.extend(repo_exclusions)
            selected = self._select_paths(
                snapshot,
                tokens=tokens,
                changed_paths=changed_paths if alias == "primary" else set(),
            )
            for path, reason in selected:
                if len(evidence) >= min(self.settings.limits.evidence_units, 240):
                    exclusions.append(
                        "Evidence selection stopped at the public-edition review budget."
                    )
                    break
                entry = snapshot.by_path[path]
                content = snapshot.repository.read_blob(entry)
                if not content:
                    continue
                kind = (
                    SourceKind.PRIMARY_REPOSITORY
                    if alias == "primary"
                    else SourceKind.RELATED_REPOSITORY
                )
                evidence.append(self._unit(snapshot.pin, kind, path, reason, content[:96_000]))
                if alias == "primary" and path in changed_paths:
                    symbols = _python_symbols(path, content)
                    if symbols:
                        notes.append(f"Changed Python symbols in {path}: {', '.join(symbols[:20])}")

        evidence = _deduplicate_evidence(evidence)
        estimated_tokens = sum(len(item.content) for item in evidence) // 4
        while evidence and estimated_tokens > self.settings.limits.provider_input_tokens:
            evidence.pop()
            estimated_tokens = sum(len(item.content) for item in evidence) // 4
        notes.extend(
            [
                "Repository source was inspected from Git objects without checkout or execution.",
                "Python symbols use the standard AST; other languages use lexical/topology fallback in v1.",
                "Candidate relationships are hypotheses until confirmed by cited contracts or product owners.",
            ]
        )
        return ContextPack(
            schema_version=CONTEXT_SCHEMA_VERSION,
            assessment_id=assessment_id,
            created_at=utc_now(),
            pull_request=pull_request,
            repositories=[snapshot.pin for snapshot in self.snapshots.values()],
            manifests=manifests,
            evidence=evidence,
            exclusions=sorted(set(exclusions)),
            context_notes=notes,
            estimated_tokens=estimated_tokens,
        )

    def resolve_requests(self, pack: ContextPack, requests: list[ContextRequest]) -> ContextPack:
        existing_numbers = [
            int(item.id[1:]) for item in pack.evidence if re.fullmatch(r"E\d{4,}", item.id)
        ]
        if existing_numbers:
            self._next_evidence = max(self._next_evidence, max(existing_numbers) + 1)
        existing = {(item.repository_alias, item.path) for item in pack.evidence}
        added: list[EvidenceUnit] = []
        for request in requests:
            snapshot = self.snapshots.get(request.repository_alias)
            if snapshot is None:
                continue
            query_tokens = {token.casefold() for token in TOKEN.findall(request.query)}
            ranked: list[tuple[int, TreeEntry]] = []
            for entry in snapshot.tree:
                if not _eligible(entry) or (snapshot.pin.alias, entry.path) in existing:
                    continue
                path_tokens = set(TOKEN.findall(entry.path.casefold()))
                score = sum(6 for token in query_tokens if token in entry.path.casefold())
                score += len(query_tokens & path_tokens) * 3
                if request.kind == "test" and _is_test(entry.path):
                    score += 5
                if request.kind == "contract" and _is_contract(entry.path):
                    score += 5
                if request.kind == "documentation" and _is_documentation(entry.path):
                    score += 5
                if score:
                    ranked.append((score, entry))
            ranked.sort(key=lambda item: (-item[0], item[1].path))
            for _, entry in ranked[: request.max_results]:
                content = snapshot.repository.read_blob(entry)
                if not content:
                    continue
                kind = (
                    SourceKind.PRIMARY_REPOSITORY
                    if snapshot.pin.alias == "primary"
                    else SourceKind.RELATED_REPOSITORY
                )
                added.append(
                    self._unit(
                        snapshot.pin,
                        kind,
                        entry.path,
                        f"Model context request: {request.reason}",
                        content[:96_000],
                    )
                )
        merged = _deduplicate_evidence([*pack.evidence, *added])
        estimated_tokens = sum(len(item.content) for item in merged) // 4
        if estimated_tokens > self.settings.limits.provider_input_tokens:
            merged = pack.evidence
            estimated_tokens = pack.estimated_tokens
        return pack.model_copy(update={"evidence": merged, "estimated_tokens": estimated_tokens})

    def _manifest(self, snapshot: RepositorySnapshot) -> tuple[RepositoryManifest, list[str]]:
        extensions: Counter[str] = Counter()
        manifests: list[str] = []
        tests: list[str] = []
        contracts: list[str] = []
        docs: list[str] = []
        excluded = 0
        exclusions: list[str] = []
        for entry in snapshot.tree:
            if _denied(entry.path):
                excluded += 1
                continue
            suffix = PurePosixPath(entry.path).suffix.casefold()
            if suffix in LANGUAGES:
                extensions[LANGUAGES[suffix]] += 1
            if PurePosixPath(entry.path).name.casefold() in MANIFEST_NAMES:
                manifests.append(entry.path)
            if _is_test(entry.path):
                tests.append(entry.path)
            if _is_contract(entry.path):
                contracts.append(entry.path)
            if _is_documentation(entry.path):
                docs.append(entry.path)
        frameworks = _frameworks(manifests)
        parser_coverage = {
            language: "AST + lexical" if language == "Python" else "lexical/topology"
            for language in extensions
        }
        if excluded:
            exclusions.append(
                f"{snapshot.pin.alias}: excluded {excluded} secret-like or unsupported paths."
            )
        return (
            RepositoryManifest(
                repository_alias=snapshot.pin.alias,
                commit_sha=snapshot.pin.commit_sha,
                languages=[name for name, _ in extensions.most_common()],
                frameworks=frameworks,
                manifests=manifests[:80],
                test_paths=tests[:250],
                contract_paths=contracts[:250],
                documentation_paths=docs[:120],
                entry_count=len(snapshot.tree),
                excluded_count=excluded,
                parser_coverage=parser_coverage,
                notes=[
                    "Manifest is deterministic for the pinned commit.",
                    "Unsupported languages remain available through path and lexical evidence only.",
                ],
            ),
            exclusions,
        )

    def _select_paths(
        self,
        snapshot: RepositorySnapshot,
        *,
        tokens: set[str],
        changed_paths: set[str],
    ) -> list[tuple[str, str]]:
        ranked: dict[str, tuple[int, str]] = {}
        changed_stems = {PurePosixPath(path).stem.casefold() for path in changed_paths}
        for entry in snapshot.tree:
            if not _eligible(entry):
                continue
            path = entry.path
            lower = path.casefold()
            name = PurePosixPath(path).name.casefold()
            score = 0
            reasons: list[str] = []
            if path in changed_paths:
                score += 100
                reasons.append("Full content of a changed file")
            if name in MANIFEST_NAMES:
                score += 45
                reasons.append("Build/dependency manifest")
            if _is_contract(path):
                score += 28
                reasons.append("Contract, schema, event, or migration candidate")
            if _is_test(path):
                score += 20
                reasons.append("Related test convention or coverage candidate")
                if any(stem in lower for stem in changed_stems if len(stem) > 2):
                    score += 25
            if _is_documentation(path):
                score += 12
                reasons.append("Product or architecture documentation")
            matched = [token for token in tokens if token in lower]
            if matched:
                score += min(30, len(matched) * 5)
                reasons.append("Path matches change terminology")
            if score:
                ranked[path] = (score, "; ".join(reasons))
        limit = 100 if snapshot.pin.alias == "primary" else 65
        selected = sorted(ranked.items(), key=lambda item: (-item[1][0], item[0]))[:limit]
        return [(path, reason) for path, (_, reason) in selected]

    def _unit(
        self,
        pin: RepositoryPin,
        kind: SourceKind,
        path: str,
        reason: str,
        content: str,
    ) -> EvidenceUnit:
        redacted, count = _redact(content)
        evidence_id = f"E{self._next_evidence:04d}"
        self._next_evidence += 1
        line_count = max(1, redacted.count("\n") + 1)
        return EvidenceUnit(
            id=evidence_id,
            source_kind=kind,
            repository_alias=pin.alias,
            repository_slug=pin.slug,
            commit_sha=pin.commit_sha,
            path=path,
            start_line=1,
            end_line=line_count,
            reason=reason,
            content=redacted,
            sha256=hashlib.sha256(redacted.encode()).hexdigest(),
            redactions=count,
        )


def _interest_tokens(pull_request: PullRequestMetadata, notes: str) -> set[str]:
    raw = " ".join(
        [
            pull_request.title,
            pull_request.body,
            notes,
            *[item.path for item in pull_request.changed_files],
        ]
    )
    stop = {
        "this",
        "that",
        "with",
        "from",
        "into",
        "change",
        "changes",
        "update",
        "updated",
        "file",
        "files",
        "src",
        "test",
        "tests",
    }
    return {
        token.casefold().strip("./:-_")
        for token in TOKEN.findall(raw)
        if len(token.strip("./:-_")) >= 4 and token.casefold() not in stop
    }


def _eligible(entry: TreeEntry) -> bool:
    if entry.kind != "blob" or entry.size < 0 or entry.size > 512 * 1024:
        return False
    if _denied(entry.path):
        return False
    suffix = PurePosixPath(entry.path).suffix.casefold()
    name = PurePosixPath(entry.path).name.casefold()
    return suffix in TEXT_EXTENSIONS or name in MANIFEST_NAMES or name.startswith("readme")


def _denied(path: str) -> bool:
    return bool(DENIED_PATH.search(path.casefold()))


def _is_test(path: str) -> bool:
    lower = f"/{path.casefold()}"
    name = PurePosixPath(path).name.casefold()
    return any(part in lower for part in ("/test/", "/tests/", "/spec/", "/specs/")) or any(
        marker in name for marker in (".test.", ".spec.", "_test.", "test_")
    )


def _is_contract(path: str) -> bool:
    lower = path.casefold()
    return any(
        marker in lower
        for marker in (
            "openapi",
            "swagger",
            "schema",
            "contract",
            "migration",
            "graphql",
            ".proto",
            "events",
            "messages",
            "feature_flag",
        )
    )


def _is_documentation(path: str) -> bool:
    lower = path.casefold()
    name = PurePosixPath(path).name.casefold()
    return (
        lower.startswith("docs/")
        or "/docs/" in lower
        or name.startswith("readme")
        or name.startswith("adr-")
        or name in {"architecture.md", "contributing.md", "codeowners"}
    )


def _frameworks(manifests: list[str]) -> list[str]:
    joined = " ".join(manifests).casefold()
    mapping = {
        "package.json": "Node.js ecosystem",
        "pyproject.toml": "Python project",
        "pom.xml": "Maven/JVM",
        "build.gradle": "Gradle/JVM",
        "go.mod": "Go modules",
        "cargo.toml": "Rust/Cargo",
        "composer.json": "PHP/Composer",
        "gemfile": "Ruby/Bundler",
        "dockerfile": "Containerized runtime",
    }
    return [label for marker, label in mapping.items() if marker in joined]


def _python_symbols(path: str, content: str) -> list[str]:
    if PurePosixPath(path).suffix.casefold() != ".py":
        return []
    try:
        tree = ast.parse(content)
    except (SyntaxError, ValueError):
        return []
    return [
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    ]


def _redact(content: str) -> tuple[str, int]:
    result = content
    count = 0
    for pattern in SECRET_PATTERNS:
        if pattern.groups:
            result, substitutions = pattern.subn(r"\1[REDACTED]", result)
        else:
            result, substitutions = pattern.subn("[REDACTED]", result)
        count += substitutions
    return result, count


def _deduplicate_evidence(evidence: list[EvidenceUnit]) -> list[EvidenceUnit]:
    seen: set[tuple[str, str, str]] = set()
    result: list[EvidenceUnit] = []
    for item in evidence:
        key = (item.repository_alias, item.path, item.sha256)
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result
