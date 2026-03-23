from __future__ import annotations

import importlib.util
import os
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / ".github" / "scripts" / "deploy_github_pages.py"
SPEC = importlib.util.spec_from_file_location("deploy_github_pages", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class DeployGithubPagesTests(unittest.TestCase):
    def test_build_authenticated_remote_url_uses_github_token_auth(self) -> None:
        url = MODULE.build_authenticated_remote_url(
            "https://github.com",
            "fipciu1996/OpenClaw-env-manager",
            "token-123",
        )

        self.assertEqual(
            url,
            "https://x-access-token:token-123@github.com/fipciu1996/OpenClaw-env-manager.git",
        )

    def test_remote_url_prefers_github_actions_environment(self) -> None:
        with patch.dict(
            os.environ,
            {
                "GITHUB_TOKEN": "token-123",
                "GITHUB_REPOSITORY": "fipciu1996/OpenClaw-env-manager",
                "GITHUB_SERVER_URL": "https://github.com",
            },
            clear=False,
        ):
            with patch.object(MODULE, "run_git") as run_git:
                url = MODULE.remote_url()

        self.assertIn("x-access-token:token-123@github.com", url)
        run_git.assert_not_called()

    def test_format_git_failure_redacts_token_and_includes_stderr(self) -> None:
        error = subprocess.CalledProcessError(
            1,
            ["git", "push"],
            output="remote output",
            stderr="fatal: token-123 was rejected",
        )

        with patch.dict(os.environ, {"GITHUB_TOKEN": "token-123"}, clear=False):
            message = MODULE._format_git_failure(
                ["git", "push", "https://x-access-token:token-123@github.com/demo/repo.git"],
                error,
            )

        self.assertIn("Git command failed:", message)
        self.assertIn("stderr:", message)
        self.assertIn("stdout:", message)
        self.assertIn("***", message)
        self.assertNotIn("token-123", message)
