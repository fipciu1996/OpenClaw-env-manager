# `openclawenv.toml` Structure

## Purpose

`openclawenv.toml` is the canonical manifest for an OpenClaw-env-manager environment. It
describes what should exist in the generated OpenClaw workspace, which runtime
dependencies should be installed, which skills should be materialized, and how
the bot should be configured.

OpenClaw-env-manager treats this file as the source of truth for:

- validation
- lockfile generation
- Dockerfile generation
- Compose generation
- interactive bot management

## Top-Level Layout

An `openclawenv.toml` file is built around five primary sections:

| Section | Required | Purpose |
| --- | --- | --- |
| `schema_version` | yes | Manifest schema version. Current value is `1`. |
| `[project]` | yes | Human-readable project metadata. |
| `[runtime]` | yes | Base image, system packages, Python packages, Node packages, env defaults, and runtime user/workdir. |
| `[agent]` | yes | References or inline content for the agent markdown documents. |
| `[[skills]]` | no | Skill definitions or source references. |
| `[openclaw]` | yes | OpenClaw-specific runtime settings and sandbox configuration. |

## Minimal Example

```toml
schema_version = 1

[project]
name = "operations-agent"
version = "0.1.0"
description = "Support bot for operations workflows"
runtime = "openclaw"

[runtime]
base_image = "python:3.12-slim"
python_version = "3.12"
system_packages = ["git", "curl", "chromium"]
python_packages = ["requests==2.32.3"]
node_packages = ["typescript@5.8.3"]
env = { PYTHONUNBUFFERED = "1" }
user = "agent"
workdir = "/workspace"

[agent]
agents_md = "AGENTS.md"
soul_md = "SOUL.md"
user_md = "USER.md"
identity_md = "IDENTITY.md"
tools_md = "TOOLS.md"
memory_seed = "memory.md"

[[skills]]
name = "incident-brief"
description = "Prepare concise incident reports."
source = "org/incident-brief"

[openclaw]
agent_id = "main"
agent_name = "Operations Agent"
workspace = "/opt/openclaw/workspace"
state_dir = "/opt/openclaw"

[openclaw.sandbox]
mode = "workspace-write"
scope = "session"
workspace_access = "full"
network = "none"
read_only_root = false
```

## `schema_version`

`schema_version` must be set to `1`.

This field allows OpenClaw-env-manager to evolve the manifest format over time while still
supporting explicit compatibility checks.

## `[project]`

The `[project]` section contains basic metadata.

| Field | Required | Purpose |
| --- | --- | --- |
| `name` | yes | Human-readable bot or environment name. |
| `version` | yes | Version string stored in the manifest metadata. |
| `description` | yes | Short explanation of the environment's purpose. |
| `runtime` | yes | Runtime family. In v1 this is expected to be `openclaw`. |

## `[runtime]`

The `[runtime]` section defines what the generated image should install and how
the bot runtime should behave.

| Field | Required | Purpose |
| --- | --- | --- |
| `base_image` | yes | Sandbox or agent image reference, preferably pinned with a digest by the lockfile. |
| `python_version` | yes | Target Python version metadata. |
| `system_packages` | no | Extra distro packages installed with the image build. |
| `python_packages` | no | Exact Python requirements such as `requests==2.32.3`. |
| `node_packages` | no | Exact global Node.js packages such as `typescript@5.8.3`. |
| `env` | no | Non-secret default environment variables. |
| `user` | no | Default runtime user metadata. |
| `workdir` | no | Default working directory metadata. |

### Secrets

For managed bots created through the interactive menu, secrets are stored in a
sibling `.env` file inside `bots/<slug>/` instead of inline
`[[runtime.secret_refs]]` entries.

That means:

- `openclawenv.toml` keeps non-secret runtime configuration
- `bots/<slug>/.env` holds the local secret values or references
- generated Compose env files are derived from that sidecar data

## `[agent]`

The `[agent]` section describes the markdown files exposed to the agent.

| Field | Required | Purpose |
| --- | --- | --- |
| `agents_md` | yes | Main operating instructions. |
| `soul_md` | yes | Bot identity, values, or behavior framing. |
| `user_md` | yes | User-facing context or role description. |
| `identity_md` | no | Additional identity details. |
| `tools_md` | no | Tool usage guidance. |
| `memory_seed` | no | Seed memory content or a reference to `memory.md`. |

Each value can be provided in one of two forms:

- inline markdown content
- a relative path to a sibling `.md` file

Example:

```toml
[agent]
agents_md = "AGENTS.md"
soul_md = "SOUL.md"
user_md = "USER.md"
memory_seed = "memory.md"
```

For managed bots, OpenClaw-env-manager usually writes:

- `AGENTS.md`
- `SOUL.md`
- `USER.md`
- `IDENTITY.md`
- `TOOLS.md`
- `memory.md`

next to the manifest and stores only file references in `openclawenv.toml`.

## `[[skills]]`

Each `[[skills]]` entry defines one skill available to the generated
environment.

| Field | Required | Purpose |
| --- | --- | --- |
| `name` | yes | Stable skill identifier. |
| `description` | no | Human-readable summary. |
| `content` | no | Inline `SKILL.md` content. |
| `source` | no | External source reference such as `org/skill-name`. |
| `assets` | no | Optional inline text assets associated with the skill. |

Skills may be:

- fully inline
- source-backed placeholders
- discovered later from a running container snapshot

OpenClaw-env-manager also normalizes a mandatory baseline so the effective skill set always
contains:

- `deus-context-engine`
- `self-improving-agent`
- `skill-security-review`
- `freeride`
- `agent-browser-clawdbot`

## `[openclaw]`

The `[openclaw]` section defines the workspace layout and runtime configuration
used to generate `openclaw.json`.

| Field | Required | Purpose |
| --- | --- | --- |
| `agent_id` | yes | Stable agent identifier used in generated config. |
| `agent_name` | yes | Human-readable agent name used in generated artifacts. |
| `workspace` | yes | Workspace root path inside the image/runtime. |
| `state_dir` | yes | State/config root path inside the image/runtime. |

### `[openclaw.sandbox]`

The nested sandbox section controls the generated OpenClaw sandbox policy.

| Field | Required | Purpose |
| --- | --- | --- |
| `mode` | yes | Sandbox mode such as `workspace-write`. |
| `scope` | yes | Sandbox lifecycle scope such as `session`. |
| `workspace_access` | yes | Workspace visibility policy. |
| `network` | yes | Network access policy. |
| `read_only_root` | yes | Whether the root filesystem is read-only. |

## File Placement For Managed Bots

When a bot is created from the interactive menu, the generated directory usually
looks like this:

```text
bots/<bot-slug>/
  openclawenv.toml
  .env
  AGENTS.md
  SOUL.md
  USER.md
  IDENTITY.md
  TOOLS.md
  memory.md
  Dockerfile
  openclawenv.lock
  docker-compose-<bot>.yml
  .<bot>.env
```

In this layout:

- `openclawenv.toml` holds the declarative structure
- markdown files hold the actual long-form agent content
- `.env` stores bot-local secrets
- generated artifacts are written next to the manifest

## Validation Rules Worth Remembering

OpenClaw-env-manager enforces a few important rules when loading the manifest:

- `schema_version` must be supported
- required top-level sections must exist
- Python packages must be pinned in deterministic form
- Node.js packages must be pinned in deterministic form
- managed-bot secrets should live in the sibling `.env`
- markdown references must point to files relative to the manifest directory

## Related Files

- [Getting Started](getting-started.md)
- [Concepts](concepts.md)
- [API: Manifests](api/manifests.md)
