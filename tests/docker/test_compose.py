from __future__ import annotations

from copy import deepcopy
import unittest
from pathlib import Path

from openenv.docker.compose import (
    AllBotsComposeSpec,
    DEFAULT_OPENCLAW_BRIDGE_HOST_BIND,
    DEFAULT_OPENCLAW_GATEWAY_HOST_BIND,
    DEFAULT_OPENCLAW_NOFILE_HARD,
    DEFAULT_OPENCLAW_NOFILE_SOFT,
    DEFAULT_OPENCLAW_NPROC,
    DEFAULT_OPENCLAW_PIDS_LIMIT,
    DEFAULT_OPENCLAW_TMPFS,
    OPENCLAW_HELPER_ENTRYPOINT,
    all_bots_compose_filename,
    all_bots_env_filename,
    cli_container_name,
    default_compose_filename,
    default_env_filename,
    gateway_container_name,
    render_all_bots_compose,
    render_all_bots_env_file,
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
        self.assertIn('        OPENCLAW_INSTALL_BROWSER: "${OPENCLAW_INSTALL_BROWSER:-}"', compose_text)
        self.assertIn(
            '        OPENCLAW_INSTALL_DOCKER_CLI: "${OPENCLAW_INSTALL_DOCKER_CLI:-}"',
            compose_text,
        )
        self.assertIn('    user: "root"', compose_text)
        self.assertIn("    cap_drop:", compose_text)
        self.assertIn("      - ALL", compose_text)
        expected_entrypoint = (
            '    entrypoint: [' + ", ".join(f'"{part}"' for part in OPENCLAW_HELPER_ENTRYPOINT) + "]"
        )
        self.assertIn(
            expected_entrypoint,
            compose_text,
        )
        self.assertIn("    security_opt:", compose_text)
        self.assertIn("      - no-new-privileges:true", compose_text)
        self.assertIn("    read_only: true", compose_text)
        self.assertIn(f'      - "${{OPENCLAW_TMPFS:-{DEFAULT_OPENCLAW_TMPFS}}}"', compose_text)
        self.assertIn(
            f'    pids_limit: "${{OPENCLAW_PIDS_LIMIT:-{DEFAULT_OPENCLAW_PIDS_LIMIT}}}"',
            compose_text,
        )
        self.assertIn(
            f'        soft: "${{OPENCLAW_NOFILE_SOFT:-{DEFAULT_OPENCLAW_NOFILE_SOFT}}}"',
            compose_text,
        )
        self.assertIn(
            f'        hard: "${{OPENCLAW_NOFILE_HARD:-{DEFAULT_OPENCLAW_NOFILE_HARD}}}"',
            compose_text,
        )
        self.assertIn(
            f'      nproc: "${{OPENCLAW_NPROC:-{DEFAULT_OPENCLAW_NPROC}}}"',
            compose_text,
        )
        self.assertIn(
            f'${{OPENCLAW_GATEWAY_HOST_BIND:-{DEFAULT_OPENCLAW_GATEWAY_HOST_BIND}}}',
            compose_text,
        )
        self.assertIn(
            f'${{OPENCLAW_BRIDGE_HOST_BIND:-{DEFAULT_OPENCLAW_BRIDGE_HOST_BIND}}}',
            compose_text,
        )
        self.assertIn('HOME: "/root"', compose_text)
        self.assertIn('NPM_CONFIG_CACHE: "/tmp/.npm"', compose_text)
        self.assertIn('XDG_CACHE_HOME: "/tmp/.cache"', compose_text)
        self.assertIn('OPENCLAW_STATE_DIR: "/opt/openclaw"', compose_text)
        self.assertIn('OPENCLAW_CONFIG_PATH: "/opt/openclaw/openclaw.json"', compose_text)
        self.assertIn('        "sh",', compose_text)
        self.assertIn('        "-lc",', compose_text)
        self.assertIn(
            "run_clawhub install 'freeride' --workdir '/opt/openclaw/workspace' --force --no-input",
            compose_text,
        )
        self.assertIn(
            "mv '/opt/openclaw/workspace/skills/freeride' '/opt/openclaw/workspace/skills/free-ride'",
            compose_text,
        )
        self.assertNotIn("@openclaw/clawhub", compose_text)

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
        self.assertEqual(all_bots_env_filename(), ".all-bots.env")

    def test_render_all_bots_env_file_preserves_custom_values(self) -> None:
        env_text = render_all_bots_env_file(
            existing_values={
                "OPENCLAW_GATEWAY_TOKEN": "gateway-token",
                "TELEGRAM_BOT_TOKEN": "telegram-secret",
            }
        )

        self.assertIn("OPENCLAW_GATEWAY_TOKEN=gateway-token", env_text)
        self.assertIn("# Preserved custom values", env_text)
        self.assertIn("TELEGRAM_BOT_TOKEN=telegram-secret", env_text)

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
        self.assertIn(
            f"OPENCLAW_GATEWAY_HOST_BIND={DEFAULT_OPENCLAW_GATEWAY_HOST_BIND}",
            env_text,
        )
        self.assertIn(
            f"OPENCLAW_BRIDGE_HOST_BIND={DEFAULT_OPENCLAW_BRIDGE_HOST_BIND}",
            env_text,
        )
        self.assertIn(f"OPENCLAW_TMPFS={DEFAULT_OPENCLAW_TMPFS}", env_text)

    def test_env_file_includes_security_advisories_for_risky_runtime_overrides(self) -> None:
        manifest, _ = load_manifest(FIXTURES / "example.openclawenv.toml")

        env_text = render_env_file(
            manifest,
            "openclawenv/ops-agent:1.2.3",
            existing_values={
                "OPENCLAW_GATEWAY_HOST_BIND": "0.0.0.0",
                "OPENCLAW_ALLOW_INSECURE_PRIVATE_WS": "1",
            },
        )

        self.assertIn("# Security advisories for explicit runtime overrides", env_text)
        self.assertIn("# WARNING: OPENCLAW_GATEWAY_HOST_BIND exposes the gateway", env_text)
        self.assertIn("# WARNING: OPENCLAW_ALLOW_INSECURE_PRIVATE_WS is enabled", env_text)

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
        self.assertIn('      - "./.all-bots.env"', compose_text)
        self.assertIn("  bot-operations-agent:", compose_text)
        self.assertIn("  bot-analytics-agent:", compose_text)
        self.assertIn('      context: "./operations-agent"', compose_text)
        self.assertIn('      context: "./analytics-agent"', compose_text)
        self.assertIn('      - "./operations-agent/.operations-agent.env"', compose_text)
        self.assertIn('      - "./analytics-agent/.analytics-agent.env"', compose_text)
        self.assertEqual(compose_text.count('      - "./.all-bots.env"'), 3)
        self.assertIn('    image: "${OPENCLAW_GATEWAY_IMAGE:-ghcr.io/openclaw/openclaw:latest}"', compose_text)
        self.assertIn('    user: "root"', compose_text)
        self.assertIn('      HOME: "/opt/openclaw"', compose_text)
        self.assertIn('      NPM_CONFIG_CACHE: "/tmp/.npm"', compose_text)
        self.assertIn('      XDG_CACHE_HOME: "/tmp/.cache"', compose_text)
        self.assertIn('      OPENCLAW_STATE_DIR: "/opt/openclaw/.openclaw"', compose_text)
        self.assertIn('      OPENCLAW_CONFIG_PATH: "/opt/openclaw/.openclaw/openclaw.json"', compose_text)
        self.assertIn('      - "./.all-bots:/opt/openclaw"', compose_text)
        self.assertIn('      - ALL', compose_text)
        self.assertIn('    read_only: true', compose_text)
        self.assertIn(
            "run_clawhub install 'freeride' --workdir '/opt/openclaw/workspace/operations-agent' --force --no-input",
            compose_text,
        )
        self.assertIn(
            "run_clawhub install 'freeride' --workdir '/opt/openclaw/workspace/analytics-agent' --force --no-input",
            compose_text,
        )
        self.assertIn(
            "mv '/opt/openclaw/workspace/operations-agent/skills/freeride' '/opt/openclaw/workspace/operations-agent/skills/free-ride'",
            compose_text,
        )
        self.assertNotIn("@openclaw/clawhub", compose_text)

