from __future__ import annotations

import os
import subprocess

import pytest

from aqa_ai_workflows_pe.adapters.git import GitRunner


def test_git_runner_uses_a_packaged_askpass_helper(settings) -> None:
    runner = GitRunner(settings)

    assert runner.askpass.is_file()
    assert runner.askpass.parent.name == "resources"
    assert runner.askpass.name == ("git-askpass.cmd" if os.name == "nt" else "git-askpass")


@pytest.mark.skipif(os.name == "nt", reason="Windows uses the packaged cmd helper")
def test_packaged_askpass_returns_only_the_scoped_git_token(settings) -> None:
    runner = GitRunner(settings)
    environment = os.environ.copy()
    environment["AQA_GIT_TOKEN"] = "synthetic-github-token"

    username = subprocess.run(
        [str(runner.askpass), "Username for GitHub"],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )
    password = subprocess.run(
        [str(runner.askpass), "Password for GitHub"],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )

    assert username.stdout.strip() == "x-access-token"
    assert password.stdout.strip() == "synthetic-github-token"
