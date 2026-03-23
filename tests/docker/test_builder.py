from __future__ import annotations

import shutil
import subprocess
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from openenv.core.errors import CommandError
from openenv.docker.builder import build_image, build_image_with_args, default_image_tag


TESTS_ROOT = Path(__file__).resolve().parents[1]
TEMP_ROOT = TESTS_ROOT / "_tmp"
TEMP_ROOT.mkdir(exist_ok=True)


class _LocalTemporaryDirectory:
    def __init__(self, *args, **kwargs) -> None:
        self.prefix = kwargs.get("prefix", "openclawenv-build-")

    def __enter__(self) -> str:
        self.path = TEMP_ROOT / f"{self.prefix}{uuid.uuid4().hex[:8]}"
        self.path.mkdir()
        return str(self.path)

    def __exit__(self, exc_type, exc, tb) -> bool:
        shutil.rmtree(self.path, ignore_errors=True)
        return False


class BuilderTests(unittest.TestCase):
    def test_default_image_tag_slugifies_project_name(self) -> None:
        self.assertEqual(default_image_tag("My Fancy Bot", "1.2.3"), "openclawenv/my-fancy-bot:1.2.3")

    def test_build_image_delegates_to_build_image_with_args(self) -> None:
        with patch("openenv.docker.builder.build_image_with_args") as build_image_with_args_mock:
            build_image("FROM alpine\n", "openclawenv/demo:1.0.0")

        build_image_with_args_mock.assert_called_once_with(
            "FROM alpine\n",
            "openclawenv/demo:1.0.0",
            build_args=None,
        )

    def test_build_image_with_args_runs_docker_build(self) -> None:
        captured_commands: list[list[str]] = []

        def fake_run(command: list[str], *, check: bool) -> subprocess.CompletedProcess[str]:
            captured_commands.append(command)
            self.assertTrue(check)
            dockerfile_path = Path(command[5])
            self.assertEqual(dockerfile_path.read_text(encoding="utf-8"), "FROM alpine\n")
            return subprocess.CompletedProcess(command, 0)

        with patch("openenv.docker.builder.tempfile.TemporaryDirectory", _LocalTemporaryDirectory):
            with patch("openenv.docker.builder.subprocess.run", side_effect=fake_run):
                build_image_with_args(
                    "FROM alpine\n",
                    "openclawenv/demo:1.0.0",
                    build_args={"BETA": "2", "ALPHA": "1"},
                )

        self.assertEqual(len(captured_commands), 1)
        command = captured_commands[0]
        self.assertEqual(command[:4], ["docker", "build", "--tag", "openclawenv/demo:1.0.0"])
        self.assertEqual(command[4], "--file")
        self.assertIn("--build-arg", command)
        self.assertIn("ALPHA=1", command)
        self.assertIn("BETA=2", command)

    def test_build_image_with_args_raises_when_docker_is_missing(self) -> None:
        with patch("openenv.docker.builder.tempfile.TemporaryDirectory", _LocalTemporaryDirectory):
            with patch(
                "openenv.docker.builder.subprocess.run",
                side_effect=OSError("docker not found"),
            ):
                with self.assertRaises(CommandError) as ctx:
                    build_image_with_args("FROM alpine\n", "openclawenv/demo:1.0.0", build_args=None)

        self.assertIn("Docker is not available on PATH", str(ctx.exception))

    def test_build_image_with_args_raises_when_docker_build_fails(self) -> None:
        with patch("openenv.docker.builder.tempfile.TemporaryDirectory", _LocalTemporaryDirectory):
            with patch(
                "openenv.docker.builder.subprocess.run",
                side_effect=subprocess.CalledProcessError(
                    returncode=23,
                    cmd=["docker", "build"],
                ),
            ):
                with self.assertRaises(CommandError) as ctx:
                    build_image_with_args("FROM alpine\n", "openclawenv/demo:1.0.0", build_args=None)

        self.assertIn("Docker build failed for tag openclawenv/demo:1.0.0", str(ctx.exception))

