from __future__ import annotations

import unittest
from pathlib import Path

from openenv.docker.dockerfile import (
    DEFAULT_GLOBAL_NODE_TOOLS,
    DEFAULT_NODE_PACKAGES,
    DEFAULT_PYTHON_VENV_PATH,
    DEFAULT_SKILL_SCAN_FAIL_ON_SEVERITY,
    DEFAULT_SKILL_SCAN_FORMAT,
    DEFAULT_SKILL_SCAN_POLICY,
    OPENCLAW_GATEWAY_RUNTIME_IMAGE,
    SKILL_SCANNER_REQUIREMENT,
    render_dockerfile,
)
from openenv.core.skills import FREERIDE_SKILL_NAME, FREERIDE_SKILL_SOURCE
from openenv.manifests.loader import load_manifest
from openenv.manifests.lockfile import build_lockfile, dump_lockfile


TESTS_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = TESTS_ROOT / "fixtures"


class DockerfileTests(unittest.TestCase):
    def test_dockerfile_matches_golden_fixture(self) -> None:
        manifest, raw_manifest_text = load_manifest(FIXTURES / "example.openclawenv.toml")
        lockfile = build_lockfile(manifest, raw_manifest_text)
        dockerfile = render_dockerfile(
            manifest,
            lockfile,
            raw_manifest_text=raw_manifest_text,
            raw_lock_text=dump_lockfile(lockfile),
        )
        expected = (FIXTURES / "example.Dockerfile").read_text(encoding="utf-8")

        self.assertEqual(dockerfile, expected)

    def test_dockerfile_uses_openclaw_gateway_runtime_base(self) -> None:
        manifest, raw_manifest_text = load_manifest(FIXTURES / "example.openclawenv.toml")
        lockfile = build_lockfile(manifest, raw_manifest_text)

        dockerfile = render_dockerfile(
            manifest,
            lockfile,
            raw_manifest_text=raw_manifest_text,
            raw_lock_text=dump_lockfile(lockfile),
        )

        self.assertIn(f"FROM {OPENCLAW_GATEWAY_RUNTIME_IMAGE}", dockerfile)
        self.assertIn(
            'LABEL io.openclawenv.sandbox-image="python:3.12-slim@sha256:',
            dockerfile,
        )
        self.assertIn('ARG OPENCLAW_INSTALL_BROWSER=""', dockerfile)
        self.assertIn('ARG OPENCLAW_INSTALL_DOCKER_CLI=""', dockerfile)
        self.assertIn("USER root", dockerfile)
        self.assertTrue(dockerfile.rstrip().endswith("USER root"))
        self.assertNotIn("WORKDIR /workspace", dockerfile)
        self.assertNotIn("USER agent", dockerfile)
        self.assertNotIn("USER node", dockerfile)
        self.assertIn(f'ENV VIRTUAL_ENV="{DEFAULT_PYTHON_VENV_PATH}"', dockerfile)
        self.assertIn(f'ENV PATH="{DEFAULT_PYTHON_VENV_PATH}/bin:$PATH"', dockerfile)

    def test_dockerfile_always_installs_skill_scanner(self) -> None:
        manifest, raw_manifest_text = load_manifest(FIXTURES / "example.openclawenv.toml")
        manifest.runtime.python_packages = []
        lockfile = build_lockfile(manifest, raw_manifest_text)
        lockfile.python_packages = []

        dockerfile = render_dockerfile(
            manifest,
            lockfile,
            raw_manifest_text=raw_manifest_text,
            raw_lock_text=dump_lockfile(lockfile),
        )

        self.assertIn(
            f"RUN python -m pip install --no-cache-dir {SKILL_SCANNER_REQUIREMENT}",
            dockerfile,
        )
        self.assertIn(
            f'RUN python -m venv "{DEFAULT_PYTHON_VENV_PATH}" '
            f'2>/dev/null || python -m virtualenv "{DEFAULT_PYTHON_VENV_PATH}"',
            dockerfile,
        )

    def test_dockerfile_always_installs_nodejs_and_npx_support(self) -> None:
        manifest, raw_manifest_text = load_manifest(FIXTURES / "example.openclawenv.toml")
        lockfile = build_lockfile(manifest, raw_manifest_text)

        dockerfile = render_dockerfile(
            manifest,
            lockfile,
            raw_manifest_text=raw_manifest_text,
            raw_lock_text=dump_lockfile(lockfile),
        )

        for package in DEFAULT_NODE_PACKAGES:
            self.assertIn(package, dockerfile)
        self.assertIn("python3-venv", dockerfile)
        self.assertIn("py3-virtualenv", dockerfile)
        for package in DEFAULT_GLOBAL_NODE_TOOLS:
            self.assertIn(package, dockerfile)
        self.assertIn("command -v npx", dockerfile)
        self.assertIn("npm exec --yes --", dockerfile)
        self.assertIn("command -v apt-get", dockerfile)
        self.assertIn("command -v apk", dockerfile)
        self.assertIn(
            "RUN npm install --global --no-fund --no-update-notifier agent-browser "
            "typescript@5.8.3",
            dockerfile,
        )
        self.assertIn("RUN agent-browser install", dockerfile)
        self.assertIn("OPENCLAW_INSTALL_BROWSER requires an apt-get based image", dockerfile)
        self.assertIn("OPENCLAW_INSTALL_DOCKER_CLI requires an apt-get based image", dockerfile)

    def test_dockerfile_runs_skill_scan_during_build(self) -> None:
        manifest, raw_manifest_text = load_manifest(FIXTURES / "example.openclawenv.toml")
        lockfile = build_lockfile(manifest, raw_manifest_text)

        dockerfile = render_dockerfile(
            manifest,
            lockfile,
            raw_manifest_text=raw_manifest_text,
            raw_lock_text=dump_lockfile(lockfile),
        )

        self.assertIn(
            f"ARG OPENCLAWENV_SKILL_SCAN_FORMAT={DEFAULT_SKILL_SCAN_FORMAT}",
            dockerfile,
        )
        self.assertIn(
            f"ARG OPENCLAWENV_SKILL_SCAN_POLICY={DEFAULT_SKILL_SCAN_POLICY}",
            dockerfile,
        )
        self.assertIn(
            "ARG OPENCLAWENV_SKILL_SCAN_FAIL_ON_SEVERITY="
            f"{DEFAULT_SKILL_SCAN_FAIL_ON_SEVERITY}",
            dockerfile,
        )
        self.assertIn(
            'skill-scanner scan-all "/opt/openclaw/workspace/skills" --recursive --check-overlap',
            dockerfile,
        )

    def test_dockerfile_installs_freeride_into_openclaw_workspace(self) -> None:
        manifest, raw_manifest_text = load_manifest(FIXTURES / "example.openclawenv.toml")
        lockfile = build_lockfile(manifest, raw_manifest_text)

        dockerfile = render_dockerfile(
            manifest,
            lockfile,
            raw_manifest_text=raw_manifest_text,
            raw_lock_text=dump_lockfile(lockfile),
        )

        self.assertIn('ln -sfn "/opt/openclaw" "/root/.openclaw"', dockerfile)
        self.assertNotIn('"/home/agent/.openclaw"', dockerfile)
        self.assertIn(
            f'RUN rm -rf "/opt/openclaw/workspace/skills/{FREERIDE_SKILL_NAME}" '
            f'"/opt/openclaw/workspace/skills/{FREERIDE_SKILL_SOURCE}" '
            f'&& (npx --yes clawhub@latest install "{FREERIDE_SKILL_SOURCE}" '
            '--workdir "/opt/openclaw/workspace" --force --no-input) '
            f'&& if [ -d "/opt/openclaw/workspace/skills/{FREERIDE_SKILL_SOURCE}" ]; '
            f'then mv "/opt/openclaw/workspace/skills/{FREERIDE_SKILL_SOURCE}" '
            f'"/opt/openclaw/workspace/skills/{FREERIDE_SKILL_NAME}"; fi',
            dockerfile,
        )
        self.assertIn(
            'RUN rm -rf "/opt/openclaw/workspace/skills/deus-context-engine" '
            '&& (npx --yes clawhub@latest install "deus-context-engine" '
            '--workdir "/opt/openclaw/workspace" --force --no-input)',
            dockerfile,
        )
        self.assertNotIn("@openclaw/clawhub", dockerfile)
        self.assertNotIn("pip install --no-cache-dir -e", dockerfile)

    def test_dockerfile_skips_build_time_skill_scan_without_skills(self) -> None:
        manifest, raw_manifest_text = load_manifest(FIXTURES / "example.openclawenv.toml")
        manifest.skills = []
        lockfile = build_lockfile(manifest, raw_manifest_text)

        dockerfile = render_dockerfile(
            manifest,
            lockfile,
            raw_manifest_text=raw_manifest_text,
            raw_lock_text=dump_lockfile(lockfile),
        )

        self.assertNotIn("skill-scanner scan-all", dockerfile)
        self.assertNotIn("OPENCLAWENV_SKILL_SCAN_POLICY", dockerfile)

