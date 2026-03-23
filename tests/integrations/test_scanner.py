from __future__ import annotations

import shutil
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from openenv.core.errors import CommandError
from openenv.integrations.scanner import materialize_skills, run_skill_scanner
from openenv.manifests.loader import load_manifest


TESTS_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = TESTS_ROOT / "fixtures"
TEMP_ROOT = TESTS_ROOT / "_tmp"
TEMP_ROOT.mkdir(exist_ok=True)


class ScannerTests(unittest.TestCase):
    def test_materialize_skills_writes_skill_tree(self) -> None:
        manifest, _ = load_manifest(FIXTURES / "example.openclawenv.toml")
        target = TEMP_ROOT / "scanner-materialize"
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)

        skills_root = materialize_skills(manifest, target)

        self.assertTrue((skills_root / "deus-context-engine" / "SKILL.md").exists())
        self.assertTrue((skills_root / "self-improving-agent" / "SKILL.md").exists())
        self.assertTrue((skills_root / "skill-security-review" / "SKILL.md").exists())
        self.assertTrue((skills_root / "free-ride" / "SKILL.md").exists())
        self.assertTrue((skills_root / "agent-browser-clawdbot" / "SKILL.md").exists())
        self.assertTrue((skills_root / "incident-brief" / "SKILL.md").exists())
        self.assertTrue(
            (skills_root / "incident-brief" / "templates" / "report.md").exists()
        )

        shutil.rmtree(target, ignore_errors=True)

    def test_materialize_skills_rewrites_home_based_openclaw_paths(self) -> None:
        manifest, _ = load_manifest(FIXTURES / "example.openclawenv.toml")
        incident_brief = next(
            skill for skill in manifest.skills if skill.name == "incident-brief"
        )
        incident_brief.content = (
            "---\n"
            "name: incident-brief\n"
            "description: Summarize incidents.\n"
            "---\n\n"
            "Read `/home/deus/.openclaw/workspace/memory/projects/demo.md` "
            "and inspect `~/.openclaw/openclaw.json`.\n"
        )
        incident_brief.assets["templates/report.md"] = (
            "Workspace: ${HOME}/.openclaw/workspace/memory/projects/\n"
            "State: $HOME/.openclaw/cache.db\n"
        )
        target = TEMP_ROOT / "scanner-rewrite"
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)

        skills_root = materialize_skills(manifest, target)
        rendered_skill = (skills_root / "incident-brief" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        rendered_asset = (
            skills_root / "incident-brief" / "templates" / "report.md"
        ).read_text(encoding="utf-8")

        self.assertIn(
            f"{manifest.openclaw.workspace}/memory/projects/demo.md",
            rendered_skill,
        )
        self.assertIn(
            f"{manifest.openclaw.state_dir}/openclaw.json",
            rendered_skill,
        )
        self.assertIn(
            f"{manifest.openclaw.workspace}/memory/projects/",
            rendered_asset,
        )
        self.assertIn(
            f"{manifest.openclaw.state_dir}/cache.db",
            rendered_asset,
        )
        self.assertNotIn("/home/deus/.openclaw", rendered_skill)
        self.assertNotIn("${HOME}/.openclaw", rendered_asset)
        self.assertNotIn("$HOME/.openclaw", rendered_asset)

        shutil.rmtree(target, ignore_errors=True)

    def test_run_skill_scanner_invokes_scan_all(self) -> None:
        work_dir = TEMP_ROOT / "scanner-run"
        if work_dir.exists():
            shutil.rmtree(work_dir, ignore_errors=True)
        work_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = work_dir / "openclawenv.toml"
        shutil.copyfile(FIXTURES / "example.openclawenv.toml", manifest_path)
        manifest, _ = load_manifest(manifest_path)

        with patch("openenv.integrations.scanner.subprocess.run") as subprocess_run:
            result = run_skill_scanner(
                manifest_path,
                manifest,
                scanner_args=["--", "--policy", "strict"],
            )

        self.assertIsNone(result)
        command = (
            subprocess_run.call_args.kwargs["args"]
            if "args" in subprocess_run.call_args.kwargs
            else subprocess_run.call_args.args[0]
        )
        self.assertEqual(command[0], "skill-scanner")
        self.assertEqual(command[1], "scan-all")
        self.assertIn("--recursive", command)
        self.assertIn("--policy", command)
        self.assertIn("strict", command)

        shutil.rmtree(work_dir, ignore_errors=True)

    def test_run_skill_scanner_keeps_materialized_artifacts_when_requested(self) -> None:
        work_dir = TEMP_ROOT / "scanner-keep"
        if work_dir.exists():
            shutil.rmtree(work_dir, ignore_errors=True)
        work_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = work_dir / "openclawenv.toml"
        shutil.copyfile(FIXTURES / "example.openclawenv.toml", manifest_path)
        manifest, _ = load_manifest(manifest_path)

        with patch("openenv.integrations.scanner.subprocess.run") as subprocess_run:
            destination = run_skill_scanner(
                manifest_path,
                manifest,
                keep_artifacts=True,
            )

        self.assertIsNotNone(destination)
        self.assertTrue(destination.exists())
        self.assertTrue((destination / "skills" / "incident-brief" / "SKILL.md").exists())
        subprocess_run.assert_called_once()

        shutil.rmtree(work_dir, ignore_errors=True)

    def test_run_skill_scanner_raises_when_scanner_is_missing(self) -> None:
        work_dir = TEMP_ROOT / "scanner-missing"
        if work_dir.exists():
            shutil.rmtree(work_dir, ignore_errors=True)
        work_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = work_dir / "openclawenv.toml"
        shutil.copyfile(FIXTURES / "example.openclawenv.toml", manifest_path)
        manifest, _ = load_manifest(manifest_path)

        with patch("openenv.integrations.scanner.subprocess.run", side_effect=OSError("missing")):
            with self.assertRaises(CommandError) as ctx:
                run_skill_scanner(manifest_path, manifest)

        self.assertIn("skill-scanner is not available on PATH", str(ctx.exception))
        self.assertFalse((work_dir / ".openclawenv-scan").exists())

        shutil.rmtree(work_dir, ignore_errors=True)

    def test_run_skill_scanner_raises_when_scanner_fails(self) -> None:
        work_dir = TEMP_ROOT / "scanner-fail"
        if work_dir.exists():
            shutil.rmtree(work_dir, ignore_errors=True)
        work_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = work_dir / "openclawenv.toml"
        shutil.copyfile(FIXTURES / "example.openclawenv.toml", manifest_path)
        manifest, _ = load_manifest(manifest_path)

        with patch(
            "openenv.integrations.scanner.subprocess.run",
            side_effect=subprocess.CalledProcessError(
                returncode=5,
                cmd=["skill-scanner"],
            ),
        ):
            with self.assertRaises(CommandError) as ctx:
                run_skill_scanner(manifest_path, manifest)

        self.assertEqual(ctx.exception.exit_code, 5)
        self.assertIn("skill-scanner failed with exit code 5", str(ctx.exception))

        shutil.rmtree(work_dir, ignore_errors=True)

