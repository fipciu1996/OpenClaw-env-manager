from __future__ import annotations

import tomllib
import shutil
import unittest
from pathlib import Path

from openenv.manifests import loader as manifest_loader
from openenv.core.skills import MANDATORY_SKILL_SOURCES
from openenv.core.errors import ValidationError
from openenv.manifests.loader import load_manifest, parse_manifest
from openenv.manifests.writer import render_manifest


TESTS_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = TESTS_ROOT / "fixtures"
TEMP_ROOT = TESTS_ROOT / "_tmp"
TEMP_ROOT.mkdir(exist_ok=True)


class ManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.work_dir = TEMP_ROOT / "manifest"
        if self.work_dir.exists():
            shutil.rmtree(self.work_dir, ignore_errors=True)
        self.work_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.work_dir, ignore_errors=True)

    def test_load_fixture_manifest(self) -> None:
        manifest, _ = load_manifest(FIXTURES / "example.openclawenv.toml")

        self.assertEqual(manifest.project.name, "ops-agent")
        self.assertEqual(manifest.runtime.user, "root")
        self.assertEqual(manifest.openclaw.agent_name, "Operations Agent")
        self.assertEqual(manifest.runtime.node_packages, ["typescript@5.8.3"])
        self.assertEqual(len(manifest.skills), 6)
        self.assertEqual(
            [skill.source for skill in manifest.skills[: len(MANDATORY_SKILL_SOURCES)]],
            list(MANDATORY_SKILL_SOURCES),
        )

    def test_load_manifest_reports_missing_file(self) -> None:
        with self.assertRaises(ValidationError) as ctx:
            load_manifest(self.work_dir / "missing.toml")

        self.assertIn("Manifest file not found", str(ctx.exception))

    def test_load_manifest_reports_invalid_toml(self) -> None:
        manifest_path = self.work_dir / "openclawenv.toml"
        manifest_path.write_text("schema_version = [", encoding="utf-8")

        with self.assertRaises(ValidationError) as ctx:
            load_manifest(manifest_path)

        self.assertIn("Invalid TOML", str(ctx.exception))

    def test_rejects_inline_sensitive_env(self) -> None:
        raw = """
schema_version = 1

[project]
name = "bad-agent"
version = "0.1.0"
description = "bad"
runtime = "openclaw"

[runtime]
base_image = "python:3.12-slim@sha256:1111111111111111111111111111111111111111111111111111111111111111"
python_version = "3.12"
python_packages = ["requests==2.32.3"]
env = { OPENAI_API_KEY = "super-secret-value" }

[agent]
agents_md = "a"
soul_md = "b"
user_md = "c"

[openclaw]
agent_id = "main"
agent_name = "Bad Agent"

[openclaw.sandbox]
mode = "workspace-write"
scope = "session"
workspace_access = "full"
network = "bridge"
read_only_root = false
"""
        with self.assertRaises(ValidationError):
            parse_manifest(tomllib.loads(raw))

    def test_parse_manifest_adds_mandatory_skills_when_missing(self) -> None:
        raw = """
schema_version = 1

[project]
name = "base-agent"
version = "0.1.0"
description = "minimal"
runtime = "openclaw"

[runtime]
base_image = "python:3.12-slim@sha256:1111111111111111111111111111111111111111111111111111111111111111"
python_version = "3.12"

[agent]
agents_md = "a"
soul_md = "b"
user_md = "c"

[openclaw]
agent_id = "main"
agent_name = "Base Agent"

[openclaw.sandbox]
mode = "workspace-write"
scope = "session"
workspace_access = "full"
network = "bridge"
read_only_root = false
"""
        manifest = parse_manifest(tomllib.loads(raw))

        self.assertEqual(
            [skill.source for skill in manifest.skills],
            list(MANDATORY_SKILL_SOURCES),
        )

    def test_load_manifest_reads_secret_refs_from_sidecar_env(self) -> None:
        manifest_path = self.work_dir / "openclawenv.toml"
        manifest_path.write_text(
            """
schema_version = 1

[project]
name = "env-agent"
version = "0.1.0"
description = "env-backed"
runtime = "openclaw"

[runtime]
base_image = "python:3.12-slim@sha256:1111111111111111111111111111111111111111111111111111111111111111"
python_version = "3.12"
python_packages = ["requests==2.32.3"]

[agent]
agents_md = "a"
soul_md = "b"
user_md = "c"

[openclaw]
agent_id = "main"
agent_name = "Env Agent"

[openclaw.sandbox]
mode = "workspace-write"
scope = "session"
workspace_access = "full"
network = "bridge"
read_only_root = false
""".strip(),
            encoding="utf-8",
        )
        (self.work_dir / ".env").write_text(
            "# Secret references\nOPENAI_API_KEY=\nDB_PASSWORD=secret\n",
            encoding="utf-8",
        )

        manifest, _ = load_manifest(manifest_path)

        self.assertEqual(
            [secret.name for secret in manifest.runtime.secret_refs],
            ["OPENAI_API_KEY", "DB_PASSWORD"],
        )

    def test_load_manifest_reads_agent_docs_from_local_markdown_refs(self) -> None:
        manifest_path = self.work_dir / "openclawenv.toml"
        manifest_path.write_text(
            """
schema_version = 1

[project]
name = "ref-agent"
version = "0.1.0"
description = "file-backed docs"
runtime = "openclaw"

[runtime]
base_image = "python:3.12-slim@sha256:1111111111111111111111111111111111111111111111111111111111111111"
python_version = "3.12"

[agent]
agents_md = "AGENTS.md"
soul_md = "SOUL.md"
user_md = "USER.md"
identity_md = "IDENTITY.md"
tools_md = "TOOLS.md"
memory_seed = "memory.md"

[openclaw]
agent_id = "main"
agent_name = "Ref Agent"

[openclaw.sandbox]
mode = "workspace-write"
scope = "session"
workspace_access = "full"
network = "bridge"
read_only_root = false
""".strip(),
            encoding="utf-8",
        )
        (self.work_dir / "AGENTS.md").write_text("# Agent Contract\n", encoding="utf-8")
        (self.work_dir / "SOUL.md").write_text("# Soul\n", encoding="utf-8")
        (self.work_dir / "USER.md").write_text("# User\n", encoding="utf-8")
        (self.work_dir / "IDENTITY.md").write_text("# Identity\n", encoding="utf-8")
        (self.work_dir / "TOOLS.md").write_text("# Tools\n", encoding="utf-8")
        (self.work_dir / "memory.md").write_text(
            "Remember the operating model.\nKeep summaries short.\n",
            encoding="utf-8",
        )

        manifest, _ = load_manifest(manifest_path)

        self.assertEqual(manifest.agent.agents_md, "# Agent Contract\n")
        self.assertEqual(manifest.agent.agents_md_ref, "AGENTS.md")
        self.assertEqual(manifest.agent.soul_md_ref, "SOUL.md")
        self.assertEqual(manifest.agent.user_md_ref, "USER.md")
        self.assertEqual(manifest.agent.identity_md_ref, "IDENTITY.md")
        self.assertEqual(manifest.agent.tools_md_ref, "TOOLS.md")
        self.assertEqual(manifest.agent.memory_seed_ref, "memory.md")
        self.assertEqual(
            manifest.agent.memory_seed,
            ["Remember the operating model.", "Keep summaries short."],
        )

    def test_parse_manifest_reads_openclaw_channel_config(self) -> None:
        raw = """
schema_version = 1

[project]
name = "channel-agent"
version = "0.1.0"
description = "channels"
runtime = "openclaw"

[runtime]
base_image = "python:3.12-slim@sha256:1111111111111111111111111111111111111111111111111111111111111111"
python_version = "3.12"

[agent]
agents_md = "a"
soul_md = "b"
user_md = "c"

[openclaw]
agent_id = "main"
agent_name = "Channel Agent"

[openclaw.sandbox]
mode = "workspace-write"
scope = "session"
workspace_access = "full"
network = "bridge"
read_only_root = false

[openclaw.channels.telegram]
enabled = true
allowFrom = ["123456"]

[openclaw.channels.googlechat.accounts.workspace]
serviceAccountFile = "/opt/secrets/googlechat.json"
"""
        manifest = parse_manifest(tomllib.loads(raw))

        self.assertEqual(
            manifest.openclaw.channels,
            {
                "telegram": {"enabled": True, "allowFrom": ["123456"]},
                "googlechat": {
                    "accounts": {
                        "workspace": {
                            "serviceAccountFile": "/opt/secrets/googlechat.json",
                        }
                    }
                },
            },
        )

    def test_render_manifest_round_trips_openclaw_channel_config(self) -> None:
        manifest = parse_manifest(
            tomllib.loads(
                """
schema_version = 1

[project]
name = "channel-agent"
version = "0.1.0"
description = "channels"
runtime = "openclaw"

[runtime]
base_image = "python:3.12-slim@sha256:1111111111111111111111111111111111111111111111111111111111111111"
python_version = "3.12"

[agent]
agents_md = "a"
soul_md = "b"
user_md = "c"

[openclaw]
agent_id = "main"
agent_name = "Channel Agent"

[openclaw.sandbox]
mode = "workspace-write"
scope = "session"
workspace_access = "full"
network = "bridge"
read_only_root = false

[openclaw.channels.matrix]
defaultAccount = "work"

[openclaw.channels.matrix.accounts.work]
homeserver = "https://matrix.example.org"
allowBots = "mentions"
"""
            )
        )

        reparsed = parse_manifest(tomllib.loads(render_manifest(manifest)))

        self.assertEqual(reparsed.openclaw.channels, manifest.openclaw.channels)

    def test_rejects_manifest_with_both_toml_and_sidecar_secret_refs(self) -> None:
        manifest_path = self.work_dir / "openclawenv.toml"
        manifest_path.write_text(
            """
schema_version = 1

[project]
name = "env-agent"
version = "0.1.0"
description = "env-backed"
runtime = "openclaw"

[runtime]
base_image = "python:3.12-slim@sha256:1111111111111111111111111111111111111111111111111111111111111111"
python_version = "3.12"

[[runtime.secret_refs]]
name = "OPENAI_API_KEY"
source = "env:OPENAI_API_KEY"
required = true

[agent]
agents_md = "a"
soul_md = "b"
user_md = "c"

[openclaw]
agent_id = "main"
agent_name = "Env Agent"

[openclaw.sandbox]
mode = "workspace-write"
scope = "session"
workspace_access = "full"
network = "bridge"
read_only_root = false
""".strip(),
            encoding="utf-8",
        )
        (self.work_dir / ".env").write_text("OPENAI_API_KEY=\n", encoding="utf-8")

        with self.assertRaises(ValidationError):
            load_manifest(manifest_path)

    def test_rejects_skill_asset_traversal(self) -> None:
        raw = """
schema_version = 1

[project]
name = "bad-agent"
version = "0.1.0"
description = "bad"
runtime = "openclaw"

[runtime]
base_image = "python:3.12-slim@sha256:1111111111111111111111111111111111111111111111111111111111111111"
python_version = "3.12"
python_packages = ["requests==2.32.3"]

[agent]
agents_md = "a"
soul_md = "b"
user_md = "c"

[[skills]]
name = "bad"
description = "bad"
content = "---\\nname: bad\\ndescription: bad\\n---\\n"
assets = { "../escape.txt" = "nope" }

[openclaw]
agent_id = "main"
agent_name = "Bad Agent"

[openclaw.sandbox]
mode = "workspace-write"
scope = "session"
workspace_access = "full"
network = "bridge"
read_only_root = false
"""
        with self.assertRaises(ValidationError):
            parse_manifest(tomllib.loads(raw))

    def test_rejects_agent_doc_reference_outside_manifest_directory(self) -> None:
        raw = """
schema_version = 1

[project]
name = "bad-agent"
version = "0.1.0"
description = "bad"
runtime = "openclaw"

[runtime]
base_image = "python:3.12-slim@sha256:1111111111111111111111111111111111111111111111111111111111111111"
python_version = "3.12"

[agent]
agents_md = "../AGENTS.md"
soul_md = "b"
user_md = "c"

[openclaw]
agent_id = "main"
agent_name = "Bad Agent"

[openclaw.sandbox]
mode = "workspace-write"
scope = "session"
workspace_access = "full"
network = "bridge"
read_only_root = false
"""
        with self.assertRaises(ValidationError):
            parse_manifest(tomllib.loads(raw), base_dir=self.work_dir)

    def test_rejects_non_openclaw_runtime(self) -> None:
        raw = """
schema_version = 1

[project]
name = "bad-agent"
version = "0.1.0"
description = "bad"
runtime = "docker"

[runtime]
base_image = "python:3.12-slim@sha256:1111111111111111111111111111111111111111111111111111111111111111"
python_version = "3.12"

[agent]
agents_md = "a"
soul_md = "b"
user_md = "c"

[openclaw]
agent_id = "main"
agent_name = "Bad Agent"

[openclaw.sandbox]
mode = "workspace-write"
scope = "session"
workspace_access = "full"
network = "bridge"
read_only_root = false
"""
        with self.assertRaises(ValidationError) as ctx:
            parse_manifest(tomllib.loads(raw))

        self.assertIn("project.runtime", str(ctx.exception))

    def test_allows_wildcard_tool_policies_but_rejects_overlap(self) -> None:
        wildcard_raw = """
schema_version = 1

[project]
name = "wild-agent"
version = "0.1.0"
description = "bad tools"
runtime = "openclaw"

[runtime]
base_image = "python:3.12-slim@sha256:1111111111111111111111111111111111111111111111111111111111111111"
python_version = "3.12"

[agent]
agents_md = "a"
soul_md = "b"
user_md = "c"

[openclaw]
agent_id = "main"
agent_name = "Wild Agent"

[openclaw.sandbox]
mode = "workspace-write"
scope = "session"
workspace_access = "full"
network = "bridge"
read_only_root = true

[openclaw.tools]
allow = ["*"]
deny = []
"""
        manifest = parse_manifest(tomllib.loads(wildcard_raw))
        self.assertEqual(manifest.openclaw.tools_allow, ["*"])

        overlap_raw = wildcard_raw.replace('allow = ["*"]', 'allow = ["shell_command"]').replace(
            "deny = []",
            'deny = ["shell_command"]',
        )
        with self.assertRaises(ValidationError) as overlap_ctx:
            parse_manifest(tomllib.loads(overlap_raw))

        self.assertIn("cannot overlap", str(overlap_ctx.exception))

    def test_rejects_relative_runtime_workdir(self) -> None:
        raw = """
schema_version = 1

[project]
name = "bad-agent"
version = "0.1.0"
description = "bad"
runtime = "openclaw"

[runtime]
base_image = "python:3.12-slim@sha256:1111111111111111111111111111111111111111111111111111111111111111"
python_version = "3.12"
workdir = "workspace"

[agent]
agents_md = "a"
soul_md = "b"
user_md = "c"

[openclaw]
agent_id = "main"
agent_name = "Bad Agent"

[openclaw.sandbox]
mode = "workspace-write"
scope = "session"
workspace_access = "full"
network = "bridge"
read_only_root = false
"""
        with self.assertRaises(ValidationError) as ctx:
            parse_manifest(tomllib.loads(raw))

        self.assertIn("runtime.workdir must be an absolute POSIX path", str(ctx.exception))

    def test_rejects_empty_runtime_env_value(self) -> None:
        raw = """
schema_version = 1

[project]
name = "bad-agent"
version = "0.1.0"
description = "bad"
runtime = "openclaw"

[runtime]
base_image = "python:3.12-slim@sha256:1111111111111111111111111111111111111111111111111111111111111111"
python_version = "3.12"
env = { APP_MODE = "" }

[agent]
agents_md = "a"
soul_md = "b"
user_md = "c"

[openclaw]
agent_id = "main"
agent_name = "Bad Agent"

[openclaw.sandbox]
mode = "workspace-write"
scope = "session"
workspace_access = "full"
network = "bridge"
read_only_root = false
"""
        with self.assertRaises(ValidationError) as ctx:
            parse_manifest(tomllib.loads(raw))

        self.assertIn("runtime.env.APP_MODE cannot be empty", str(ctx.exception))

    def test_rejects_relative_openclaw_workspace(self) -> None:
        raw = """
schema_version = 1

[project]
name = "bad-agent"
version = "0.1.0"
description = "bad"
runtime = "openclaw"

[runtime]
base_image = "python:3.12-slim@sha256:1111111111111111111111111111111111111111111111111111111111111111"
python_version = "3.12"

[agent]
agents_md = "a"
soul_md = "b"
user_md = "c"

[openclaw]
agent_id = "main"
agent_name = "Bad Agent"
workspace = "workspace"

[openclaw.sandbox]
mode = "workspace-write"
scope = "session"
workspace_access = "full"
network = "bridge"
read_only_root = false
"""
        with self.assertRaises(ValidationError) as ctx:
            parse_manifest(tomllib.loads(raw))

        self.assertIn("openclaw.workspace must be an absolute POSIX path", str(ctx.exception))

    def test_rejects_duplicate_skill_names(self) -> None:
        raw = """
schema_version = 1

[project]
name = "dup-agent"
version = "0.1.0"
description = "bad"
runtime = "openclaw"

[runtime]
base_image = "python:3.12-slim@sha256:1111111111111111111111111111111111111111111111111111111111111111"
python_version = "3.12"

[agent]
agents_md = "a"
soul_md = "b"
user_md = "c"

[[skills]]
name = "duplicate"
description = "first"
content = "---\\nname: duplicate\\ndescription: first\\n---\\n"

[[skills]]
name = "duplicate"
description = "second"
content = "---\\nname: duplicate\\ndescription: second\\n---\\n"

[openclaw]
agent_id = "main"
agent_name = "Dup Agent"

[openclaw.sandbox]
mode = "workspace-write"
scope = "session"
workspace_access = "full"
network = "bridge"
read_only_root = false
"""
        with self.assertRaises(ValidationError) as ctx:
            parse_manifest(tomllib.loads(raw))

        self.assertIn("Duplicate skill name", str(ctx.exception))

    def test_memory_seed_inline_string_is_split_into_lines(self) -> None:
        raw = """
schema_version = 1

[project]
name = "memory-agent"
version = "0.1.0"
description = "memory"
runtime = "openclaw"

[runtime]
base_image = "python:3.12-slim@sha256:1111111111111111111111111111111111111111111111111111111111111111"
python_version = "3.12"

[agent]
agents_md = "a"
soul_md = "b"
user_md = "c"
memory_seed = "Keep calm\\n\\nStay focused\\n"

[openclaw]
agent_id = "main"
agent_name = "Memory Agent"

[openclaw.sandbox]
mode = "workspace-write"
scope = "session"
workspace_access = "full"
network = "bridge"
read_only_root = false
"""
        manifest = parse_manifest(tomllib.loads(raw))

        self.assertEqual(manifest.agent.memory_seed, ["Keep calm", "Stay focused"])

    def test_rejects_missing_markdown_reference_file(self) -> None:
        raw = """
schema_version = 1

[project]
name = "missing-ref"
version = "0.1.0"
description = "missing ref"
runtime = "openclaw"

[runtime]
base_image = "python:3.12-slim@sha256:1111111111111111111111111111111111111111111111111111111111111111"
python_version = "3.12"

[agent]
agents_md = "AGENTS.md"
soul_md = "b"
user_md = "c"

[openclaw]
agent_id = "main"
agent_name = "Missing Ref"

[openclaw.sandbox]
mode = "workspace-write"
scope = "session"
workspace_access = "full"
network = "bridge"
read_only_root = false
"""
        with self.assertRaises(ValidationError) as ctx:
            parse_manifest(tomllib.loads(raw), base_dir=self.work_dir)

        self.assertIn("references a missing file", str(ctx.exception))

    def test_rejects_empty_markdown_reference_file(self) -> None:
        raw = """
schema_version = 1

[project]
name = "empty-ref"
version = "0.1.0"
description = "empty ref"
runtime = "openclaw"

[runtime]
base_image = "python:3.12-slim@sha256:1111111111111111111111111111111111111111111111111111111111111111"
python_version = "3.12"

[agent]
agents_md = "AGENTS.md"
soul_md = "b"
user_md = "c"

[openclaw]
agent_id = "main"
agent_name = "Empty Ref"

[openclaw.sandbox]
mode = "workspace-write"
scope = "session"
workspace_access = "full"
network = "bridge"
read_only_root = false
"""
        (self.work_dir / "AGENTS.md").write_text("\n", encoding="utf-8")

        with self.assertRaises(ValidationError) as ctx:
            parse_manifest(tomllib.loads(raw), base_dir=self.work_dir)

        self.assertIn("file cannot be empty", str(ctx.exception))

    def test_rejects_invalid_secret_ref_required_type(self) -> None:
        raw = """
schema_version = 1

[project]
name = "bad-secret-agent"
version = "0.1.0"
description = "bad"
runtime = "openclaw"

[runtime]
base_image = "python:3.12-slim@sha256:1111111111111111111111111111111111111111111111111111111111111111"
python_version = "3.12"

[[runtime.secret_refs]]
name = "OPENAI_API_KEY"
source = "env:OPENAI_API_KEY"
required = "yes"

[agent]
agents_md = "a"
soul_md = "b"
user_md = "c"

[openclaw]
agent_id = "main"
agent_name = "Bad Secret Agent"

[openclaw.sandbox]
mode = "workspace-write"
scope = "session"
workspace_access = "full"
network = "bridge"
read_only_root = false
"""
        with self.assertRaises(ValidationError) as ctx:
            parse_manifest(tomllib.loads(raw))

        self.assertIn("runtime.secret_refs[1].required must be a boolean", str(ctx.exception))

    def test_rejects_invalid_runtime_env_map_types(self) -> None:
        raw = """
schema_version = 1

[project]
name = "bad-env-agent"
version = "0.1.0"
description = "bad"
runtime = "openclaw"

[runtime]
base_image = "python:3.12-slim@sha256:1111111111111111111111111111111111111111111111111111111111111111"
python_version = "3.12"
env = { APP_MODE = 1 }

[agent]
agents_md = "a"
soul_md = "b"
user_md = "c"

[openclaw]
agent_id = "main"
agent_name = "Bad Env Agent"

[openclaw.sandbox]
mode = "workspace-write"
scope = "session"
workspace_access = "full"
network = "bridge"
read_only_root = false
"""
        with self.assertRaises(ValidationError) as ctx:
            parse_manifest(tomllib.loads(raw))

        self.assertIn("runtime.env.APP_MODE must be a string", str(ctx.exception))

    def test_parse_manifest_rejects_non_table_root_and_wrong_schema_version(self) -> None:
        with self.assertRaises(ValidationError) as root_ctx:
            manifest_loader.parse_manifest([])
        self.assertIn("Manifest root must be a TOML table", str(root_ctx.exception))

        with self.assertRaises(ValidationError) as schema_ctx:
            manifest_loader.parse_manifest({"schema_version": 2})
        self.assertIn("schema_version must be set to 1", str(schema_ctx.exception))

    def test_parse_manifest_rejects_invalid_top_level_shapes(self) -> None:
        with self.subTest("skills must be an array"):
            data = self._minimal_manifest_data()
            data["skills"] = {}
            with self.assertRaises(ValidationError) as ctx:
                parse_manifest(data)
            self.assertIn("skills must be an array of tables", str(ctx.exception))

        with self.subTest("tools must be a table"):
            data = self._minimal_manifest_data()
            data["openclaw"]["tools"] = []
            with self.assertRaises(ValidationError) as ctx:
                parse_manifest(data)
            self.assertIn("openclaw.tools must be a table", str(ctx.exception))

    def test_loader_helper_validators_cover_direct_error_paths(self) -> None:
        with self.assertRaises(ValidationError):
            manifest_loader._parse_secret_refs("invalid")
        with self.assertRaises(ValidationError):
            manifest_loader._parse_secret_refs([123])

        with self.assertRaises(ValidationError):
            manifest_loader._parse_skill("invalid", 1)
        with self.assertRaises(ValidationError):
            manifest_loader._parse_skill(
                {"name": "skill", "description": "desc"},
                1,
            )
        with self.assertRaises(ValidationError):
            manifest_loader._parse_skill(
                {"name": "skill", "description": "desc", "content": "plain text"},
                1,
            )

        with self.assertRaises(ValidationError):
            manifest_loader._validate_runtime(
                manifest_loader.RuntimeConfig(
                    base_image="",
                    python_version="3.12",
                    system_packages=[],
                    python_packages=[],
                    node_packages=[],
                    env={},
                    user="root",
                    workdir="/workspace",
                    secret_refs=[],
                )
            )
        with self.assertRaises(ValidationError):
            manifest_loader._validate_openclaw(
                manifest_loader.OpenClawConfig(
                    agent_id="agent",
                    agent_name="Agent",
                    workspace="/opt/openclaw/workspace",
                    state_dir="relative-state",
                    tools_allow=[],
                    tools_deny=[],
                    sandbox=manifest_loader.SandboxConfig(
                        mode="workspace-write",
                        scope="session",
                        workspace_access="full",
                        network="none",
                        read_only_root=False,
                    ),
                )
            )

        with self.assertRaises(ValidationError):
            manifest_loader._require_table({}, "project")
        with self.assertRaises(ValidationError):
            manifest_loader._require_string({"name": ""}, "name")
        with self.assertRaises(ValidationError):
            manifest_loader._optional_string("", "field")
        with self.assertRaises(ValidationError):
            manifest_loader._require_bool({"flag": "yes"}, "flag")
        with self.assertRaises(ValidationError):
            manifest_loader._optional_bool("yes", "flag")
        with self.assertRaises(ValidationError):
            manifest_loader._string_list("wrong", "field")
        with self.assertRaises(ValidationError):
            manifest_loader._string_list(["", 1], "field")
        with self.assertRaises(ValidationError):
            manifest_loader._string_map([], "field")
        with self.assertRaises(ValidationError):
            manifest_loader._string_map({"": "value"}, "field")
        with self.assertRaises(ValidationError):
            manifest_loader._string_map({"key": 1}, "field")

    def test_agent_document_and_memory_seed_helpers_cover_optional_and_reference_paths(self) -> None:
        (self.work_dir / "AGENTS.md").write_text("# Agent Contract\n", encoding="utf-8")
        (self.work_dir / "memory.md").write_text(
            "Remember this.\n\nStay focused.\n",
            encoding="utf-8",
        )

        content, reference = manifest_loader._parse_agent_document(
            {"agents_md": "AGENTS.md"},
            "agents_md",
            base_dir=self.work_dir,
        )
        self.assertEqual(content, "# Agent Contract\n")
        self.assertEqual(reference, "AGENTS.md")

        missing_optional = manifest_loader._parse_agent_document(
            {},
            "identity_md",
            base_dir=self.work_dir,
            required=False,
        )
        none_optional = manifest_loader._parse_agent_document(
            {"identity_md": None},
            "identity_md",
            base_dir=self.work_dir,
            required=False,
        )
        self.assertEqual(missing_optional, (None, None))
        self.assertEqual(none_optional, (None, None))

        memory_seed, memory_reference = manifest_loader._parse_memory_seed(
            "memory.md",
            base_dir=self.work_dir,
        )
        self.assertEqual(memory_seed, ["Remember this.", "Stay focused."])
        self.assertEqual(memory_reference, "memory.md")

        listed_memory_seed, listed_memory_reference = manifest_loader._parse_memory_seed(
            ["Keep calm", "Ship it"],
            base_dir=self.work_dir,
        )
        self.assertEqual(listed_memory_seed, ["Keep calm", "Ship it"])
        self.assertIsNone(listed_memory_reference)

    def _minimal_manifest_data(self) -> dict[str, object]:
        return tomllib.loads(
            """
schema_version = 1

[project]
name = "base-agent"
version = "0.1.0"
description = "minimal"
runtime = "openclaw"

[runtime]
base_image = "python:3.12-slim@sha256:1111111111111111111111111111111111111111111111111111111111111111"
python_version = "3.12"

[agent]
agents_md = "a"
soul_md = "b"
user_md = "c"

[openclaw]
agent_id = "main"
agent_name = "Base Agent"

[openclaw.sandbox]
mode = "workspace-write"
scope = "session"
workspace_access = "full"
network = "bridge"
read_only_root = false
""".strip()
        )


