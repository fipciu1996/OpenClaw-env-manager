from __future__ import annotations

from copy import deepcopy
import unittest
from pathlib import Path

from openenv.docker.compose import (
    AllBotsComposeSpec,
    all_bots_compose_filename,
    cli_container_name,
    default_compose_filename,
    default_env_filename,
    gateway_container_name,
    render_all_bots_compose,
    render_compose,
    render_env_file,
)
from openenv.manifests.loader import load_manifest
from openenv.manifests.lockfile import build_lockfile


TESTS_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = TESTS_ROOT / "fixtures"


class ComposeTests(unittest.TestCase):
    def test_compose_matches_golden_fixture(self) -> None:
        manifest, raw_manifest_text = load_manifest(FIXTURES / "example.openclawenv.toml")
        build_lockfile(manifest, raw_manifest_text)

        compose_text = render_compose(manifest, "openclawenv/ops-agent:1.2.3")
        expected = (FIXTURES / "example.compose.yml").read_text(encoding="utf-8")

        self.assertEqual(compose_text, expected)

    def test_compose_builds_gateway_image_from_local_dockerfile(self) -> None:
        manifest, _ = load_manifest(FIXTURES / "example.openclawenv.toml")

        compose_text = render_compose(manifest, "openclawenv/ops-agent:1.2.3")

        self.assertIn('image: "${OPENCLAW_IMAGE:-openclawenv/ops-agent:1.2.3}"', compose_text)
        self.assertIn("    build:", compose_text)
        self.assertIn('      context: "."', compose_text)
        self.assertIn('      dockerfile: "Dockerfile"', compose_text)

    def test_default_compose_filename_uses_bot_name(self) -> None:
        self.assertEqual(
            default_compose_filename("Operations Agent"),
            "docker-compose-operations-agent.yml",
        )

    def test_default_env_filename_uses_bot_name(self) -> None:
        self.assertEqual(
            default_env_filename("Operations Agent"),
            ".operations-agent.env",
        )

    def test_all_bots_compose_filename_is_stable(self) -> None:
        self.assertEqual(all_bots_compose_filename(), "all-bots-compose.yml")

    def test_container_names_use_openclaw_suffixes(self) -> None:
        self.assertEqual(
            gateway_container_name("Operations Agent"),
            "operations-agent-openclaw-gateway",
        )
        self.assertEqual(
            cli_container_name("Operations Agent"),
            "operations-agent-openclaw-cli",
        )

    def test_env_file_matches_golden_fixture(self) -> None:
        manifest, _ = load_manifest(FIXTURES / "example.openclawenv.toml")

        env_text = render_env_file(manifest, "openclawenv/ops-agent:1.2.3")
        expected = (FIXTURES / "example.bot.env").read_text(encoding="utf-8")

        self.assertEqual(env_text, expected)

    def test_render_all_bots_compose_contains_shared_gateway_and_each_bot(self) -> None:
        manifest, _ = load_manifest(FIXTURES / "example.openclawenv.toml")
        second_manifest = deepcopy(manifest)
        second_manifest.project.name = "analytics-agent"
        second_manifest.project.version = "2.0.0"
        second_manifest.project.description = "Analytics support"
        second_manifest.openclaw.agent_name = "Analytics Agent"
        second_manifest.runtime.env["OPENCLAWENV_PROJECT"] = "analytics-agent"

        compose_text = render_all_bots_compose(
            [
                AllBotsComposeSpec(
                    slug="operations-agent",
                    manifest=manifest,
                    image_tag="openclawenv/ops-agent:1.2.3",
                ),
                AllBotsComposeSpec(
                    slug="analytics-agent",
                    manifest=second_manifest,
                    image_tag="openclawenv/analytics-agent:2.0.0",
                ),
            ]
        )

        self.assertIn('container_name: "all-bots-openclaw-gateway"', compose_text)
        self.assertEqual(compose_text.count("openclaw-gateway:"), 1)
        self.assertIn("  bot-operations-agent:", compose_text)
        self.assertIn("  bot-analytics-agent:", compose_text)
        self.assertIn('      context: "./operations-agent"', compose_text)
        self.assertIn('      context: "./analytics-agent"', compose_text)
        self.assertIn('      - "./operations-agent/.operations-agent.env"', compose_text)
        self.assertIn('      - "./analytics-agent/.analytics-agent.env"', compose_text)

