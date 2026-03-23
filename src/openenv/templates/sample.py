"""Sample manifest used by `clawopenenv init`."""

from __future__ import annotations

from textwrap import dedent


SAMPLE_MANIFEST = dedent(
    """\
    schema_version = 1

    [project]
    name = "research-agent"
    version = "0.1.0"
    description = "Example OpenClaw environment managed by OpenClawenv"
    runtime = "openclaw"

    [runtime]
    base_image = "python:3.12-slim"
    python_version = "3.12"
    system_packages = ["git", "curl", "chromium"]
    python_packages = ["requests==2.32.3", "rich==13.9.4"]
    node_packages = ["typescript@5.8.3"]
    env = { PYTHONUNBUFFERED = "1", OPENCLAWENV_PROJECT = "research-agent" }
    user = "agent"
    workdir = "/workspace"

    [[runtime.secret_refs]]
    name = "OPENAI_API_KEY"
    source = "env:OPENAI_API_KEY"
    required = true

    [agent]
    agents_md = \"\"\"
    # Agent Contract

    - Read `SOUL.md`, `USER.md`, and `memory.md` before responding.
    - Never expose secrets in chat.
    - Prefer reproducible commands over ad-hoc shell state.
    \"\"\"
    soul_md = \"\"\"
    # Soul

    Helpful, concise, and careful about security.
    \"\"\"
    user_md = \"\"\"
    # User

    Builds internal agent workflows for engineering teams.
    \"\"\"
    identity_md = \"\"\"
    # Identity

    You are the research agent for the OpenClawenv workspace.
    \"\"\"
    tools_md = \"\"\"
    # Tools

    Use local tools first. Escalate before destructive actions.
    \"\"\"
    memory_seed = [
      "Project starts from a deterministic Docker image.",
      "Secrets are injected at runtime from references only.",
    ]

    [[skills]]
    name = "deus-context-engine"
    description = "Always-installed skill referenced from catalog source deus-context-engine"
    source = "deus-context-engine"

    [[skills]]
    name = "self-improving-agent"
    description = "Always-installed skill referenced from catalog source self-improving-agent"
    source = "self-improving-agent"

    [[skills]]
    name = "skill-security-review"
    description = "Always-installed skill referenced from catalog source skill-security-review"
    source = "skill-security-review"

    [[skills]]
    name = "free-ride"
    description = "Always-installed skill referenced from catalog source freeride"
    source = "freeride"

    [[skills]]
    name = "agent-browser-clawdbot"
    description = "Always-installed skill referenced from catalog source agent-browser-clawdbot"
    source = "agent-browser-clawdbot"

    [[skills]]
    name = "incident-brief"
    description = "Prepare concise incident reports from logs and dashboards."
    content = \"\"\"
    ---
    name: incident-brief
    description: Prepare concise incident reports from logs and dashboards.
    ---

    1. Gather the most relevant telemetry.
    2. Summarize impact, timeline, and next actions.
    \"\"\"
    assets = { "templates/report.md" = "# Incident Report\\n\\n## Summary\\n" }

    [openclaw]
    agent_id = "main"
    agent_name = "Research Agent"
    workspace = "/opt/openclaw/workspace"
    state_dir = "/opt/openclaw"

    [openclaw.sandbox]
    mode = "workspace-write"
    scope = "session"
    workspace_access = "full"
    network = "none"
    read_only_root = false

    [openclaw.tools]
    allow = ["shell_command"]
    deny = []
    """
)
