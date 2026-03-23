"""Docker image build helpers."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from openenv.core.errors import CommandError
from openenv.core.utils import slugify_name


def default_image_tag(project_name: str, version: str) -> str:
    """Compute the default docker tag for a project."""
    return f"openclawenv/{slugify_name(project_name)}:{version}"


def build_image(dockerfile_text: str, tag: str) -> None:
    """Build a Docker image from a rendered Dockerfile."""
    build_image_with_args(dockerfile_text, tag, build_args=None)


def build_image_with_args(
    dockerfile_text: str,
    tag: str,
    *,
    build_args: dict[str, str] | None,
) -> None:
    """Build a Docker image from a rendered Dockerfile with optional build args."""
    with tempfile.TemporaryDirectory(prefix="openclawenv-build-") as temp_dir:
        dockerfile_path = Path(temp_dir) / "Dockerfile"
        dockerfile_path.write_text(dockerfile_text, encoding="utf-8")
        command = [
            "docker",
            "build",
            "--tag",
            tag,
            "--file",
            str(dockerfile_path),
            temp_dir,
        ]
        for key, value in sorted((build_args or {}).items()):
            command.extend(["--build-arg", f"{key}={value}"])
        try:
            subprocess.run(command, check=True)
        except OSError as exc:
            raise CommandError("Docker is not available on PATH.") from exc
        except subprocess.CalledProcessError as exc:
            raise CommandError(
                f"Docker build failed for tag {tag} with exit code {exc.returncode}."
            ) from exc
