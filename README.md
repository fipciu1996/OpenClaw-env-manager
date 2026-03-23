# Open-env

[![CI](https://github.com/fipciu1996/Open-env/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/fipciu1996/Open-env/actions/workflows/ci.yml)
[![Coverage](https://fipciu1996.github.io/Open-env/coverage.svg)](https://fipciu1996.github.io/Open-env/coverage/)

Open-env is a Python CLI for defining an OpenClaw agent environment in one
declarative `openenv.toml` file and turning it into deterministic Docker
artifacts.

When run without arguments, the CLI opens an interactive terminal menu for bot
management.

It is inspired by Poetry's manifest-plus-lock workflow:

- `openenv.toml` describes intent
- `openenv.lock` captures deterministic build inputs
- `clawopenenv scan` runs an optional preflight security scan for materialized skills
- `clawopenenv export dockerfile` renders a standalone Dockerfile
- `clawopenenv export compose` renders a bot-specific docker-compose file
- `clawopenenv build` builds the image and enforces a build-time skill scan gate

## Table Of Contents

- [CI And Coverage](#ci-and-coverage)
- [Releases And PyPI](#releases-and-pypi)
- [Documentation](#documentation)
- [Host Prerequisites](#host-prerequisites)
  - [Windows](#windows)
  - [macOS](#macos)
  - [Linux](#linux)
  - [Notes](#notes)
- [V1 Scope](#v1-scope)
- [Manifest Shape](#manifest-shape)
- [CLI](#cli)
- [Makefile](#makefile)
- [Interactive Bot Menu](#interactive-bot-menu)
- [Generated Image Contents](#generated-image-contents)
- [Tests](#tests)

## CI And Coverage

GitHub Actions runs the test suite for every push to `main`, every pull request,
and on manual dispatch. A separate coverage job runs the tests under
`coverage.py`, uploads the raw reports as workflow artifacts, validates the
MkDocs build, and publishes the HTML coverage report plus a generated coverage
badge to GitHub Pages for pushes to `main`.

Once GitHub Pages is enabled for the repository with `Build and deployment`
configured to `GitHub Actions`, the published coverage site is available at
[fipciu1996.github.io/Open-env/coverage/](https://fipciu1996.github.io/Open-env/coverage/).

## Releases And PyPI

Package publication to PyPI is handled by
`.github/workflows/publish-pypi.yml`.

The release workflow is intentionally narrow:

- it runs only on pushed release tags matching `1.2.3` or `v1.2.3`
- it verifies that the tag version matches `[project].version` in
  `pyproject.toml`
- it builds both `sdist` and `wheel`
- it checks the generated distributions with `twine`
- it publishes to PyPI through Trusted Publishing with GitHub OIDC

Example release tag:

```bash
make install-hooks
make release-tag VERSION=1.0.1 TAG_MESSAGE="Open-env 1.0.1"
git push origin 1.0.1
```

Git does not provide a native `pre-tag` hook, so Open-env uses a practical
replacement:

- `python .github/scripts/create_release_tag.py <tag>` or
  `make release-tag VERSION=<tag>` updates `pyproject.toml` and `CHANGELOG.md`,
  creates a release commit, and only then creates the annotated tag
- `.githooks/pre-push` verifies that every pushed release tag still matches the
  package version and blocks the push when they diverge
- changelog entries are managed through `changelog-cli`, which is installed as
  part of `.[dev]`

To activate the repository-managed hooks locally:

```bash
make install-hooks
```

Useful `changelog-cli` commands:

```bash
changelog entry added --message "Describe a new feature"
changelog entry changed --message "Describe a behavior change"
changelog entry fixed --message "Describe a bug fix"
changelog current
```

Once the package is published, installation from PyPI is:

```bash
python -m pip install OpenClaw-env-manager
```

The installed console command is:

```bash
clawopenenv
```

Before the first release, configure a PyPI Trusted Publisher for:

- owner: `fipciu1996`
- repository: `Open-env`
- workflow: `.github/workflows/publish-pypi.yml`

## Documentation

Project documentation is generated with `MkDocs + mkdocstrings`. The `docs/`
directory holds narrative pages, while the API reference is generated directly
from `src/openenv/`.

The docs also include a dedicated reference page for the generated
`openenv.toml` structure, including the top-level sections, field meanings, and
managed-bot file layout.

Install the docs toolchain:

```bash
python -m pip install -e .[docs]
```

Build the docs locally:

```bash
python -m mkdocs build --strict
```

Run the local preview server:

```bash
python -m mkdocs serve
```

Equivalent `make` shortcuts:

```bash
make install-docs
make docs-build
make docs-serve
```

Versioned documentation publishing is configured for GitLab Pages in
`.gitlab-ci.yml`. The deployment model is:

- default branch: published at the root Pages URL
- other branches: published under `branch-<ref-slug>/`
- tags: published under `tag-<ref-slug>/`

This setup uses GitLab Pages parallel deployments through `pages.path_prefix`.
According to the current GitLab documentation, that feature is available on
GitLab Premium and Ultimate. Branch previews are configured to expire after
`30 days`, while the default-branch and tag deployments are kept indefinitely.

## Host Prerequisites

Before using Open-env on a workstation or CI runner, install:

- Docker with `docker compose` support
- Python `3.12+` with `pip`
- optionally `git`
- optionally `make` on Linux/macOS if you want to use the provided `Makefile`

Quick verification:

```bash
docker version
docker compose version
python --version
python -m pip --version
```

Expected result: Docker CLI is available, `docker compose` works, and Python is
at least `3.12`.

### Windows

1. Install Docker Desktop for Windows:
   [official Docker Desktop for Windows guide](https://docs.docker.com/desktop/setup/install/windows-install/).
2. Prefer the WSL 2 backend. Docker's current documentation requires WSL
   `2.1.5+` and a supported Windows 10/11 build.
3. Install Python `3.12+` from
   [python.org/downloads](https://www.python.org/downloads/) or through the
   Python Install Manager described in the
   [official Windows documentation](https://docs.python.org/3/using/windows.html).
4. Restart the terminal and verify:

```powershell
wsl --version
docker version
docker compose version
python --version
```

### macOS

1. Install Docker Desktop for Mac:
   [official Docker Desktop for Mac guide](https://docs.docker.com/desktop/setup/install/mac-install/).
2. Install Python `3.12+` from
   [python.org/downloads](https://www.python.org/downloads/). The official
   macOS installer is a `universal2` build and works on both Apple Silicon and
   Intel Macs.
3. See the
   [official Python on macOS guide](https://docs.python.org/3/using/mac.html)
   for installer details and shell path setup.
4. Verify:

```bash
docker version
docker compose version
python3 --version
python3 -m pip --version
```

### Linux

1. Install Docker Engine from the
   [official Docker Engine install overview](https://docs.docker.com/engine/install/)
   and pick your distribution-specific page there. If you prefer Docker
   Desktop and your distro is supported, see the
   [official Docker Desktop for Linux guide](https://docs.docker.com/desktop/setup/install/linux/).
2. For common distros, Docker maintains dedicated instructions for
   [Ubuntu](https://docs.docker.com/engine/install/ubuntu/) and
   [Debian](https://docs.docker.com/engine/install/debian/), and the install
   overview links the rest of the supported platforms.
3. Check whether your distro already ships Python `3.12+`:

```bash
python3 --version
```

4. If your distro Python is older than `3.12`, use a newer distro package or
   install CPython from the latest source release published on
   [python.org/downloads](https://www.python.org/downloads/), following the
   [official Unix installation guide](https://docs.python.org/3/using/unix.html).
5. Verify:

```bash
docker version
docker compose version
python3 --version
python3 -m pip --version
```

### Notes

- Open-env assumes a Docker environment with Compose available as
  `docker compose`.
- On Linux, the Python executable is often `python3` rather than `python`.
- Docker Desktop licensing can require a paid subscription in larger
  commercial organizations; check Docker's current terms before rolling it out
  company-wide.

## V1 Scope

Open-env v1 is intentionally narrow:

- OpenClaw-first
- Python-first
- one inline manifest
- Docker image output
- secret references only
- no session or auth state snapshotting

The current locker accepts exact Python requirements only:

- `package==version`
- `name @ URL`

It also accepts exact Node.js requirements only:

- `package@version`
- `@scope/package@version`

That constraint keeps the lockfile deterministic without shipping a full Python
dependency resolver in v1.

Open-env can also integrate with Cisco's
[Skill Scanner](https://github.com/cisco-ai-defense/skill-scanner), which the
upstream project describes as a best-effort scanner for agent skills with
static, behavioral, and optional LLM-based analysis.

Five catalog skills are treated as always installed defaults across manifests,
managed bots, and generated images:

- `deus-context-engine`
- `self-improving-agent`
- `skill-security-review`
- `freeride` (`free-ride` inside the workspace)
- `agent-browser-clawdbot`

## Manifest Shape

`openenv.toml` contains five top-level sections:

- `project`
- `runtime`
- `agent`
- `skills`
- `openclaw`

Example:

```toml
schema_version = 1

[project]
name = "ops-agent"
version = "1.2.3"
description = "Deterministic OpenClaw image for operations support"
runtime = "openclaw"

[runtime]
base_image = "python:3.12-slim"
python_version = "3.12"
system_packages = ["git", "curl", "chromium"]
python_packages = ["requests==2.32.3", "rich==13.9.4"]
node_packages = ["typescript@5.8.3"]
env = { PYTHONUNBUFFERED = "1" }
user = "agent"
workdir = "/workspace"

[[runtime.secret_refs]]
name = "OPENAI_API_KEY"
source = "env:OPENAI_API_KEY"
required = true

[agent]
agents_md = """# Agent Contract"""
soul_md = """# Soul"""
user_md = """# User"""
memory_seed = ["Remember the operating model."]

[[skills]]
name = "incident-brief"
description = "Prepare concise incident reports."
content = """
---
name: incident-brief
description: Prepare concise incident reports.
---
"""

[openclaw]
agent_id = "main"
agent_name = "Operations Agent"

[openclaw.sandbox]
mode = "workspace-write"
scope = "session"
workspace_access = "full"
network = "none"
read_only_root = false
```

The `agent` section supports both inline markdown content and relative `.md`
file references. For example, `agents_md = "AGENTS.md"` will load
`AGENTS.md` from the same directory as `openenv.toml`.

Even if they are not declared manually, Open-env normalizes manifests so that
`deus-context-engine`, `self-improving-agent`, `skill-security-review`,
`freeride`, and `agent-browser-clawdbot` remain present in the effective skill
set. `openenv init` writes them explicitly into the starter manifest.

## CLI

Create a starter manifest:

```bash
clawopenenv init
```

Open the interactive bot menu:

```bash
clawopenenv
```

Validate the manifest:

```bash
clawopenenv validate
```

Generate the lockfile:

```bash
clawopenenv lock
```

Run a skill security scan:

```bash
clawopenenv scan -- --policy strict --fail-on-severity high
```

Build the image with a stricter build-time scan policy:

```bash
clawopenenv build --scan-policy strict --scan-fail-on-severity medium
```

Export the Dockerfile:

```bash
clawopenenv export dockerfile --output Dockerfile
```

Export the bot compose file:

```bash
clawopenenv export compose
```

`clawopenenv export compose` also writes a sibling `Dockerfile`, so the generated
compose bundle can rebuild the bot image locally without any extra wiring.

Build the image:

```bash
clawopenenv build
```

`clawopenenv build` also writes a compose file named after the bot, for example
`docker-compose-operations-agent.yml`, next to the manifest.
When `runtime.base_image` is not pinned with `@sha256`, Open-env first checks
for the image locally and automatically tries `docker image pull <image>` if it
is missing before failing lock generation.

Module-oriented execution is also available through:

```bash
python -m clawopenenv
```

## Makefile

Common workflows are also available through `Makefile` targets:

```bash
make install
make install-dev
make install-scan
make test
make coverage
make coverage-html
make menu
make validate
make lock
make scan SCAN_ARGS="-- --policy strict --fail-on-severity high"
make dockerfile
make compose
make build
```

You can override defaults, for example:

```bash
make lock MANIFEST=examples/demo.openenv.toml LOCKFILE=examples/demo.openenv.lock
make dockerfile DOCKERFILE=build/Dockerfile
make build TAG=openenv/demo:dev
```

## Interactive Bot Menu

Running `clawopenenv` without parameters opens a menu that lets you:

- choose Polish or English as the interface language on entry
- list managed bots
- from the bot selection screen, generate a shared stack at
  `bots/all-bots-compose.yml` with one gateway and one bot service per managed
  bot
- open a listed bot and generate `openenv.lock`, `Dockerfile`, and bot-specific
  `docker-compose` artifacts
- open a listed bot and improve its `*.md` documents through OpenRouter
  tool calling, with the resulting markdown normalized to consistent English
- list running bots launched from `bots/<bot-slug>/docker-compose-*.yml`
- open a running bot and preview recent container logs
- open a running bot and create a skill snapshot, which inspects installed
  skills in the running container and updates `openenv.toml` with any new
  discoveries
- add a new bot by answering interactive questions about role, skill sources,
  dependencies, secrets, sites, and databases
- the interactive skill prompt only asks for additional skills, because
  `deus-context-engine`, `self-improving-agent`, `skill-security-review`,
  `freeride`, and `agent-browser-clawdbot` are always included automatically
- edit an existing bot and rewrite its stored manifest data
- delete an existing bot together with its stored manifest data

Managed bots are stored under `bots/<bot-slug>/openenv.toml`.
For bots created from the interactive menu, secret refs are stored in
`bots/<bot-slug>/.env` instead of `[[runtime.secret_refs]]` blocks inside the
manifest. Agent documents are stored as sibling markdown files such as
`bots/<bot-slug>/AGENTS.md`, `SOUL.md`, `USER.md`, `IDENTITY.md`, `TOOLS.md`,
and `memory.md`, while the manifest keeps only relative references to those
files. The OpenRouter-backed document improvement action looks for
`OPENROUTER_API_KEY` in the system environment first and then in the project
root `.env`. If the key is missing and the action is selected, the menu prompts
for it and writes `OPENROUTER_API_KEY=...` to the project root `.env`.

## Generated Image Contents

The generated image writes:

- the OpenClaw gateway/runtime itself by building on top of
  `alpine/openclaw:main`, so the resulting image can actually run
  `node dist/index.js gateway`
- the OpenClaw workspace files such as `AGENTS.md`, `SOUL.md`, and `USER.md`
- inline skills under `<workspace>/skills/<skill-name>/`
- a generated `openclaw.json`
- copies of `openenv.toml` and `openenv.lock` under `/opt/openenv`
- Python plus Node.js tooling available in the image, including `node`, `npm`,
  and `npx`
- exact `runtime.node_packages` installed globally with `npm install --global`
- the `agent-browser` CLI installed globally by default, followed by
  `agent-browser install` during image build so the browser runtime is prepared
- the `cisco-ai-skill-scanner==2.0.4` CLI installed in the image for in-container
  skill scanning
- the `freeride` skill installed from ClawHub into the real OpenClaw workspace
  and exposed through `~/.openclaw -> /opt/openclaw`, so `freeride auto` updates
  the same `openclaw.json` used by the container
- a build-time `skill-scanner scan-all` gate against `<workspace>/skills`, using
  `balanced` policy and failing on `high` severity by default

`runtime.base_image` is still preserved and pinned in `openenv.lock`, but it is
used as the sandbox/agent image inside the generated `openclaw.json`, not as
the outer gateway container base.

The tool can also generate a bot-specific OpenClaw-style compose file with
`openclaw-gateway` and `openclaw-cli` services, host-mounted config/workspace
directories, and a bot-specific env file such as `.operations-agent.env`. The
gateway service includes a `build:` section that rebuilds the local image from
the adjacent generated `Dockerfile`, and both services use the resulting tag
through `OPENCLAW_IMAGE`. When a canonical sidecar `bots/<bot-slug>/.env` file
exists, its secret values are merged into the generated compose env file
together with OpenClaw defaults such as image tag, ports, bind mode, and
workspace paths.

When `clawopenenv scan` is used, the CLI materializes skills to a temporary
directory and runs `skill-scanner scan-all ... --recursive` against that tree
as a local preflight check. During `docker build`, the generated Dockerfile also
runs `skill-scanner scan-all <workspace>/skills --recursive --check-overlap`,
so the image build fails when findings meet the configured severity threshold.
For already running bot containers, the interactive menu can also create a
skill snapshot by inspecting `<workspace>/skills` inside the container and
merging any newly discovered skills back into the bot manifest.
When `freeride` is present, the Docker build also runs
`npx clawhub@latest install freeride` plus `python -m pip install -e` for the
installed `free-ride` package before the skill scan gate. After container start,
set `OPENROUTER_API_KEY` and run `freeride auto` followed by
`openclaw gateway restart` if you want FreeRide to rewrite the active
OpenClaw model configuration.
By default, Docker builds also run `npm install -g agent-browser` and
`agent-browser install` to prepare browser automation, while the mandatory
`agent-browser-clawdbot` skill documents how agents should use that tool.
When using the exported Dockerfile directly, you can override the defaults with
Docker build args such as `OPENENV_SKILL_SCAN_POLICY=strict`,
`OPENENV_SKILL_SCAN_FORMAT=json`, and
`OPENENV_SKILL_SCAN_FAIL_ON_SEVERITY=medium`. Use `--keep-artifacts` if you
want to inspect the materialized skill bundle in `.openenv-scan/`.

Example GitHub Actions step for the exported Dockerfile:

```yaml
- name: Build Open-env image with skill scan gate
  run: |
    docker build \
      --file Dockerfile \
      --tag openenv/agent:ci \
      --build-arg OPENENV_SKILL_SCAN_POLICY=strict \
      --build-arg OPENENV_SKILL_SCAN_FAIL_ON_SEVERITY=medium \
      .
```

Secrets are never baked into the image. Sensitive values must be supplied at
runtime through the generated `.<bot-name>.env` file.

## Tests

Run the built-in unittest suite:

```bash
python -m unittest discover -s tests -t . -v
```

Generate a terminal coverage report:

```bash
python -m coverage run -m unittest discover -s tests -t . -v
python -m coverage report -m
```

Generate the HTML report under `htmlcov/`:

```bash
make coverage-html
```
