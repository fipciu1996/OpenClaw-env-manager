from __future__ import annotations

import io
import itertools
import shutil
import unittest
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from openenv.cli import main
from openenv.core.errors import CommandError
from openenv.manifests.loader import load_manifest
from openenv.manifests.lockfile import build_lockfile, write_lockfile


TESTS_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = TESTS_ROOT / "fixtures"
TEMP_ROOT = TESTS_ROOT / "_tmp"
TEMP_ROOT.mkdir(exist_ok=True)
_COUNTER = itertools.count()


@contextmanager
def workspace_dir() -> Path:
    path = TEMP_ROOT / f"case-{next(_COUNTER)}"
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


class CliTests(unittest.TestCase):
    def test_init_refuses_to_overwrite_existing_manifest_without_force(self) -> None:
        with workspace_dir() as temp_dir:
            manifest_path = temp_dir / "openclawenv.toml"
            manifest_path.write_text("already here", encoding="utf-8")

            stderr = io.StringIO()
            with redirect_stderr(stderr):
                exit_code = main(["init", "--path", str(manifest_path)])

            self.assertEqual(exit_code, 1)
            self.assertIn("Refusing to overwrite existing file", stderr.getvalue())

    def test_init_creates_manifest(self) -> None:
        with workspace_dir() as temp_dir:
            manifest_path = temp_dir / "openclawenv.toml"

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = main(["init", "--path", str(manifest_path)])

            self.assertEqual(exit_code, 0)
            self.assertTrue(manifest_path.exists())
            manifest_text = manifest_path.read_text(encoding="utf-8")
            self.assertIn('system_packages = ["git", "curl", "chromium"]', manifest_text)
            self.assertIn('node_packages = ["typescript@5.8.3"]', manifest_text)
            self.assertIn('source = "deus-context-engine"', manifest_text)
            self.assertIn('source = "self-improving-agent"', manifest_text)
            self.assertIn('source = "skill-security-review"', manifest_text)
            self.assertIn('source = "freeride"', manifest_text)
            self.assertIn('source = "agent-browser-clawdbot"', manifest_text)

    def test_export_writes_dockerfile(self) -> None:
        with workspace_dir() as temp_dir:
            manifest_path = temp_dir / "openclawenv.toml"
            lock_path = temp_dir / "openclawenv.lock"
            output_path = temp_dir / "Dockerfile"
            shutil.copyfile(FIXTURES / "example.openclawenv.toml", manifest_path)
            shutil.copyfile(FIXTURES / "example.openclawenv.lock", lock_path)

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "export",
                        "dockerfile",
                        "--path",
                        str(manifest_path),
                        "--lock",
                        str(lock_path),
                        "--output",
                        str(output_path),
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertTrue(output_path.exists())

    def test_scan_invokes_skill_scanner(self) -> None:
        with workspace_dir() as temp_dir:
            manifest_path = temp_dir / "openclawenv.toml"
            shutil.copyfile(FIXTURES / "example.openclawenv.toml", manifest_path)

            with patch("openenv.cli.run_skill_scanner") as run_skill_scanner:
                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    exit_code = main(
                        [
                            "scan",
                            "--path",
                            str(manifest_path),
                            "--",
                            "--policy",
                            "strict",
                        ]
                    )

            self.assertEqual(exit_code, 0)
            run_skill_scanner.assert_called_once()
            self.assertEqual(run_skill_scanner.call_args.kwargs["scanner_args"], ["--", "--policy", "strict"])

    def test_export_compose_writes_default_bot_file(self) -> None:
        with workspace_dir() as temp_dir:
            manifest_path = temp_dir / "openclawenv.toml"
            lock_path = temp_dir / "openclawenv.lock"
            dockerfile_path = temp_dir / "Dockerfile"
            compose_path = temp_dir / "docker-compose-operations-agent.yml"
            env_path = temp_dir / ".operations-agent.env"
            shutil.copyfile(FIXTURES / "example.openclawenv.toml", manifest_path)
            shutil.copyfile(FIXTURES / "example.openclawenv.lock", lock_path)

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "export",
                        "compose",
                        "--path",
                        str(manifest_path),
                        "--lock",
                        str(lock_path),
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertTrue(dockerfile_path.exists())
            self.assertTrue(compose_path.exists())
            self.assertTrue(env_path.exists())
            compose_text = compose_path.read_text(encoding="utf-8")
            self.assertIn("openclaw-gateway:", compose_text)
            self.assertIn("openclaw-cli:", compose_text)
            self.assertIn('dockerfile: "Dockerfile"', compose_text)
            expected_env = (FIXTURES / "example.bot.env").read_text(encoding="utf-8")
            self.assertEqual(env_path.read_text(encoding="utf-8"), expected_env)

    def test_export_to_stdout_emits_raw_dockerfile(self) -> None:
        with workspace_dir() as temp_dir:
            manifest_path = temp_dir / "openclawenv.toml"
            lock_path = temp_dir / "openclawenv.lock"
            shutil.copyfile(FIXTURES / "example.openclawenv.toml", manifest_path)
            shutil.copyfile(FIXTURES / "example.openclawenv.lock", lock_path)

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "export",
                        "dockerfile",
                        "--path",
                        str(manifest_path),
                        "--lock",
                        str(lock_path),
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertTrue(stdout.getvalue().startswith("# syntax=docker/dockerfile:1"))

    def test_lock_writes_lockfile(self) -> None:
        with workspace_dir() as temp_dir:
            manifest_path = temp_dir / "openclawenv.toml"
            lock_path = temp_dir / "generated.lock"
            shutil.copyfile(FIXTURES / "example.openclawenv.toml", manifest_path)

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    ["lock", "--path", str(manifest_path), "--output", str(lock_path)]
                )

            self.assertEqual(exit_code, 0)
            self.assertTrue(lock_path.exists())
            self.assertIn('"lock_version": 1', lock_path.read_text(encoding="utf-8"))

    def test_build_uses_default_tag(self) -> None:
        with workspace_dir() as temp_dir:
            manifest_path = temp_dir / "openclawenv.toml"
            lock_path = temp_dir / "openclawenv.lock"
            dockerfile_path = temp_dir / "Dockerfile"
            compose_path = temp_dir / "docker-compose-operations-agent.yml"
            env_path = temp_dir / ".operations-agent.env"
            shutil.copyfile(FIXTURES / "example.openclawenv.toml", manifest_path)
            shutil.copyfile(FIXTURES / "example.openclawenv.lock", lock_path)

            with patch("openenv.cli.build_image_with_args") as build_image:
                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    exit_code = main(
                        [
                            "build",
                            "--path",
                            str(manifest_path),
                            "--lock",
                            str(lock_path),
                        ]
                    )

            self.assertEqual(exit_code, 0)
            build_image.assert_called_once()
            _, tag = build_image.call_args.args
            self.assertEqual(tag, "openclawenv/ops-agent:1.2.3")
            self.assertEqual(
                build_image.call_args.kwargs["build_args"],
                {
                    "OPENCLAWENV_SKILL_SCAN_FAIL_ON_SEVERITY": "high",
                    "OPENCLAWENV_SKILL_SCAN_FORMAT": "summary",
                    "OPENCLAWENV_SKILL_SCAN_POLICY": "balanced",
                },
            )
            self.assertTrue(dockerfile_path.exists())
            self.assertTrue(compose_path.exists())
            self.assertTrue(env_path.exists())
            expected = (FIXTURES / "example.compose.yml").read_text(encoding="utf-8")
            self.assertEqual(compose_path.read_text(encoding="utf-8"), expected)
            expected_env = (FIXTURES / "example.bot.env").read_text(encoding="utf-8")
            self.assertEqual(env_path.read_text(encoding="utf-8"), expected_env)

    def test_build_passes_custom_skill_scan_settings(self) -> None:
        with workspace_dir() as temp_dir:
            manifest_path = temp_dir / "openclawenv.toml"
            lock_path = temp_dir / "openclawenv.lock"
            shutil.copyfile(FIXTURES / "example.openclawenv.toml", manifest_path)
            shutil.copyfile(FIXTURES / "example.openclawenv.lock", lock_path)

            with patch("openenv.cli.build_image_with_args") as build_image:
                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    exit_code = main(
                        [
                            "build",
                            "--path",
                            str(manifest_path),
                            "--lock",
                            str(lock_path),
                            "--scan-format",
                            "json",
                            "--scan-policy",
                            "strict",
                            "--scan-fail-on-severity",
                            "medium",
                        ]
                    )

            self.assertEqual(exit_code, 0)
            build_image.assert_called_once()
            self.assertEqual(
                build_image.call_args.kwargs["build_args"],
                {
                    "OPENCLAWENV_SKILL_SCAN_FAIL_ON_SEVERITY": "medium",
                    "OPENCLAWENV_SKILL_SCAN_FORMAT": "json",
                    "OPENCLAWENV_SKILL_SCAN_POLICY": "strict",
                },
            )

    def test_export_compose_prefers_sidecar_env_file(self) -> None:
        with workspace_dir() as temp_dir:
            manifest_path = temp_dir / "openclawenv.toml"
            lock_path = temp_dir / "openclawenv.lock"
            compose_path = temp_dir / "docker-compose-sidecar-agent.yml"
            env_path = temp_dir / ".sidecar-agent.env"
            manifest_path.write_text(
                """
schema_version = 1

[project]
name = "sidecar-agent"
version = "0.1.0"
description = "sidecar secrets"
runtime = "openclaw"

[runtime]
base_image = "python:3.12-slim@sha256:1111111111111111111111111111111111111111111111111111111111111111"
python_version = "3.12"
python_packages = ["requests==2.32.3"]
env = { PYTHONUNBUFFERED = "1" }
user = "agent"
workdir = "/workspace"

[agent]
agents_md = "a"
soul_md = "b"
user_md = "c"

[openclaw]
agent_id = "main"
agent_name = "Sidecar Agent"

[openclaw.sandbox]
mode = "workspace-write"
scope = "session"
workspace_access = "full"
network = "none"
read_only_root = false
""".strip(),
                encoding="utf-8",
            )
            canonical_env = "OPENAI_API_KEY=top-secret\n"
            (temp_dir / ".env").write_text(canonical_env, encoding="utf-8")
            manifest, raw_manifest_text = load_manifest(manifest_path)
            write_lockfile(lock_path, build_lockfile(manifest, raw_manifest_text))

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "export",
                        "compose",
                        "--path",
                        str(manifest_path),
                        "--lock",
                        str(lock_path),
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertTrue(compose_path.exists())
            self.assertTrue(env_path.exists())
            env_text = env_path.read_text(encoding="utf-8")
            self.assertIn("OPENAI_API_KEY=top-secret", env_text)
            self.assertIn("OPENCLAW_IMAGE=openclawenv/sidecar-agent:0.1.0", env_text)
            self.assertIn("OPENCLAW_CONFIG_DIR=./.openclaw", env_text)

    def test_validate_prints_summary(self) -> None:
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = main(
                ["validate", "--path", str(FIXTURES / "example.openclawenv.toml")]
            )

        self.assertEqual(exit_code, 0)
        self.assertIn("Manifest valid", stdout.getvalue())

    def test_scan_logs_kept_artifacts_directory(self) -> None:
        with workspace_dir() as temp_dir:
            manifest_path = temp_dir / "openclawenv.toml"
            shutil.copyfile(FIXTURES / "example.openclawenv.toml", manifest_path)
            kept_dir = temp_dir / ".openclawenv-scan"

            stdout = io.StringIO()
            with patch("openenv.cli.run_skill_scanner", return_value=kept_dir):
                with redirect_stdout(stdout):
                    exit_code = main(["scan", "--path", str(manifest_path)])

            self.assertEqual(exit_code, 0)
            self.assertIn(str(kept_dir), stdout.getvalue())

    def test_export_compose_uses_explicit_output_path(self) -> None:
        with workspace_dir() as temp_dir:
            manifest_path = temp_dir / "openclawenv.toml"
            lock_path = temp_dir / "openclawenv.lock"
            compose_path = temp_dir / "custom-compose.yml"
            env_path = temp_dir / ".operations-agent.env"
            dockerfile_path = temp_dir / "Dockerfile"
            shutil.copyfile(FIXTURES / "example.openclawenv.toml", manifest_path)
            shutil.copyfile(FIXTURES / "example.openclawenv.lock", lock_path)

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "export",
                        "compose",
                        "--path",
                        str(manifest_path),
                        "--lock",
                        str(lock_path),
                        "--output",
                        str(compose_path),
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertTrue(compose_path.exists())
            self.assertTrue(env_path.exists())
            self.assertTrue(dockerfile_path.exists())

    def test_main_returns_one_for_manifest_lock_mismatch(self) -> None:
        with workspace_dir() as temp_dir:
            manifest_path = temp_dir / "openclawenv.toml"
            lock_path = temp_dir / "openclawenv.lock"
            shutil.copyfile(FIXTURES / "example.openclawenv.toml", manifest_path)
            shutil.copyfile(FIXTURES / "example.openclawenv.lock", lock_path)
            lock_text = lock_path.read_text(encoding="utf-8").replace(
                '"manifest_hash": "',
                '"manifest_hash": "mismatch-',
                1,
            )
            lock_path.write_text(lock_text, encoding="utf-8")

            stderr = io.StringIO()
            with redirect_stderr(stderr):
                exit_code = main(
                    [
                        "export",
                        "dockerfile",
                        "--path",
                        str(manifest_path),
                        "--lock",
                        str(lock_path),
                    ]
                )

            self.assertEqual(exit_code, 1)
            self.assertIn("lockfile does not match", stderr.getvalue())

    def test_main_returns_command_error_exit_code(self) -> None:
        stderr = io.StringIO()
        with patch(
            "openenv.cli._handle_validate",
            side_effect=CommandError("bad command", exit_code=9),
        ):
            with redirect_stderr(stderr):
                exit_code = main(["validate", "--path", str(FIXTURES / "example.openclawenv.toml")])

        self.assertEqual(exit_code, 9)
        self.assertIn("bad command", stderr.getvalue())

