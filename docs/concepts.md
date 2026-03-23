# Concepts

## Manifest First

`openclawenv.toml` is the canonical source of truth. It describes:

- project metadata
- runtime dependencies and defaults
- agent-facing markdown documents
- inline and referenced skills
- OpenClaw-specific runtime settings

## Deterministic Build Inputs

`openclawenv.lock` captures the resolved state needed to rebuild the environment.
That includes:

- the resolved base image reference with digest
- pinned Python and Node.js requirements
- the normalized manifest hash
- the rendered build payload snapshot

## Generated Artifacts

OpenClaw-env-manager can render and maintain several build outputs:

- `Dockerfile`
- bot-specific `docker-compose-<bot>.yml`
- bot-specific `.<bot>.env`
- shared `bots/all-bots-compose.yml`

The generated Docker image is built on top of an OpenClaw-compatible runtime and
adds project-specific workspace content, tools, and skill scanning.

## Managed Bots

When the CLI is launched without arguments, it opens an interactive menu for
managing bots under `bots/<slug>/`.

Managed bots keep:

- `openclawenv.toml` as the manifest
- `AGENTS.md`, `SOUL.md`, `USER.md`, `IDENTITY.md`, `TOOLS.md`, and `memory.md`
  as sibling documents
- `.env` as the local secret sidecar file

## Skill Lifecycle

Skills can come from inline content or source references. OpenClaw-env-manager also enforces
several mandatory skills so that security and operational baselines remain
present across generated environments.

The workflow includes:

- preflight scanning through the CLI
- build-time scanning in the Dockerfile
- runtime snapshotting from a running bot container

## API Reference Strategy

The API pages in this site are generated with `mkdocstrings`. That means the
reference stays close to the internal code structure and updates as the
package evolves.
