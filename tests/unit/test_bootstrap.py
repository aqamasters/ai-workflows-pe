from __future__ import annotations

import sys
from pathlib import Path

from scripts import bootstrap as bootstrap_module


def test_bootstrap_path_is_printed_only_for_machine_readable_mode(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    python = tmp_path / ".venv" / "bin" / "python"
    calls: list[bool] = []

    def fake_bootstrap(root: Path, *, print_only: bool = False) -> Path:
        assert root == tmp_path
        calls.append(print_only)
        return python

    monkeypatch.setattr(bootstrap_module, "bootstrap", fake_bootstrap)
    monkeypatch.setattr(sys, "argv", ["bootstrap.py", str(tmp_path)])

    bootstrap_module.main()

    assert capsys.readouterr().out == ""

    monkeypatch.setattr(
        sys,
        "argv",
        ["bootstrap.py", str(tmp_path), "--print-python"],
    )

    bootstrap_module.main()

    assert capsys.readouterr().out == f"{python}\n"
    assert calls == [False, True]
