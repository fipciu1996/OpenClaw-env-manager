from __future__ import annotations

import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from openenv.core.errors import LockResolutionError
from openenv.manifests.loader import load_manifest
from openenv.core.errors import ValidationError
from openenv.manifests.lockfile import (
    build_lockfile,
    dump_lockfile,
    load_lockfile,
    parse_lockfile,
    resolve_base_image,
)


TESTS_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = TESTS_ROOT / "fixtures"


class LockfileTests(unittest.TestCase):
    def test_lockfile_matches_golden_fixture(self) -> None:
        manifest, raw_manifest_text = load_manifest(FIXTURES / "example.openclawenv.toml")
        lockfile = build_lockfile(manifest, raw_manifest_text)
        expected = (FIXTURES / "example.openclawenv.lock").read_text(encoding="utf-8")

        self.assertEqual(dump_lockfile(lockfile), expected)

    def test_lockfile_is_deterministic(self) -> None:
        manifest, raw_manifest_text = load_manifest(FIXTURES / "example.openclawenv.toml")

        first = dump_lockfile(build_lockfile(manifest, raw_manifest_text))
        second = dump_lockfile(build_lockfile(manifest, raw_manifest_text))

        self.assertEqual(first, second)

    def test_skill_change_updates_manifest_hash(self) -> None:
        manifest, raw_manifest_text = load_manifest(FIXTURES / "example.openclawenv.toml")
        base_lock = build_lockfile(manifest, raw_manifest_text)
        incident_brief = next(
            skill for skill in manifest.skills if skill.name == "incident-brief"
        )
        incident_brief.content = incident_brief.content + "\n3. Capture action items.\n"

        changed_lock = build_lockfile(manifest, raw_manifest_text)

        self.assertNotEqual(base_lock.manifest_hash, changed_lock.manifest_hash)

    def test_rejects_unpinned_node_requirement(self) -> None:
        manifest, raw_manifest_text = load_manifest(FIXTURES / "example.openclawenv.toml")
        manifest.runtime.node_packages = ["typescript"]

        with self.assertRaises(LockResolutionError):
            build_lockfile(manifest, raw_manifest_text)

    def test_pulls_missing_local_base_image_before_failing(self) -> None:
        manifest, raw_manifest_text = load_manifest(FIXTURES / "example.openclawenv.toml")
        manifest.runtime.base_image = "python:3.12-slim"
        digest = "sha256:" + "1" * 64
        with patch("openenv.manifests.lockfile.subprocess.run") as run_mock:
            run_mock.side_effect = [
                subprocess.CalledProcessError(
                    returncode=1,
                    cmd=["docker", "image", "inspect", manifest.runtime.base_image],
                    stderr="Error response from daemon: No such image: python:3.12-slim",
                ),
                subprocess.CompletedProcess(
                    args=["docker", "image", "pull", manifest.runtime.base_image],
                    returncode=0,
                    stdout="Pulled",
                    stderr="",
                ),
                subprocess.CompletedProcess(
                    args=["docker", "image", "inspect", manifest.runtime.base_image],
                    returncode=0,
                    stdout=f'["python@{digest}"]',
                    stderr="",
                ),
            ]

            lockfile = build_lockfile(manifest, raw_manifest_text)

        self.assertEqual(lockfile.base_image["digest"], digest)
        self.assertEqual(
            lockfile.base_image["resolved_reference"],
            f"python:3.12-slim@{digest}",
        )
        self.assertEqual(
            run_mock.call_args_list[1].args[0],
            ["docker", "image", "pull", "python:3.12-slim"],
        )

    def test_preserves_original_tag_when_resolving_local_base_image(self) -> None:
        manifest, raw_manifest_text = load_manifest(FIXTURES / "example.openclawenv.toml")
        manifest.runtime.base_image = "python:3.12-slim"
        digest = "sha256:" + "2" * 64
        with patch("openenv.manifests.lockfile.subprocess.run") as run_mock:
            run_mock.return_value = subprocess.CompletedProcess(
                args=["docker", "image", "inspect", manifest.runtime.base_image],
                returncode=0,
                stdout=f'["python@{digest}"]',
                stderr="",
            )

            lockfile = build_lockfile(manifest, raw_manifest_text)

        self.assertEqual(
            lockfile.base_image["resolved_reference"],
            f"python:3.12-slim@{digest}",
        )

    def test_reports_pull_failure_when_missing_local_base_image_cannot_be_downloaded(self) -> None:
        manifest, raw_manifest_text = load_manifest(FIXTURES / "example.openclawenv.toml")
        manifest.runtime.base_image = "python:3.12-slim"
        with patch("openenv.manifests.lockfile.subprocess.run") as run_mock:
            run_mock.side_effect = [
                subprocess.CalledProcessError(
                    returncode=1,
                    cmd=["docker", "image", "inspect", manifest.runtime.base_image],
                    stderr="Error response from daemon: No such image: python:3.12-slim",
                ),
                subprocess.CalledProcessError(
                    returncode=1,
                    cmd=["docker", "image", "pull", manifest.runtime.base_image],
                    stderr="Error response from daemon: pull access denied",
                ),
            ]

            with self.assertRaises(LockResolutionError) as ctx:
                build_lockfile(manifest, raw_manifest_text)

        self.assertIn("docker pull failed", str(ctx.exception))
        self.assertIn("pull access denied", str(ctx.exception))

    def test_rejects_unpinned_python_requirement(self) -> None:
        manifest, raw_manifest_text = load_manifest(FIXTURES / "example.openclawenv.toml")
        manifest.runtime.python_packages = ["requests>=2.0"]

        with self.assertRaises(LockResolutionError):
            build_lockfile(manifest, raw_manifest_text)

    def test_resolve_base_image_returns_pinned_digest_without_docker(self) -> None:
        digest = "sha256:" + "3" * 64

        image = resolve_base_image(f"python:3.12-slim@{digest}")

        self.assertEqual(
            image,
            {
                "digest": digest,
                "resolved_reference": f"python:3.12-slim@{digest}",
            },
        )

    def test_resolve_base_image_reports_docker_missing(self) -> None:
        with patch(
            "openenv.manifests.lockfile.subprocess.run",
            side_effect=OSError("docker missing"),
        ):
            with self.assertRaises(LockResolutionError) as ctx:
                resolve_base_image("python:3.12-slim")

        self.assertIn("Docker is required", str(ctx.exception))

    def test_resolve_base_image_rejects_invalid_repo_digests_json(self) -> None:
        with patch("openenv.manifests.lockfile.subprocess.run") as run_mock:
            run_mock.return_value = subprocess.CompletedProcess(
                args=["docker", "image", "inspect", "python:3.12-slim"],
                returncode=0,
                stdout="not-json",
                stderr="",
            )

            with self.assertRaises(LockResolutionError) as ctx:
                resolve_base_image("python:3.12-slim")

        self.assertIn("unreadable RepoDigests payload", str(ctx.exception))

    def test_resolve_base_image_rejects_missing_repo_digests(self) -> None:
        with patch("openenv.manifests.lockfile.subprocess.run") as run_mock:
            run_mock.return_value = subprocess.CompletedProcess(
                args=["docker", "image", "inspect", "python:3.12-slim"],
                returncode=0,
                stdout="[]",
                stderr="",
            )

            with self.assertRaises(LockResolutionError) as ctx:
                resolve_base_image("python:3.12-slim")

        self.assertIn("did not return a RepoDigest", str(ctx.exception))

    def test_resolve_base_image_rejects_digestless_reference(self) -> None:
        with patch("openenv.manifests.lockfile.subprocess.run") as run_mock:
            run_mock.return_value = subprocess.CompletedProcess(
                args=["docker", "image", "inspect", "python:3.12-slim"],
                returncode=0,
                stdout='["python:3.12-slim"]',
                stderr="",
            )

            with self.assertRaises(LockResolutionError) as ctx:
                resolve_base_image("python:3.12-slim")

        self.assertIn("did not include a digest", str(ctx.exception))

    def test_resolve_base_image_reports_pull_then_inspect_failure(self) -> None:
        with patch("openenv.manifests.lockfile.subprocess.run") as run_mock:
            run_mock.side_effect = [
                subprocess.CalledProcessError(
                    returncode=1,
                    cmd=["docker", "image", "inspect", "python:3.12-slim"],
                    stderr="Error response from daemon: No such image",
                ),
                subprocess.CompletedProcess(
                    args=["docker", "image", "pull", "python:3.12-slim"],
                    returncode=0,
                    stdout="Pulled",
                    stderr="",
                ),
                subprocess.CalledProcessError(
                    returncode=1,
                    cmd=["docker", "image", "inspect", "python:3.12-slim"],
                    stderr="Error response from daemon: inspection failed",
                ),
            ]

            with self.assertRaises(LockResolutionError) as ctx:
                resolve_base_image("python:3.12-slim")

        self.assertIn("still could not be inspected locally", str(ctx.exception))

    def test_load_lockfile_reports_missing_file(self) -> None:
        with self.assertRaises(ValidationError) as ctx:
            load_lockfile(FIXTURES / "missing.openclawenv.lock")

        self.assertIn("Lockfile not found", str(ctx.exception))

    def test_load_lockfile_reports_invalid_json(self) -> None:
        path = FIXTURES / "broken.openclawenv.lock"
        path.write_text("{broken", encoding="utf-8")
        try:
            with self.assertRaises(ValidationError) as ctx:
                load_lockfile(path)
        finally:
            path.unlink(missing_ok=True)

        self.assertIn("Invalid JSON", str(ctx.exception))

    def test_parse_lockfile_rejects_invalid_root(self) -> None:
        with self.assertRaises(ValidationError) as ctx:
            parse_lockfile(["not", "an", "object"])

        self.assertIn("Lockfile root must be an object", str(ctx.exception))

    def test_parse_lockfile_rejects_missing_keys(self) -> None:
        with self.assertRaises(ValidationError) as ctx:
            parse_lockfile({"lock_version": 1})

        self.assertIn("missing required keys", str(ctx.exception))

    def test_parse_lockfile_rejects_wrong_types(self) -> None:
        payload = {
            "lock_version": 1,
            "manifest_hash": "abc",
            "base_image": [],
            "python_packages": [],
            "node_packages": [],
            "system_packages": [],
            "source_snapshot": {},
        }
        with self.assertRaises(ValidationError) as ctx:
            parse_lockfile(payload)

        self.assertIn("lockfile.base_image must be an object", str(ctx.exception))

    def test_parse_lockfile_rejects_empty_manifest_hash(self) -> None:
        payload = {
            "lock_version": 1,
            "manifest_hash": "   ",
            "base_image": {},
            "python_packages": [],
            "node_packages": [],
            "system_packages": [],
            "source_snapshot": {},
        }
        with self.assertRaises(ValidationError) as ctx:
            parse_lockfile(payload)

        self.assertIn("manifest_hash must be a non-empty string", str(ctx.exception))

