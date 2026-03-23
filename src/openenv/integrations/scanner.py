"""Skill scanner integration for OpenClawenv."""

from __future__ import annotations

import shutil
import subprocess
import uuid
from pathlib import Path

from openenv.core.errors import CommandError
from openenv.core.models import Manifest
from openenv.core.utils import rewrite_openclaw_home_paths


def materialize_skills(manifest: Manifest, target_dir: str | Path) -> Path:
    """Write inline skills to a directory tree consumable by skill-scanner."""
    skills_root = Path(target_dir)
    skills_root.mkdir(parents=True, exist_ok=True)
    for skill in manifest.skills:
        skill_dir = skills_root / skill.name
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(
            skill.rendered_content(
                state_dir=manifest.openclaw.state_dir,
                workspace=manifest.openclaw.workspace,
            ),
            encoding="utf-8",
        )
        for relative_path, content in sorted(skill.assets.items()):
            asset_path = skill_dir / relative_path
            asset_path.parent.mkdir(parents=True, exist_ok=True)
            asset_path.write_text(
                rewrite_openclaw_home_paths(
                    content,
                    state_dir=manifest.openclaw.state_dir,
                    workspace=manifest.openclaw.workspace,
                ),
                encoding="utf-8",
            )
    return skills_root


def run_skill_scanner(
    manifest_path: str | Path,
    manifest: Manifest,
    *,
    scanner_bin: str = "skill-scanner",
    scanner_args: list[str] | None = None,
    keep_artifacts: bool = False,
) -> Path | None:
    """Materialize skills and invoke the external skill-scanner CLI."""
    manifest_root = Path(manifest_path).resolve().parent
    extra_args = list(scanner_args or [])
    if extra_args and extra_args[0] == "--":
        extra_args = extra_args[1:]

    scan_root = manifest_root / f"openclawenv-scan-tmp-{uuid.uuid4().hex}"
    scan_root.mkdir(parents=True, exist_ok=False)
    try:
        skills_root = materialize_skills(manifest, scan_root / "skills")
        command = [scanner_bin, "scan-all", str(skills_root), "--recursive", *extra_args]
        try:
            subprocess.run(command, check=True, cwd=manifest_root)
        except OSError as exc:
            raise CommandError(
                "skill-scanner is not available on PATH. "
                "Install it with `pip install .[scan]` or provide --scanner-bin."
            ) from exc
        except subprocess.CalledProcessError as exc:
            raise CommandError(
                f"skill-scanner failed with exit code {exc.returncode}.",
                exit_code=exc.returncode,
            ) from exc

        if keep_artifacts:
            destination = manifest_root / ".openclawenv-scan"
            if destination.exists():
                shutil.rmtree(destination, ignore_errors=True)
            shutil.copytree(scan_root, destination)
            return destination
    finally:
        shutil.rmtree(scan_root, ignore_errors=True)
    return None
