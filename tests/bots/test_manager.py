from __future__ import annotations

import io
import shutil
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from openenv.bots import manager as bot_manager
from openenv.bots.manager import (
    BotAnswers,
    DocumentImprovementResult,
    _bot_from_selection,
    _ensure_bot_agent_documents_materialized,
    _hydrate_skill_from_snapshot,
    _load_running_bot,
    _normalize_language,
    _prompt_csv,
    _prompt_csv_with_default,
    _prompt_nonempty,
    _render_tools_markdown,
    _require_language,
    _resolve_openrouter_api_key,
    _running_bot_from_selection,
    _select_language,
    _unique_paths,
    create_bot,
    create_skill_snapshot,
    delete_bot,
    discover_bots,
    discover_running_bots,
    generate_all_bots_stack,
    generate_bot_artifacts,
    improve_bot_markdown_documents,
    interactive_menu,
    load_bot,
    update_bot,
)
from openenv.core.errors import OpenEnvError
from openenv.core.models import SkillConfig
from openenv.core.skills import MANDATORY_SKILL_SOURCES
from openenv.docker.runtime import CapturedSkill
from openenv.cli import main
from openenv.manifests.lockfile import build_lockfile as build_lockfile_for_test
from openenv.manifests.writer import render_manifest


TESTS_ROOT = Path(__file__).resolve().parents[1]
TEMP_ROOT = TESTS_ROOT / "_tmp"
TEMP_ROOT.mkdir(exist_ok=True)
PINNED_IMAGE = (
    "python:3.12-slim@sha256:1111111111111111111111111111111111111111111111111111111111111111"
)


class BotManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.work_dir = TEMP_ROOT / "bot-manager"
        if self.work_dir.exists():
            shutil.rmtree(self.work_dir, ignore_errors=True)
        self.work_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.work_dir, ignore_errors=True)

    def test_create_and_discover_bot(self) -> None:
        record = create_bot(
            self.work_dir,
            BotAnswers(
                display_name="Publisher Bot",
                role="Publikacja i dystrybucja tresci",
                skill_sources=["kralsamwise/kdp-publisher"],
                system_packages=["ffmpeg"],
                python_packages=["requests==2.32.3"],
                node_packages=["typescript@5.8.3"],
                secret_names=["OPENAI_API_KEY", "KDP_PASSWORD"],
                websites=["https://kdp.amazon.com"],
                databases=["postgres://publisher-db"],
                access_notes=["Dostep tylko do konta wydawniczego."],
            ),
        )

        self.assertTrue(record.manifest_path.exists())
        text = record.manifest_path.read_text(encoding="utf-8")
        self.assertIn('source = "kralsamwise/kdp-publisher"', text)
        for source in MANDATORY_SKILL_SOURCES:
            self.assertIn(f'source = "{source}"', text)
        self.assertIn("[access]", text)
        self.assertNotIn("[[runtime.secret_refs]]", text)
        self.assertIn('node_packages = ["typescript@5.8.3"]', text)
        self.assertIn('user = "root"', text)
        self.assertIn('agents_md = "AGENTS.md"', text)
        self.assertIn('soul_md = "SOUL.md"', text)
        self.assertIn('user_md = "USER.md"', text)
        self.assertIn('identity_md = "IDENTITY.md"', text)
        self.assertIn('tools_md = "TOOLS.md"', text)
        self.assertIn('memory_seed = "memory.md"', text)
        self.assertIn('mode = "off"', text)
        self.assertNotIn("# Agent Contract", text)
        self.assertTrue((self.work_dir / "bots" / "publisher-bot" / "AGENTS.md").exists())
        self.assertTrue((self.work_dir / "bots" / "publisher-bot" / "SOUL.md").exists())
        self.assertTrue((self.work_dir / "bots" / "publisher-bot" / "USER.md").exists())
        self.assertTrue((self.work_dir / "bots" / "publisher-bot" / "IDENTITY.md").exists())
        self.assertTrue((self.work_dir / "bots" / "publisher-bot" / "TOOLS.md").exists())
        self.assertTrue((self.work_dir / "bots" / "publisher-bot" / "memory.md").exists())
        sidecar_env = (self.work_dir / "bots" / "publisher-bot" / ".env").read_text(
            encoding="utf-8"
        )
        self.assertIn("OPENAI_API_KEY=", sidecar_env)
        self.assertIn("KDP_PASSWORD=", sidecar_env)

        discovered = discover_bots(self.work_dir)
        self.assertEqual(len(discovered), 1)
        self.assertEqual(discovered[0].display_name, "Publisher Bot")
        self.assertEqual(discovered[0].role, "Publikacja i dystrybucja tresci")
        self.assertEqual(
            [
                skill.source
                for skill in discovered[0].manifest.skills[
                    : len(MANDATORY_SKILL_SOURCES)
                ]
            ],
            list(MANDATORY_SKILL_SOURCES),
        )
        self.assertEqual(
            [secret.name for secret in discovered[0].manifest.runtime.secret_refs],
            ["OPENAI_API_KEY", "KDP_PASSWORD"],
        )

    def test_update_bot_can_rename_and_replace_manifest_data(self) -> None:
        create_bot(
            self.work_dir,
            BotAnswers(
                display_name="Publisher Bot",
                role="Publikacja tresci",
                skill_sources=["kralsamwise/kdp-publisher"],
                system_packages=["ffmpeg"],
                python_packages=["requests==2.32.3"],
                node_packages=["typescript@5.8.3"],
                secret_names=["OPENAI_API_KEY"],
                websites=["https://kdp.amazon.com"],
                databases=["postgres://publisher-db"],
                access_notes=["Read only"],
            ),
        )
        env_path = self.work_dir / "bots" / "publisher-bot" / ".env"
        env_path.write_text(
            "# Secret references for Publisher Bot\n"
            "# Keys declared here are synthesized into runtime.secret_refs for the bot.\n\n"
            "OPENAI_API_KEY=already-set\n",
            encoding="utf-8",
        )

        updated = update_bot(
            self.work_dir,
            "publisher-bot",
            BotAnswers(
                display_name="Analytics Bot",
                role="Analiza i raportowanie",
                skill_sources=["kralsamwise/kdp-publisher", "acme/report-writer"],
                system_packages=["jq"],
                python_packages=["pandas==2.2.3"],
                node_packages=["tsx@4.19.3"],
                secret_names=["OPENAI_API_KEY", "ANALYTICS_TOKEN"],
                websites=["https://analytics.example.com"],
                databases=["postgres://analytics-db"],
                access_notes=["Write access only in reporting schema"],
            ),
        )

        self.assertEqual(updated.slug, "analytics-bot")
        self.assertFalse((self.work_dir / "bots" / "publisher-bot").exists())
        self.assertTrue((self.work_dir / "bots" / "analytics-bot").exists())

        text = updated.manifest_path.read_text(encoding="utf-8")
        self.assertIn('agent_name = "Analytics Bot"', text)
        self.assertIn('source = "acme/report-writer"', text)
        self.assertIn('"jq"', text)
        self.assertIn('"pandas==2.2.3"', text)
        self.assertNotIn("[[runtime.secret_refs]]", text)
        self.assertIn('node_packages = ["tsx@4.19.3"]', text)
        self.assertIn('agents_md = "AGENTS.md"', text)
        self.assertTrue((self.work_dir / "bots" / "analytics-bot" / "AGENTS.md").exists())
        self.assertTrue((self.work_dir / "bots" / "analytics-bot" / "memory.md").exists())

        updated_env = (self.work_dir / "bots" / "analytics-bot" / ".env").read_text(
            encoding="utf-8"
        )
        self.assertIn("OPENAI_API_KEY=already-set", updated_env)
        self.assertIn("ANALYTICS_TOKEN=", updated_env)

    def test_update_bot_preserves_manual_channel_config(self) -> None:
        record = create_bot(
            self.work_dir,
            BotAnswers(
                display_name="Publisher Bot",
                role="Publikacja tresci",
                skill_sources=[],
                system_packages=[],
                python_packages=[],
                node_packages=[],
                secret_names=[],
                websites=[],
                databases=[],
                access_notes=[],
            ),
        )
        manifest = record.manifest
        manifest.openclaw.channels = {
            "telegram": {
                "enabled": True,
                "allowFrom": ["123456"],
            }
        }
        record.manifest_path.write_text(render_manifest(manifest), encoding="utf-8")

        updated = update_bot(
            self.work_dir,
            "publisher-bot",
            BotAnswers(
                display_name="Publisher Bot",
                role="Publikacja i analityka",
                skill_sources=[],
                system_packages=[],
                python_packages=[],
                node_packages=[],
                secret_names=[],
                websites=[],
                databases=[],
                access_notes=[],
            ),
        )

        self.assertEqual(
            updated.manifest.openclaw.channels,
            {"telegram": {"enabled": True, "allowFrom": ["123456"]}},
        )

    def test_delete_bot_removes_directory(self) -> None:
        record = create_bot(
            self.work_dir,
            BotAnswers(
                display_name="Cleanup Bot",
                role="Czyszczenie danych",
                skill_sources=[],
                system_packages=[],
                python_packages=[],
                node_packages=[],
                secret_names=[],
                websites=[],
                databases=[],
                access_notes=[],
            ),
        )
        self.assertEqual(
            [skill.source for skill in record.manifest.skills],
            list(MANDATORY_SKILL_SOURCES),
        )

        delete_bot(self.work_dir, "cleanup-bot")

        self.assertEqual(discover_bots(self.work_dir), [])

    def test_generate_bot_artifacts_writes_bundle(self) -> None:
        create_bot(
            self.work_dir,
            BotAnswers(
                display_name="Bundle Bot",
                role="Generowanie artefaktow",
                skill_sources=["kralsamwise/kdp-publisher"],
                system_packages=[],
                python_packages=["requests==2.32.3"],
                node_packages=["typescript@5.8.3"],
                secret_names=["OPENAI_API_KEY"],
                websites=[],
                databases=[],
                access_notes=[],
            ),
        )

        with patch(
            "openenv.bots.manager.build_lockfile",
            side_effect=self._build_stub_lockfile,
        ):
            artifacts = generate_bot_artifacts(self.work_dir, "bundle-bot")

        self.assertTrue(artifacts.lock_path.exists())
        self.assertTrue(artifacts.dockerfile_path.exists())
        self.assertTrue(artifacts.compose_path.exists())
        self.assertTrue(artifacts.env_path.exists())
        self.assertEqual(artifacts.image_tag, "openclawenv/bundle-bot:0.1.0")
        self.assertIn(
            "# syntax=docker/dockerfile:1",
            artifacts.dockerfile_path.read_text(encoding="utf-8"),
        )
        self.assertIn(
            "docker-compose-bundle-bot.yml",
            str(artifacts.compose_path),
        )
        self.assertIn(
            "# OpenClaw runtime and secrets for Bundle Bot",
            artifacts.env_path.read_text(encoding="utf-8"),
        )
        self.assertIn(
            "OPENAI_API_KEY=",
            artifacts.env_path.read_text(encoding="utf-8"),
        )
        self.assertTrue((artifacts.bot.manifest_path.parent / ".openclaw" / "openclaw.json").exists())
        self.assertTrue((artifacts.bot.manifest_path.parent / "workspace" / "AGENTS.md").exists())
        openclaw_config_text = (
            artifacts.bot.manifest_path.parent / ".openclaw" / "openclaw.json"
        ).read_text(encoding="utf-8")
        self.assertIn('"mode": "off"', openclaw_config_text)
        self.assertNotIn('"backend": "docker"', openclaw_config_text)

    def test_generate_bot_artifacts_preserves_installed_catalog_skill_content(self) -> None:
        create_bot(
            self.work_dir,
            BotAnswers(
                display_name="Bundle Bot",
                role="Generowanie artefaktow",
                skill_sources=[],
                system_packages=[],
                python_packages=[],
                node_packages=[],
                secret_names=[],
                websites=[],
                databases=[],
                access_notes=[],
            ),
        )

        with patch(
            "openenv.bots.manager.build_lockfile",
            side_effect=self._build_stub_lockfile,
        ):
            artifacts = generate_bot_artifacts(self.work_dir, "bundle-bot")

        skill_path = (
            artifacts.bot.manifest_path.parent / "workspace" / "skills" / "free-ride" / "SKILL.md"
        )
        skill_path.write_text("Real installed free-ride skill\n", encoding="utf-8")

        with patch(
            "openenv.bots.manager.build_lockfile",
            side_effect=self._build_stub_lockfile,
        ):
            generate_bot_artifacts(self.work_dir, "bundle-bot")

        self.assertEqual(
            skill_path.read_text(encoding="utf-8"),
            "Real installed free-ride skill\n",
        )

    def test_generate_all_bots_stack_writes_shared_compose(self) -> None:
        create_bot(
            self.work_dir,
            BotAnswers(
                display_name="Bundle Bot",
                role="Generowanie artefaktow",
                skill_sources=["kralsamwise/kdp-publisher"],
                system_packages=[],
                python_packages=["requests==2.32.3"],
                node_packages=["typescript@5.8.3"],
                secret_names=["OPENAI_API_KEY"],
                websites=[],
                databases=[],
                access_notes=[],
            ),
        )
        create_bot(
            self.work_dir,
            BotAnswers(
                display_name="Docs Bot",
                role="Improving documentation",
                skill_sources=[],
                system_packages=[],
                python_packages=[],
                node_packages=[],
                secret_names=[],
                websites=[],
                databases=[],
                access_notes=[],
            ),
        )

        with patch(
            "openenv.bots.manager.build_lockfile",
            side_effect=self._build_stub_lockfile,
        ):
            stack = generate_all_bots_stack(self.work_dir)

        self.assertEqual(len(stack.bot_artifacts), 2)
        self.assertTrue(stack.stack_path.exists())
        stack_text = stack.stack_path.read_text(encoding="utf-8")
        shared_env_path = self.work_dir / "bots" / ".all-bots.env"
        shared_config_path = self.work_dir / "bots" / ".all-bots" / ".openclaw" / "openclaw.json"
        self.assertIn("openclaw-gateway:", stack_text)
        self.assertEqual(stack_text.count("openclaw-gateway:"), 1)
        self.assertIn("bot-bundle-bot:", stack_text)
        self.assertIn("bot-docs-bot:", stack_text)
        self.assertIn('context: "./bundle-bot"', stack_text)
        self.assertIn('context: "./docs-bot"', stack_text)
        self.assertIn('      - "./.all-bots.env"', stack_text)
        self.assertIn('HOME: "/opt/openclaw"', stack_text)
        self.assertIn('OPENCLAW_CONFIG_PATH: "/opt/openclaw/.openclaw/openclaw.json"', stack_text)
        self.assertIn('OPENCLAW_STATE_DIR: "/opt/openclaw/.openclaw"', stack_text)
        self.assertIn('"./.all-bots:/opt/openclaw"', stack_text)
        self.assertTrue(shared_env_path.exists())
        self.assertIn("OPENCLAW_GATEWAY_TOKEN=", shared_env_path.read_text(encoding="utf-8"))
        self.assertTrue(shared_config_path.exists())
        shared_config_text = shared_config_path.read_text(encoding="utf-8")
        self.assertIn('"token": "${OPENCLAW_GATEWAY_TOKEN}"', shared_config_text)
        self.assertIn('"mode": "off"', shared_config_text)
        self.assertNotIn('"backend": "docker"', shared_config_text)
        self.assertIn('"/opt/openclaw/workspace/bundle-bot"', shared_config_text)
        self.assertIn('"/opt/openclaw/workspace/docs-bot"', shared_config_text)
        self.assertTrue(
            (self.work_dir / "bots" / ".all-bots" / "workspace" / "bundle-bot" / "AGENTS.md").exists()
        )
        self.assertTrue(
            (self.work_dir / "bots" / ".all-bots" / "workspace" / "docs-bot" / "AGENTS.md").exists()
        )

    def test_generate_all_bots_stack_preserves_shared_state_and_seeds_agent_auth(self) -> None:
        create_bot(
            self.work_dir,
            BotAnswers(
                display_name="Bundle Bot",
                role="Generowanie artefaktow",
                skill_sources=[],
                system_packages=[],
                python_packages=[],
                node_packages=[],
                secret_names=[],
                websites=[],
                databases=[],
                access_notes=[],
            ),
        )
        shared_root = self.work_dir / "bots" / ".all-bots"
        shared_main_agent_dir = shared_root / ".openclaw" / "agents" / "main" / "agent"
        shared_main_agent_dir.mkdir(parents=True, exist_ok=True)
        auth_payload = (
            '{"version":1,"profiles":{"anthropic:default":'
            '{"type":"api_key","provider":"anthropic","key":"test-key"}}}\n'
        )
        models_payload = '{"version":1,"providers":{}}\n'
        preserved_state_path = shared_root / ".openclaw" / "exec-approvals.json"
        preserved_workspace_path = shared_root / "workspace" / "bundle-bot" / "notes.txt"
        (shared_main_agent_dir / "auth-profiles.json").write_text(auth_payload, encoding="utf-8")
        (shared_main_agent_dir / "models.json").write_text(models_payload, encoding="utf-8")
        preserved_state_path.parent.mkdir(parents=True, exist_ok=True)
        preserved_state_path.write_text('{"preserve":true}\n', encoding="utf-8")
        preserved_workspace_path.parent.mkdir(parents=True, exist_ok=True)
        preserved_workspace_path.write_text("keep me\n", encoding="utf-8")

        with patch(
            "openenv.bots.manager.build_lockfile",
            side_effect=self._build_stub_lockfile,
        ):
            generate_all_bots_stack(self.work_dir)

        agent_root = (
            self.work_dir
            / "bots"
            / ".all-bots"
            / ".openclaw"
            / "agents"
            / "bundle-bot"
            / "agent"
        )
        self.assertEqual(
            (agent_root / "auth-profiles.json").read_text(encoding="utf-8"),
            auth_payload,
        )
        self.assertEqual(
            (agent_root / "models.json").read_text(encoding="utf-8"),
            models_payload,
        )
        self.assertEqual(
            preserved_state_path.read_text(encoding="utf-8"),
            '{"preserve":true}\n',
        )
        self.assertEqual(
            preserved_workspace_path.read_text(encoding="utf-8"),
            "keep me\n",
        )

    def test_generate_all_bots_stack_preserves_installed_shared_catalog_skill_content(self) -> None:
        create_bot(
            self.work_dir,
            BotAnswers(
                display_name="Bundle Bot",
                role="Generowanie artefaktow",
                skill_sources=[],
                system_packages=[],
                python_packages=[],
                node_packages=[],
                secret_names=[],
                websites=[],
                databases=[],
                access_notes=[],
            ),
        )

        with patch(
            "openenv.bots.manager.build_lockfile",
            side_effect=self._build_stub_lockfile,
        ):
            generate_all_bots_stack(self.work_dir)

        shared_skill_path = (
            self.work_dir
            / "bots"
            / ".all-bots"
            / "workspace"
            / "bundle-bot"
            / "skills"
            / "free-ride"
            / "SKILL.md"
        )
        shared_skill_path.write_text("Real installed shared free-ride skill\n", encoding="utf-8")

        with patch(
            "openenv.bots.manager.build_lockfile",
            side_effect=self._build_stub_lockfile,
        ):
            generate_all_bots_stack(self.work_dir)

        self.assertEqual(
            shared_skill_path.read_text(encoding="utf-8"),
            "Real installed shared free-ride skill\n",
        )

    def test_generate_all_bots_stack_merges_shared_channel_config(self) -> None:
        first = create_bot(
            self.work_dir,
            BotAnswers(
                display_name="Bundle Bot",
                role="Generowanie artefaktow",
                skill_sources=[],
                system_packages=[],
                python_packages=[],
                node_packages=[],
                secret_names=[],
                websites=[],
                databases=[],
                access_notes=[],
            ),
        )
        second = create_bot(
            self.work_dir,
            BotAnswers(
                display_name="Docs Bot",
                role="Dokumentacja",
                skill_sources=[],
                system_packages=[],
                python_packages=[],
                node_packages=[],
                secret_names=[],
                websites=[],
                databases=[],
                access_notes=[],
            ),
        )
        for record in (first, second):
            manifest = record.manifest
            manifest.openclaw.channels = {
                "telegram": {
                    "enabled": True,
                    "allowFrom": ["123456"],
                }
            }
            record.manifest_path.write_text(render_manifest(manifest), encoding="utf-8")

        with patch(
            "openenv.bots.manager.build_lockfile",
            side_effect=self._build_stub_lockfile,
        ):
            stack = generate_all_bots_stack(self.work_dir)

        shared_config_text = (
            self.work_dir / "bots" / ".all-bots" / ".openclaw" / "openclaw.json"
        ).read_text(encoding="utf-8")
        self.assertEqual(len(stack.bot_artifacts), 2)
        self.assertIn('"channels"', shared_config_text)
        self.assertIn('"telegram"', shared_config_text)
        self.assertIn('"allowFrom"', shared_config_text)

    def test_generate_all_bots_stack_copies_channel_env_placeholders_to_shared_env(self) -> None:
        record = create_bot(
            self.work_dir,
            BotAnswers(
                display_name="Telegram Bot",
                role="Obsluga Telegrama",
                skill_sources=[],
                system_packages=[],
                python_packages=[],
                node_packages=[],
                secret_names=["TELEGRAM_BOT_TOKEN"],
                websites=[],
                databases=[],
                access_notes=[],
            ),
        )
        manifest = record.manifest
        manifest.runtime.secret_refs = []
        manifest.openclaw.channels = {
            "telegram": {
                "enabled": True,
                "botToken": "${TELEGRAM_BOT_TOKEN}",
            }
        }
        record.manifest_path.write_text(render_manifest(manifest), encoding="utf-8")
        sidecar_env_path = self.work_dir / "bots" / "telegram-bot" / ".env"
        sidecar_env_path.write_text(
            sidecar_env_path.read_text(encoding="utf-8").replace(
                "TELEGRAM_BOT_TOKEN=",
                "TELEGRAM_BOT_TOKEN=telegram-secret",
            ),
            encoding="utf-8",
        )

        with patch(
            "openenv.bots.manager.build_lockfile",
            side_effect=self._build_stub_lockfile,
        ):
            generate_all_bots_stack(self.work_dir)

        shared_env_text = (
            self.work_dir / "bots" / ".all-bots.env"
        ).read_text(encoding="utf-8")
        shared_config_text = (
            self.work_dir / "bots" / ".all-bots" / ".openclaw" / "openclaw.json"
        ).read_text(encoding="utf-8")

        self.assertIn("TELEGRAM_BOT_TOKEN=telegram-secret", shared_env_text)
        self.assertIn('"botToken": "${TELEGRAM_BOT_TOKEN}"', shared_config_text)

    def test_interactive_menu_adds_edits_and_deletes_bot(self) -> None:
        answers = iter(
            [
                "pl",
                "2",
                "Menu Bot",
                "Obsluga publikacji",
                "kralsamwise/kdp-publisher",
                "imagemagick",
                "",
                "typescript@5.8.3",
                "OPENAI_API_KEY",
                "https://example.com",
                "publisher-db",
                "Dostep tylko do produkcji",
                "3",
                "1",
                "Menu Bot 2",
                "Obsluga raportowania",
                "kralsamwise/kdp-publisher, acme/report-writer",
                "jq",
                "pandas==2.2.3",
                "tsx@4.19.3",
                "OPENAI_API_KEY, REPORT_TOKEN",
                "https://reports.example.com",
                "reporting-db",
                "Tylko raporty",
                "4",
                "1",
                "t",
                "6",
            ]
        )
        stdout = io.StringIO()
        with patch("builtins.input", side_effect=lambda _: next(answers)):
            with redirect_stdout(stdout):
                exit_code = interactive_menu(self.work_dir)

        self.assertEqual(exit_code, 0)
        output = stdout.getvalue()
        self.assertIn("Utworzono bota `Menu Bot`", output)
        self.assertIn("Zaktualizowano bota `Menu Bot 2`", output)
        self.assertIn("Usunieto bota `Menu Bot 2`.", output)
        self.assertEqual(discover_bots(self.work_dir), [])

    def test_interactive_list_can_generate_artifacts_for_selected_bot(self) -> None:
        create_bot(
            self.work_dir,
            BotAnswers(
                display_name="Export Bot",
                role="Eksport artefaktow",
                skill_sources=["kralsamwise/kdp-publisher"],
                system_packages=[],
                python_packages=[],
                node_packages=["typescript@5.8.3"],
                secret_names=["OPENAI_API_KEY"],
                websites=[],
                databases=[],
                access_notes=[],
            ),
        )

        answers = iter(["en", "1", "1", "1", "6"])
        stdout = io.StringIO()
        with patch(
            "openenv.bots.manager.build_lockfile",
            side_effect=self._build_stub_lockfile,
        ):
            with patch("builtins.input", side_effect=lambda _: next(answers)):
                with redirect_stdout(stdout):
                    exit_code = interactive_menu(self.work_dir)

        self.assertEqual(exit_code, 0)
        output = stdout.getvalue()
        self.assertIn("OpenClawenv - Interactive menu", output)
        self.assertIn("Registered bots:", output)
        self.assertIn("Generated Dockerfile:", output)
        self.assertIn("Generated docker-compose:", output)
        self.assertTrue((self.work_dir / "bots" / "export-bot" / "Dockerfile").exists())
        self.assertTrue(
            (self.work_dir / "bots" / "export-bot" / "docker-compose-export-bot.yml").exists()
        )

    def test_interactive_list_can_generate_shared_stack_for_all_bots(self) -> None:
        create_bot(
            self.work_dir,
            BotAnswers(
                display_name="Export Bot",
                role="Eksport artefaktow",
                skill_sources=["kralsamwise/kdp-publisher"],
                system_packages=[],
                python_packages=[],
                node_packages=["typescript@5.8.3"],
                secret_names=["OPENAI_API_KEY"],
                websites=[],
                databases=[],
                access_notes=[],
            ),
        )
        create_bot(
            self.work_dir,
            BotAnswers(
                display_name="Docs Bot",
                role="Improving documentation",
                skill_sources=[],
                system_packages=[],
                python_packages=[],
                node_packages=[],
                secret_names=[],
                websites=[],
                databases=[],
                access_notes=[],
            ),
        )

        answers = iter(["en", "1", "a", "6"])
        stdout = io.StringIO()
        with patch(
            "openenv.bots.manager.build_lockfile",
            side_effect=self._build_stub_lockfile,
        ):
            with patch("builtins.input", side_effect=lambda _: next(answers)):
                with redirect_stdout(stdout):
                    exit_code = interactive_menu(self.work_dir)

        self.assertEqual(exit_code, 0)
        output = stdout.getvalue()
        self.assertIn("A. Generate a shared stack for all bots", output)
        self.assertIn("Generated shared stack:", output)
        self.assertTrue((self.work_dir / "bots" / "all-bots-compose.yml").exists())

    def test_improve_bot_markdown_documents_updates_files(self) -> None:
        create_bot(
            self.work_dir,
            BotAnswers(
                display_name="Docs Bot",
                role="Improving documentation",
                skill_sources=["kralsamwise/kdp-publisher"],
                system_packages=[],
                python_packages=[],
                node_packages=[],
                secret_names=[],
                websites=[],
                databases=[],
                access_notes=[],
            ),
        )

        def fake_openrouter_call(**kwargs):
            kwargs["write_document"]("AGENTS.md", "# Updated contract\n")
            kwargs["write_document"]("memory.md", "Keep context fresh.\n")
            return "Updated two files."

        with patch(
            "openenv.bots.manager.improve_markdown_documents_with_openrouter",
            side_effect=fake_openrouter_call,
        ):
            result = improve_bot_markdown_documents(
                self.work_dir,
                "docs-bot",
                instruction="Refresh the docs.",
                api_key="test-key",
            )

        self.assertEqual(result.summary, "Updated two files.")
        self.assertEqual(len(result.updated_paths), 2)
        self.assertEqual(
            (self.work_dir / "bots" / "docs-bot" / "AGENTS.md").read_text(
                encoding="utf-8"
            ),
            "# Updated contract\n",
        )
        self.assertEqual(
            (self.work_dir / "bots" / "docs-bot" / "memory.md").read_text(
                encoding="utf-8"
            ),
            "Keep context fresh.\n",
        )

    def test_interactive_list_can_improve_docs_and_create_root_env_key(self) -> None:
        create_bot(
            self.work_dir,
            BotAnswers(
                display_name="Docs Bot",
                role="Improving documentation",
                skill_sources=["kralsamwise/kdp-publisher"],
                system_packages=[],
                python_packages=[],
                node_packages=[],
                secret_names=[],
                websites=[],
                databases=[],
                access_notes=[],
            ),
        )

        answers = iter(["en", "1", "1", "2", "", "6"])
        stdout = io.StringIO()
        with patch(
            "openenv.bots.manager.improve_bot_markdown_documents",
            return_value=DocumentImprovementResult(
                bot=load_bot(self.work_dir, "docs-bot"),
                summary="Updated docs.",
                updated_paths=[self.work_dir / "bots" / "docs-bot" / "AGENTS.md"],
            ),
        ) as improve_docs:
            with patch("openenv.bots.manager.getpass", return_value="root-openrouter-key"):
                with patch("builtins.input", side_effect=lambda _: next(answers)):
                    with redirect_stdout(stdout):
                        exit_code = interactive_menu(self.work_dir)

        self.assertEqual(exit_code, 0)
        improve_docs.assert_called_once()
        self.assertEqual(improve_docs.call_args.kwargs["api_key"], "root-openrouter-key")
        root_env = (self.work_dir / ".env").read_text(encoding="utf-8")
        self.assertIn("OPENROUTER_API_KEY=root-openrouter-key", root_env)
        output = stdout.getvalue()
        self.assertIn("OPENROUTER_API_KEY was not found", output)
        self.assertIn("Saved OPENROUTER_API_KEY", output)
        self.assertIn("OpenRouter finished improving the documents", output)

    def test_discover_running_bots_returns_only_running_managed_bots(self) -> None:
        create_bot(
            self.work_dir,
            BotAnswers(
                display_name="Running Bot",
                role="Monitoring runtime",
                skill_sources=[],
                system_packages=[],
                python_packages=[],
                node_packages=[],
                secret_names=[],
                websites=[],
                databases=[],
                access_notes=[],
            ),
        )
        create_bot(
            self.work_dir,
            BotAnswers(
                display_name="Stopped Bot",
                role="Idle runtime",
                skill_sources=[],
                system_packages=[],
                python_packages=[],
                node_packages=[],
                secret_names=[],
                websites=[],
                databases=[],
                access_notes=[],
            ),
        )
        with patch(
            "openenv.bots.manager.build_lockfile",
            side_effect=self._build_stub_lockfile,
        ):
            generate_bot_artifacts(self.work_dir, "running-bot")
            generate_bot_artifacts(self.work_dir, "stopped-bot")

        with patch(
            "openenv.bots.manager.list_running_container_names",
            return_value={"running-bot-openclaw-gateway"},
        ):
            running_bots = discover_running_bots(self.work_dir)

        self.assertEqual([bot.slug for bot in running_bots], ["running-bot"])

    def test_create_skill_snapshot_adds_new_skill_and_updates_lockfile(self) -> None:
        create_bot(
            self.work_dir,
            BotAnswers(
                display_name="Snapshot Bot",
                role="Runtime snapshotting",
                skill_sources=[],
                system_packages=[],
                python_packages=[],
                node_packages=[],
                secret_names=[],
                websites=[],
                databases=[],
                access_notes=[],
            ),
        )
        with patch(
            "openenv.bots.manager.build_lockfile",
            side_effect=self._build_stub_lockfile,
        ):
            generate_bot_artifacts(self.work_dir, "snapshot-bot")

        with patch(
            "openenv.bots.manager.list_running_container_names",
            return_value={"snapshot-bot-openclaw-gateway"},
        ):
            with patch(
                "openenv.bots.manager.snapshot_installed_skills",
                return_value=[
                    CapturedSkill(
                        name="extra-skill",
                        description="Captured at runtime",
                        content=(
                            "---\n"
                            "name: extra-skill\n"
                            "description: Captured at runtime\n"
                            "source: acme/extra-skill\n"
                            "---\n"
                        ),
                        source="acme/extra-skill",
                        assets={"templates/note.md": "# Snapshot\n"},
                    )
                ],
            ):
                result = create_skill_snapshot(self.work_dir, "snapshot-bot")

        self.assertEqual(result.added_skill_names, ["extra-skill"])
        self.assertIsNotNone(result.lock_path)
        manifest_text = (self.work_dir / "bots" / "snapshot-bot" / "openclawenv.toml").read_text(
            encoding="utf-8"
        )
        self.assertIn('name = "extra-skill"', manifest_text)
        self.assertIn('source = "acme/extra-skill"', manifest_text)
        self.assertTrue((self.work_dir / "bots" / "snapshot-bot" / "openclawenv.lock").exists())

    def test_interactive_running_bots_can_show_logs(self) -> None:
        create_bot(
            self.work_dir,
            BotAnswers(
                display_name="Logs Bot",
                role="Reading logs",
                skill_sources=[],
                system_packages=[],
                python_packages=[],
                node_packages=[],
                secret_names=[],
                websites=[],
                databases=[],
                access_notes=[],
            ),
        )
        with patch(
            "openenv.bots.manager.build_lockfile",
            side_effect=self._build_stub_lockfile,
        ):
            generate_bot_artifacts(self.work_dir, "logs-bot")

        answers = iter(["en", "5", "1", "1", "6"])
        stdout = io.StringIO()
        with patch(
            "openenv.bots.manager.list_running_container_names",
            return_value={"logs-bot-openclaw-gateway"},
        ):
            with patch(
                "openenv.bots.manager.fetch_container_logs",
                return_value="alpha\nbeta\n",
            ):
                with patch("builtins.input", side_effect=lambda _: next(answers)):
                    with redirect_stdout(stdout):
                        exit_code = interactive_menu(self.work_dir)

        self.assertEqual(exit_code, 0)
        output = stdout.getvalue()
        self.assertIn("Running bots:", output)
        self.assertIn("Logs for `Logs Bot`:", output)
        self.assertIn("alpha", output)

    def test_main_without_args_opens_interactive_menu(self) -> None:
        with patch("openenv.cli.interactive_menu", return_value=0) as menu:
            exit_code = main([])

        self.assertEqual(exit_code, 0)
        menu.assert_called_once()

    def test_interactive_menu_reprompts_language_and_unknown_main_option(self) -> None:
        answers = iter(["??", "en", "9", "6"])
        stdout = io.StringIO()

        with patch("builtins.input", side_effect=lambda _: next(answers)):
            with redirect_stdout(stdout):
                exit_code = interactive_menu(self.work_dir)

        self.assertEqual(exit_code, 0)
        output = stdout.getvalue()
        self.assertIn("Unknown choice", output)
        self.assertIn("Unknown option. Choose 1, 2, 3, 4, 5, or 6.", output)

    def test_interactive_running_bots_snapshot_reports_no_changes(self) -> None:
        create_bot(
            self.work_dir,
            BotAnswers(
                display_name="Snapshot Bot",
                role="Runtime snapshotting",
                skill_sources=[],
                system_packages=[],
                python_packages=[],
                node_packages=[],
                secret_names=[],
                websites=[],
                databases=[],
                access_notes=[],
            ),
        )
        with patch(
            "openenv.bots.manager.build_lockfile",
            side_effect=self._build_stub_lockfile,
        ):
            generate_bot_artifacts(self.work_dir, "snapshot-bot")

        answers = iter(["en", "5", "1", "2", "6"])
        stdout = io.StringIO()
        with patch(
            "openenv.bots.manager.list_running_container_names",
            return_value={"snapshot-bot-openclaw-gateway"},
        ):
            with patch(
                "openenv.bots.manager.create_skill_snapshot",
                return_value=type(
                    "Result",
                    (),
                    {
                        "added_skill_names": [],
                        "hydrated_skill_names": [],
                        "manifest_path": self.work_dir / "bots" / "snapshot-bot" / "openclawenv.toml",
                        "lock_path": None,
                    },
                )(),
            ):
                with patch("builtins.input", side_effect=lambda _: next(answers)):
                    with redirect_stdout(stdout):
                        exit_code = interactive_menu(self.work_dir)

        self.assertEqual(exit_code, 0)
        self.assertIn("did not detect any new skill changes", stdout.getvalue())

    def test_interactive_browse_running_bots_reports_discovery_error(self) -> None:
        answers = iter(["en", "5", "6"])
        stdout = io.StringIO()
        with patch(
            "openenv.bots.manager.discover_running_bots",
            side_effect=OpenEnvError("docker not available"),
        ):
            with patch("builtins.input", side_effect=lambda _: next(answers)):
                with redirect_stdout(stdout):
                    exit_code = interactive_menu(self.work_dir)

        self.assertEqual(exit_code, 0)
        self.assertIn("Failed to inspect running bots", stdout.getvalue())

    def test_edit_and_delete_report_no_bots(self) -> None:
        answers = iter(["en", "3", "4", "6"])
        stdout = io.StringIO()
        with patch("builtins.input", side_effect=lambda _: next(answers)):
            with redirect_stdout(stdout):
                exit_code = interactive_menu(self.work_dir)

        self.assertEqual(exit_code, 0)
        output = stdout.getvalue()
        self.assertIn("There are no bots to edit.", output)
        self.assertIn("There are no bots to delete.", output)

    def test_interactive_delete_can_be_cancelled(self) -> None:
        create_bot(
            self.work_dir,
            BotAnswers(
                display_name="Cancel Bot",
                role="Delete cancellation",
                skill_sources=[],
                system_packages=[],
                python_packages=[],
                node_packages=[],
                secret_names=[],
                websites=[],
                databases=[],
                access_notes=[],
            ),
        )
        answers = iter(["en", "4", "1", "n", "6"])
        stdout = io.StringIO()
        with patch("builtins.input", side_effect=lambda _: next(answers)):
            with redirect_stdout(stdout):
                exit_code = interactive_menu(self.work_dir)

        self.assertEqual(exit_code, 0)
        self.assertIn("Deletion cancelled.", stdout.getvalue())
        self.assertTrue((self.work_dir / "bots" / "cancel-bot").exists())

    def test_interactive_bot_actions_reports_openrouter_failure(self) -> None:
        create_bot(
            self.work_dir,
            BotAnswers(
                display_name="Docs Bot",
                role="Improving documentation",
                skill_sources=[],
                system_packages=[],
                python_packages=[],
                node_packages=[],
                secret_names=[],
                websites=[],
                databases=[],
                access_notes=[],
            ),
        )
        answers = iter(["en", "1", "1", "2", "Improve docs", "6"])
        stdout = io.StringIO()
        with patch(
            "openenv.bots.manager.improve_bot_markdown_documents",
            side_effect=OpenEnvError("OpenRouter unavailable"),
        ):
            with patch("openenv.bots.manager.get_project_env_value", return_value="key"):
                with patch("builtins.input", side_effect=lambda _: next(answers)):
                    with redirect_stdout(stdout):
                        exit_code = interactive_menu(self.work_dir)

        self.assertEqual(exit_code, 0)
        self.assertIn("Failed to improve documents", stdout.getvalue())

    def test_prompt_helpers_cover_empty_and_default_paths(self) -> None:
        with patch("builtins.input", side_effect=["", "  ", "final"]):
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                value = _prompt_nonempty("Prompt: ", "en")
        self.assertEqual(value, "final")
        self.assertIn("This field is required.", stdout.getvalue())

        with patch("builtins.input", return_value=""):
            self.assertEqual(_prompt_csv("CSV: "), [])
            self.assertEqual(_prompt_csv_with_default("CSV: ", ["a", "b"]), ["a", "b"])

        with patch("builtins.input", return_value=" one, two ,, three "):
            self.assertEqual(_prompt_csv("CSV: "), ["one", "two", "three"])

    def test_selection_helpers_reject_invalid_values(self) -> None:
        record = create_bot(
            self.work_dir,
            BotAnswers(
                display_name="Select Bot",
                role="Selection",
                skill_sources=[],
                system_packages=[],
                python_packages=[],
                node_packages=[],
                secret_names=[],
                websites=[],
                databases=[],
                access_notes=[],
            ),
        )
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            self.assertIsNone(_bot_from_selection([record], "x", "en"))
            self.assertIsNone(_bot_from_selection([record], "2", "en"))
            self.assertIsNone(_running_bot_from_selection([], "1", "en"))

        self.assertIn("invalid", stdout.getvalue().lower())
        self.assertIn("out of range", stdout.getvalue())

    def test_language_helpers_cover_aliases_and_validation(self) -> None:
        self.assertEqual(_normalize_language("POLSKI"), "pl")
        self.assertEqual(_normalize_language("eng"), "en")
        self.assertIsNone(_normalize_language("??"))
        self.assertEqual(_require_language("english"), "en")
        with self.assertRaises(OpenEnvError):
            _require_language("de")

        with patch("builtins.input", side_effect=["?", "2"]):
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                language = _select_language()
        self.assertEqual(language, "en")
        self.assertIn("Unknown choice", stdout.getvalue())

    def test_resolve_openrouter_api_key_prefers_existing_value_and_rejects_empty_prompt(self) -> None:
        with patch("openenv.bots.manager.get_project_env_value", return_value="existing"):
            self.assertEqual(_resolve_openrouter_api_key(self.work_dir, "en"), "existing")

        with patch("openenv.bots.manager.get_project_env_value", return_value=""):
            with patch("openenv.bots.manager.getpass", return_value="   "):
                with redirect_stdout(io.StringIO()):
                    with self.assertRaises(OpenEnvError):
                        _resolve_openrouter_api_key(self.work_dir, "en")

    def test_ensure_bot_agent_documents_materialized_assigns_refs_and_writes_files(self) -> None:
        bot = create_bot(
            self.work_dir,
            BotAnswers(
                display_name="Materialize Bot",
                role="Materialize docs",
                skill_sources=[],
                system_packages=[],
                python_packages=[],
                node_packages=[],
                secret_names=[],
                websites=[],
                databases=[],
                access_notes=[],
            ),
        )
        manifest = bot.manifest
        manifest.agent.agents_md_ref = None
        manifest.agent.tools_md_ref = None
        manifest.agent.memory_seed_ref = None
        manifest.agent.tools_md = "# Tools\n"
        manifest_path = bot.manifest_path
        manifest_path.write_text(render_manifest(manifest), encoding="utf-8")
        reloaded = load_bot(self.work_dir, bot.slug)
        (reloaded.manifest_path.parent / "AGENTS.md").unlink(missing_ok=True)
        (reloaded.manifest_path.parent / "TOOLS.md").unlink(missing_ok=True)
        (reloaded.manifest_path.parent / "memory.md").unlink(missing_ok=True)

        updated = _ensure_bot_agent_documents_materialized(reloaded)

        self.assertEqual(updated.manifest.agent.agents_md_ref, "AGENTS.md")
        self.assertEqual(updated.manifest.agent.tools_md_ref, "TOOLS.md")
        self.assertEqual(updated.manifest.agent.memory_seed_ref, "memory.md")
        self.assertTrue((updated.manifest_path.parent / "AGENTS.md").exists())
        self.assertTrue((updated.manifest_path.parent / "TOOLS.md").exists())
        self.assertTrue((updated.manifest_path.parent / "memory.md").exists())

    def test_load_running_bot_reports_missing_compose_and_not_running(self) -> None:
        bot = create_bot(
            self.work_dir,
            BotAnswers(
                display_name="Runtime Bot",
                role="Runtime",
                skill_sources=[],
                system_packages=[],
                python_packages=[],
                node_packages=[],
                secret_names=[],
                websites=[],
                databases=[],
                access_notes=[],
            ),
        )

        with self.assertRaises(OpenEnvError) as missing_ctx:
            _load_running_bot(self.work_dir, bot.slug)
        self.assertIn("Compose file not found", str(missing_ctx.exception))

        with patch(
            "openenv.bots.manager.build_lockfile",
            side_effect=self._build_stub_lockfile,
        ):
            generate_bot_artifacts(self.work_dir, bot.slug)

        with patch("openenv.bots.manager.list_running_container_names", return_value=set()):
            with self.assertRaises(OpenEnvError) as not_running_ctx:
                _load_running_bot(self.work_dir, bot.slug)
        self.assertIn("is not currently running", str(not_running_ctx.exception))

    def test_snapshot_hydration_only_fills_missing_fields(self) -> None:
        skill = SkillConfig(
            name="catalog-skill",
            description="Skill referenced from catalog source: abc",
            content=None,
            source=None,
            assets={},
        )
        captured = CapturedSkill(
            name="catalog-skill",
            description="Hydrated description",
            content="---\nname: catalog-skill\n---\n",
            source="acme/catalog-skill",
            assets={"note.md": "hello"},
        )

        changed = _hydrate_skill_from_snapshot(skill, captured)

        self.assertTrue(changed)
        self.assertEqual(skill.description, "Hydrated description")
        self.assertEqual(skill.source, "acme/catalog-skill")
        self.assertEqual(skill.assets, {"note.md": "hello"})

    def test_unique_paths_and_render_tools_markdown_cover_optional_sections(self) -> None:
        repeated = self.work_dir / "same.md"
        unique = self.work_dir / "other.md"
        self.assertEqual(_unique_paths([repeated, repeated, unique]), [repeated, unique])

        markdown = _render_tools_markdown(
            skill_sources=["acme/one"],
            websites=["https://example.com"],
            databases=["postgres://db"],
            access_notes=["Read only"],
        )
        self.assertIn("## Skill Sources", markdown)
        self.assertIn("## Websites", markdown)
        self.assertIn("## Databases", markdown)
        self.assertIn("## Access Notes", markdown)

    def test_path_resolution_helpers_cover_preferred_legacy_and_missing_files(self) -> None:
        bot_dir = self.work_dir / "bots" / "path-bot"
        bot_dir.mkdir(parents=True, exist_ok=True)

        self.assertIsNone(bot_manager._resolve_bot_manifest_path(bot_dir))
        self.assertEqual(
            bot_manager._preferred_lockfile_path(bot_dir),
            bot_dir / bot_manager.LOCKFILE_FILENAME,
        )

        legacy_manifest = bot_dir / bot_manager.LEGACY_MANIFEST_FILENAME
        legacy_manifest.write_text("legacy", encoding="utf-8")
        self.assertEqual(bot_manager._resolve_bot_manifest_path(bot_dir), legacy_manifest)

        preferred_manifest = bot_dir / bot_manager.MANIFEST_FILENAME
        preferred_manifest.write_text("preferred", encoding="utf-8")
        self.assertEqual(bot_manager._resolve_bot_manifest_path(bot_dir), preferred_manifest)

        legacy_lockfile = bot_dir / bot_manager.LEGACY_LOCKFILE_FILENAME
        legacy_lockfile.write_text("{}", encoding="utf-8")
        self.assertEqual(bot_manager._preferred_lockfile_path(bot_dir), legacy_lockfile)

        preferred_lockfile = bot_dir / bot_manager.LOCKFILE_FILENAME
        preferred_lockfile.write_text("{}", encoding="utf-8")
        self.assertEqual(bot_manager._preferred_lockfile_path(bot_dir), preferred_lockfile)

    def test_discover_bots_skips_missing_and_invalid_manifests(self) -> None:
        record = create_bot(
            self.work_dir,
            BotAnswers(
                display_name="Legacy Bot",
                role="Legacy manifest fallback",
                skill_sources=[],
                system_packages=[],
                python_packages=[],
                node_packages=[],
                secret_names=[],
                websites=[],
                databases=[],
                access_notes=[],
            ),
        )
        legacy_manifest = record.manifest_path.parent / bot_manager.LEGACY_MANIFEST_FILENAME
        record.manifest_path.rename(legacy_manifest)

        missing_manifest_dir = self.work_dir / "bots" / "missing-manifest"
        missing_manifest_dir.mkdir(parents=True, exist_ok=True)
        broken_manifest_dir = self.work_dir / "bots" / "broken-manifest"
        broken_manifest_dir.mkdir(parents=True, exist_ok=True)
        (broken_manifest_dir / bot_manager.MANIFEST_FILENAME).write_text(
            "schema_version = [",
            encoding="utf-8",
        )

        discovered = discover_bots(self.work_dir)

        self.assertEqual([bot.slug for bot in discovered], ["legacy-bot"])
        self.assertEqual(discovered[0].manifest_path.name, bot_manager.LEGACY_MANIFEST_FILENAME)

    def test_crud_helpers_cover_duplicate_missing_and_collision_paths(self) -> None:
        create_bot(
            self.work_dir,
            BotAnswers(
                display_name="First Bot",
                role="First",
                skill_sources=[],
                system_packages=[],
                python_packages=[],
                node_packages=[],
                secret_names=[],
                websites=[],
                databases=[],
                access_notes=[],
            ),
        )
        create_bot(
            self.work_dir,
            BotAnswers(
                display_name="Second Bot",
                role="Second",
                skill_sources=[],
                system_packages=[],
                python_packages=[],
                node_packages=[],
                secret_names=[],
                websites=[],
                databases=[],
                access_notes=[],
            ),
        )

        with self.assertRaises(OpenEnvError):
            create_bot(
                self.work_dir,
                BotAnswers(
                    display_name="First Bot",
                    role="Duplicate",
                    skill_sources=[],
                    system_packages=[],
                    python_packages=[],
                    node_packages=[],
                    secret_names=[],
                    websites=[],
                    databases=[],
                    access_notes=[],
                ),
            )
        with self.assertRaises(OpenEnvError):
            update_bot(
                self.work_dir,
                "missing-bot",
                BotAnswers(
                    display_name="Missing Bot",
                    role="Missing",
                    skill_sources=[],
                    system_packages=[],
                    python_packages=[],
                    node_packages=[],
                    secret_names=[],
                    websites=[],
                    databases=[],
                    access_notes=[],
                ),
            )
        with self.assertRaises(OpenEnvError):
            update_bot(
                self.work_dir,
                "first-bot",
                BotAnswers(
                    display_name="Second Bot",
                    role="Collision",
                    skill_sources=[],
                    system_packages=[],
                    python_packages=[],
                    node_packages=[],
                    secret_names=[],
                    websites=[],
                    databases=[],
                    access_notes=[],
                ),
            )
        with self.assertRaises(OpenEnvError):
            delete_bot(self.work_dir, "missing-bot")
        with self.assertRaises(OpenEnvError):
            load_bot(self.work_dir, "missing-bot")

    def test_update_bot_same_slug_removes_legacy_manifest(self) -> None:
        record = create_bot(
            self.work_dir,
            BotAnswers(
                display_name="Same Bot",
                role="Original role",
                skill_sources=[],
                system_packages=[],
                python_packages=[],
                node_packages=[],
                secret_names=[],
                websites=[],
                databases=[],
                access_notes=[],
            ),
        )
        legacy_manifest = record.manifest_path.parent / bot_manager.LEGACY_MANIFEST_FILENAME
        legacy_manifest.write_text(
            record.manifest_path.read_text(encoding="utf-8"),
            encoding="utf-8",
        )

        updated = update_bot(
            self.work_dir,
            record.slug,
            BotAnswers(
                display_name="Same Bot",
                role="Updated role",
                skill_sources=[],
                system_packages=[],
                python_packages=[],
                node_packages=[],
                secret_names=[],
                websites=[],
                databases=[],
                access_notes=[],
            ),
        )

        self.assertEqual(updated.slug, "same-bot")
        self.assertFalse(legacy_manifest.exists())
        self.assertEqual(updated.role, "Updated role")

    def test_generate_bot_artifacts_handles_missing_sidecar_env(self) -> None:
        record = create_bot(
            self.work_dir,
            BotAnswers(
                display_name="Envless Bot",
                role="Missing sidecar env",
                skill_sources=[],
                system_packages=[],
                python_packages=[],
                node_packages=[],
                secret_names=[],
                websites=[],
                databases=[],
                access_notes=[],
            ),
        )
        (record.manifest_path.parent / ".env").unlink()

        with patch(
            "openenv.bots.manager.build_lockfile",
            side_effect=self._build_stub_lockfile,
        ):
            artifacts = generate_bot_artifacts(self.work_dir, record.slug)

        self.assertTrue(artifacts.env_path.exists())
        self.assertIn("OPENCLAW_IMAGE=", artifacts.env_path.read_text(encoding="utf-8"))

    def test_generate_all_bots_stack_rejects_empty_catalog(self) -> None:
        with self.assertRaises(OpenEnvError) as ctx:
            generate_all_bots_stack(self.work_dir)

        self.assertIn("No managed bots were found.", str(ctx.exception))

    def test_interactive_browse_helpers_cover_empty_and_failure_paths(self) -> None:
        stdout = io.StringIO()
        with patch("openenv.bots.manager.discover_running_bots", return_value=[]):
            with redirect_stdout(stdout):
                bot_manager._show_bots(self.work_dir, "en")
                bot_manager._interactive_browse_bots(self.work_dir, "en")
                bot_manager._interactive_browse_running_bots(self.work_dir, "en")

        self.assertIn("No registered bots.", stdout.getvalue())
        self.assertIn("No running bots", stdout.getvalue())

        record = create_bot(
            self.work_dir,
            BotAnswers(
                display_name="Browse Bot",
                role="Browse actions",
                skill_sources=[],
                system_packages=[],
                python_packages=[],
                node_packages=[],
                secret_names=[],
                websites=[],
                databases=[],
                access_notes=[],
            ),
        )
        stdout = io.StringIO()
        with patch("builtins.input", return_value="a"):
            with patch(
                "openenv.bots.manager.generate_all_bots_stack",
                side_effect=OpenEnvError("compose failed"),
            ):
                with redirect_stdout(stdout):
                    bot_manager._interactive_browse_bots(self.work_dir, "en")
        self.assertIn("Failed to generate the shared stack", stdout.getvalue())

        stdout = io.StringIO()
        with patch("builtins.input", side_effect=["", "x"]):
            with redirect_stdout(stdout):
                bot_manager._interactive_browse_bots(self.work_dir, "en")
                bot_manager._interactive_browse_bots(self.work_dir, "en")
        self.assertIn("invalid", stdout.getvalue().lower())

        running_bot = bot_manager.RunningBotRecord(
            bot=record,
            compose_path=record.manifest_path.parent / "docker-compose-browse-bot.yml",
            container_name="browse-bot-openclaw-gateway",
        )
        stdout = io.StringIO()
        with patch(
            "openenv.bots.manager.discover_running_bots",
            return_value=[running_bot],
        ):
            with patch("builtins.input", side_effect=["", "x"]):
                with redirect_stdout(stdout):
                    bot_manager._interactive_browse_running_bots(self.work_dir, "en")
                    bot_manager._interactive_browse_running_bots(self.work_dir, "en")
        self.assertIn("invalid", stdout.getvalue().lower())

    def test_interactive_action_helpers_cover_error_success_back_and_unknown_paths(self) -> None:
        record = create_bot(
            self.work_dir,
            BotAnswers(
                display_name="Action Bot",
                role="Action flows",
                skill_sources=[],
                system_packages=[],
                python_packages=[],
                node_packages=[],
                secret_names=[],
                websites=[],
                databases=[],
                access_notes=[],
            ),
        )
        running_bot = bot_manager.RunningBotRecord(
            bot=record,
            compose_path=record.manifest_path.parent / "docker-compose-action-bot.yml",
            container_name="action-bot-openclaw-gateway",
        )

        stdout = io.StringIO()
        with patch("builtins.input", return_value="1"):
            with patch(
                "openenv.bots.manager.generate_bot_artifacts",
                side_effect=OpenEnvError("build failed"),
            ):
                with redirect_stdout(stdout):
                    bot_manager._interactive_bot_actions(self.work_dir, record, "en")
        self.assertIn("Failed to generate artifacts", stdout.getvalue())

        stdout = io.StringIO()
        with patch("builtins.input", side_effect=["3", "9"]):
            with redirect_stdout(stdout):
                bot_manager._interactive_bot_actions(self.work_dir, record, "en")
                bot_manager._interactive_bot_actions(self.work_dir, record, "en")
        self.assertIn("Unknown option", stdout.getvalue())

        stdout = io.StringIO()
        with patch("builtins.input", return_value="1"):
            with patch(
                "openenv.bots.manager.preview_running_bot_logs",
                side_effect=OpenEnvError("logs failed"),
            ):
                with redirect_stdout(stdout):
                    bot_manager._interactive_running_bot_actions(
                        self.work_dir,
                        running_bot,
                        "en",
                    )
        self.assertIn("Failed to fetch logs", stdout.getvalue())

        snapshot_result = bot_manager.SkillSnapshotResult(
            bot=record,
            manifest_path=record.manifest_path,
            lock_path=record.manifest_path.parent / bot_manager.LOCKFILE_FILENAME,
            added_skill_names=["new-skill"],
            hydrated_skill_names=["hydrated-skill"],
        )
        stdout = io.StringIO()
        with patch("builtins.input", side_effect=["2", "3", "9"]):
            with patch(
                "openenv.bots.manager.create_skill_snapshot",
                side_effect=[
                    snapshot_result,
                    snapshot_result,
                    snapshot_result,
                ],
            ):
                with redirect_stdout(stdout):
                    bot_manager._interactive_running_bot_actions(
                        self.work_dir,
                        running_bot,
                        "en",
                    )
                    bot_manager._interactive_running_bot_actions(
                        self.work_dir,
                        running_bot,
                        "en",
                    )
                    bot_manager._interactive_running_bot_actions(
                        self.work_dir,
                        running_bot,
                        "en",
                    )
        output = stdout.getvalue()
        self.assertIn("Updated manifest", output)
        self.assertIn("Updated lockfile", output)
        self.assertIn("Added skill: new-skill", output)
        self.assertIn("Hydrated skill from container: hydrated-skill", output)
        self.assertIn("Unknown option", output)

    def test_interactive_crud_helpers_cover_failure_and_selection_shortcuts(self) -> None:
        stdout = io.StringIO()
        with patch(
            "builtins.input",
            side_effect=["Fail Bot", "Role", "", "", "", "", "", "", "", ""],
        ):
            with patch(
                "openenv.bots.manager.create_bot",
                side_effect=OpenEnvError("create failed"),
            ):
                with redirect_stdout(stdout):
                    bot_manager._interactive_add_bot(self.work_dir, "en")
        self.assertIn("Failed to create bot", stdout.getvalue())

        record = create_bot(
            self.work_dir,
            BotAnswers(
                display_name="Edit Bot",
                role="Edit flow",
                skill_sources=[],
                system_packages=[],
                python_packages=[],
                node_packages=[],
                secret_names=[],
                websites=[],
                databases=[],
                access_notes=[],
            ),
        )
        stdout = io.StringIO()
        with patch("builtins.input", return_value="x"):
            with redirect_stdout(stdout):
                bot_manager._interactive_edit_bot(self.work_dir, "en")
        self.assertIn("invalid", stdout.getvalue().lower())

        stdout = io.StringIO()
        with patch(
            "builtins.input",
            side_effect=["1", "", "", "", "", "", "", "", "", "", ""],
        ):
            with patch(
                "openenv.bots.manager.update_bot",
                side_effect=OpenEnvError("update failed"),
            ):
                with redirect_stdout(stdout):
                    bot_manager._interactive_edit_bot(self.work_dir, "en")
        self.assertIn("Failed to update bot", stdout.getvalue())

        stdout = io.StringIO()
        with patch("builtins.input", return_value="x"):
            with redirect_stdout(stdout):
                bot_manager._interactive_delete_bot(self.work_dir, "en")
        self.assertIn("invalid", stdout.getvalue().lower())

        stdout = io.StringIO()
        with patch("builtins.input", side_effect=["1", "y"]):
            with patch(
                "openenv.bots.manager.delete_bot",
                side_effect=OpenEnvError("delete failed"),
            ):
                with redirect_stdout(stdout):
                    bot_manager._interactive_delete_bot(self.work_dir, "en")
        self.assertIn("Failed to delete bot", stdout.getvalue())

        self.assertTrue((self.work_dir / "bots" / record.slug).exists())

    def test_document_and_skill_helpers_cover_optional_and_deduplicated_paths(self) -> None:
        record = create_bot(
            self.work_dir,
            BotAnswers(
                display_name="Helper Bot",
                role="Helper flows",
                skill_sources=["acme/catalog-skill"],
                system_packages=[],
                python_packages=[],
                node_packages=[],
                secret_names=[],
                websites=[],
                databases=[],
                access_notes=[],
            ),
        )
        manifest = record.manifest
        manifest.agent.identity_md = None
        manifest.agent.identity_md_ref = None
        manifest.agent.tools_md = None
        manifest.agent.tools_md_ref = None
        manifest.agent.memory_seed = []
        manifest.agent.memory_seed_ref = None

        bot_dir = record.manifest_path.parent
        bot_manager._write_agent_docs(bot_dir, manifest.agent)
        bot_manager._write_agent_doc(bot_dir, None, "ignored")
        documents = bot_manager._bot_documents(manifest)

        self.assertEqual(set(documents), {"AGENTS.md", "SOUL.md", "USER.md", "memory.md"})
        self.assertEqual(bot_manager._memory_seed_text([]), "")
        self.assertEqual(
            bot_manager._unique_preserving_order(["a", "b", "a", "c", "b"]),
            ["a", "b", "c"],
        )

        manifest.skills = [
            SkillConfig(
                name="catalog-skill",
                description="Skill referenced from catalog source: acme/catalog-skill",
                content=None,
                source=None,
                assets={},
            )
        ]
        added, hydrated = bot_manager._apply_skill_snapshot(
            manifest,
            [
                CapturedSkill(
                    name="catalog-skill",
                    description="Hydrated description",
                    content="---\nname: catalog-skill\n---\n",
                    source="acme/catalog-skill",
                    assets={"note.md": "hello"},
                ),
                CapturedSkill(
                    name="new-runtime-skill",
                    description="New runtime skill",
                    content="---\nname: new-runtime-skill\n---\n",
                    source="acme/new-runtime-skill",
                    assets={},
                ),
            ],
        )
        self.assertEqual(added, ["new-runtime-skill"])
        self.assertEqual(hydrated, ["catalog-skill"])

    def _build_stub_lockfile(self, manifest, raw_manifest_text):
        return build_lockfile_for_test(
            manifest,
            raw_manifest_text,
            resolver=lambda _: {
                "digest": PINNED_IMAGE.split("@", 1)[1],
                "resolved_reference": PINNED_IMAGE,
            },
        )

