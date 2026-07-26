from pathlib import Path

import aqa_ai_workflows_pe.paths as paths_module
from aqa_ai_workflows_pe.paths import DATA_DIR_ENV, PRODUCT_NAME, AppPaths


def _install_platform_paths(monkeypatch, root: Path) -> None:
    monkeypatch.setattr(
        paths_module,
        "user_data_path",
        lambda name, _author: root / "data" / name,
    )
    monkeypatch.setattr(
        paths_module,
        "user_cache_path",
        lambda name, _author: root / "cache" / name,
    )
    monkeypatch.setattr(
        paths_module,
        "user_log_path",
        lambda name, _author: root / "logs" / name,
    )


def test_new_install_uses_full_product_namespace(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv(DATA_DIR_ENV, raising=False)
    _install_platform_paths(monkeypatch, tmp_path)

    paths = AppPaths.discover()

    assert paths.data == tmp_path / "data" / PRODUCT_NAME
    assert paths.cache == tmp_path / "cache" / PRODUCT_NAME
    assert paths.logs == tmp_path / "logs" / PRODUCT_NAME


def test_data_directory_override_uses_new_environment_name(monkeypatch, tmp_path: Path) -> None:
    override = tmp_path / "isolated-workflow-data"
    monkeypatch.setenv(DATA_DIR_ENV, str(override))

    paths = AppPaths.discover()

    assert paths.data == override.resolve()
    assert paths.cache == override.resolve() / "cache"
    assert paths.logs == override.resolve() / "logs"
