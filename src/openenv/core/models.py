"""Domain models for OpenClawenv manifests and locks."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any

from openenv.core.utils import rewrite_openclaw_home_paths, sha256_text


@dataclass(slots=True)
class ProjectConfig:
    """Project-level metadata stored in the manifest."""

    name: str
    version: str
    description: str
    runtime: str

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation used for hashing and export."""
        return {
            "description": self.description,
            "name": self.name,
            "runtime": self.runtime,
            "version": self.version,
        }


@dataclass(slots=True)
class SecretRef:
    """Reference to a secret that must be provided from the runtime environment."""

    name: str
    source: str
    required: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Return the canonical dictionary form emitted into snapshots and lockfiles."""
        return {
            "name": self.name,
            "required": self.required,
            "source": self.source,
        }


@dataclass(slots=True)
class AccessConfig:
    """Human-readable notes about external systems the bot may need to access."""

    websites: list[str] = field(default_factory=list)
    databases: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize access metadata for manifests, snapshots, and documentation."""
        return {
            "databases": list(self.databases),
            "notes": list(self.notes),
            "websites": list(self.websites),
        }


@dataclass(slots=True)
class RuntimeConfig:
    """Container runtime requirements that describe the bot sandbox image."""

    base_image: str
    python_version: str
    system_packages: list[str] = field(default_factory=list)
    python_packages: list[str] = field(default_factory=list)
    node_packages: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    user: str = "root"
    workdir: str = "/workspace"
    secret_refs: list[SecretRef] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize runtime settings in a deterministic order for hashing and export."""
        return {
            "base_image": self.base_image,
            "env": dict(sorted(self.env.items())),
            "node_packages": list(self.node_packages),
            "python_packages": list(self.python_packages),
            "python_version": self.python_version,
            "secret_refs": [secret.to_dict() for secret in self.secret_refs],
            "system_packages": list(self.system_packages),
            "user": self.user,
            "workdir": self.workdir,
        }


@dataclass(slots=True)
class AgentConfig:
    """Inline or referenced markdown documents that define the bot persona and rules."""

    agents_md: str
    soul_md: str
    user_md: str
    identity_md: str | None = None
    tools_md: str | None = None
    memory_seed: list[str] = field(default_factory=list)
    agents_md_ref: str | None = None
    soul_md_ref: str | None = None
    user_md_ref: str | None = None
    identity_md_ref: str | None = None
    tools_md_ref: str | None = None
    memory_seed_ref: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize the agent documents using their loaded text content."""
        data: dict[str, Any] = {
            "agents_md": self.agents_md,
            "memory_seed": list(self.memory_seed),
            "soul_md": self.soul_md,
            "user_md": self.user_md,
        }
        if self.identity_md is not None:
            data["identity_md"] = self.identity_md
        if self.tools_md is not None:
            data["tools_md"] = self.tools_md
        return data


@dataclass(slots=True)
class SkillConfig:
    """A single skill bundled into the bot workspace."""

    name: str
    description: str
    content: str | None = None
    source: str | None = None
    assets: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the declarative skill definition as it should appear in the manifest."""
        data: dict[str, Any] = {
            "assets": dict(sorted(self.assets.items())),
            "description": self.description,
            "name": self.name,
        }
        if self.content is not None:
            data["content"] = self.content
        if self.source is not None:
            data["source"] = self.source
        return data

    def rendered_content(
        self,
        *,
        state_dir: str | None = None,
        workspace: str | None = None,
    ) -> str:
        """Return the effective `SKILL.md` text, optionally rewritten for a target runtime.

        Referenced catalog skills are materialized into a placeholder `SKILL.md` so the
        build pipeline, scanners, and snapshots can treat inline and external skills
        uniformly.
        """
        if self.content is not None:
            rendered = self.content
        else:
            source = self.source or "unknown"
            rendered = (
                "---\n"
                f"name: {self.name}\n"
                f"description: {self.description}\n"
                f"source: {source}\n"
                "---\n\n"
                "This skill is referenced from an external catalog.\n\n"
                f"Suggested install command:\n`clawhub install {source}`\n"
            )
        if state_dir is None or workspace is None:
            return rendered
        return rewrite_openclaw_home_paths(
            rendered,
            state_dir=state_dir,
            workspace=workspace,
        )

    def snapshot(
        self,
        *,
        state_dir: str | None = None,
        workspace: str | None = None,
    ) -> dict[str, Any]:
        """Return a stable content hash snapshot of the rendered skill and its assets."""
        return {
            "assets": {
                path: sha256_text(
                    rewrite_openclaw_home_paths(
                        content,
                        state_dir=state_dir,
                        workspace=workspace,
                    )
                    if state_dir is not None and workspace is not None
                    else content
                )
                for path, content in sorted(self.assets.items())
            },
            "content_sha256": sha256_text(
                self.rendered_content(state_dir=state_dir, workspace=workspace)
            ),
            "description": self.description,
            "name": self.name,
            "source": self.source,
        }


@dataclass(slots=True)
class SandboxConfig:
    """OpenClaw sandbox policy applied to the agent container."""

    mode: str = "workspace-write"
    scope: str = "session"
    workspace_access: str = "full"
    network: str = "none"
    read_only_root: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Serialize the sandbox policy using manifest-oriented field names."""
        return {
            "mode": self.mode,
            "network": self.network,
            "read_only_root": self.read_only_root,
            "scope": self.scope,
            "workspace_access": self.workspace_access,
        }


@dataclass(slots=True)
class OpenClawConfig:
    """OpenClaw-specific runtime layout and tool restrictions for a bot."""

    agent_id: str
    agent_name: str
    workspace: str = "/opt/openclaw/workspace"
    state_dir: str = "/opt/openclaw"
    tools_allow: list[str] = field(default_factory=list)
    tools_deny: list[str] = field(default_factory=list)
    sandbox: SandboxConfig = field(default_factory=SandboxConfig)

    def config_path(self) -> str:
        """Return the on-disk path of the generated `openclaw.json` file."""
        return str(PurePosixPath(self.state_dir) / "openclaw.json")

    def agent_dir(self) -> str:
        """Return the OpenClaw agent directory used by the gateway runtime."""
        return str(PurePosixPath(self.state_dir) / "agents" / self.agent_id / "agent")

    def to_dict(self) -> dict[str, Any]:
        """Serialize OpenClaw configuration using manifest field names."""
        return {
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "sandbox": self.sandbox.to_dict(),
            "state_dir": self.state_dir,
            "tools_allow": list(self.tools_allow),
            "tools_deny": list(self.tools_deny),
            "workspace": self.workspace,
        }

    def to_openclaw_json(self, image_reference: str) -> dict[str, Any]:
        """Render the `openclaw.json` payload expected by the OpenClaw gateway."""
        sandbox = {
            "mode": self.sandbox.mode,
            "scope": self.sandbox.scope,
            "workspaceAccess": self.sandbox.workspace_access,
            "docker": {
                "image": image_reference,
                "network": self.sandbox.network,
                "readOnlyRoot": self.sandbox.read_only_root,
            },
        }
        data: dict[str, Any] = {
            "agents": {
                "defaults": {
                    "workspace": self.workspace,
                    "sandbox": sandbox,
                },
                "list": [
                    {
                        "id": self.agent_id,
                        "name": self.agent_name,
                        "workspace": self.workspace,
                        "agentDir": self.agent_dir(),
                    }
                ],
            }
        }
        if self.tools_allow or self.tools_deny:
            data["agents"]["defaults"]["tools"] = {
                "allow": self.tools_allow,
                "deny": self.tools_deny,
            }
        return data


@dataclass(slots=True)
class Manifest:
    """Fully parsed OpenClawenv manifest with all defaults, refs, and skills materialized."""

    schema_version: int
    project: ProjectConfig
    runtime: RuntimeConfig
    agent: AgentConfig
    skills: list[SkillConfig]
    openclaw: OpenClawConfig
    access: AccessConfig = field(default_factory=AccessConfig)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the manifest to a deterministic dictionary representation."""
        data = {
            "agent": self.agent.to_dict(),
            "openclaw": self.openclaw.to_dict(),
            "project": self.project.to_dict(),
            "runtime": self.runtime.to_dict(),
            "schema_version": self.schema_version,
            "skills": [skill.to_dict() for skill in self.skills],
        }
        if self.access.websites or self.access.databases or self.access.notes:
            data["access"] = self.access.to_dict()
        return data

    def workspace_files(self) -> dict[str, str]:
        """Return every file that must be written into the bot workspace at build time.

        The returned mapping already includes path rewriting for skills so hard-coded home
        references are converted to the runtime-specific OpenClaw directories.
        """
        files: dict[str, str] = {
            str(PurePosixPath(self.openclaw.workspace) / "AGENTS.md"): self.agent.agents_md,
            str(PurePosixPath(self.openclaw.workspace) / "SOUL.md"): self.agent.soul_md,
            str(PurePosixPath(self.openclaw.workspace) / "USER.md"): self.agent.user_md,
        }
        if self.agent.identity_md is not None:
            files[str(PurePosixPath(self.openclaw.workspace) / "IDENTITY.md")] = (
                self.agent.identity_md
            )
        if self.agent.tools_md is not None:
            files[str(PurePosixPath(self.openclaw.workspace) / "TOOLS.md")] = (
                self.agent.tools_md
            )
        if self.agent.memory_seed:
            files[str(PurePosixPath(self.openclaw.workspace) / "memory.md")] = "\n".join(
                self.agent.memory_seed
            ).strip() + "\n"
        for skill in self.skills:
            skill_root = PurePosixPath(self.openclaw.workspace) / "skills" / skill.name
            files[str(skill_root / "SKILL.md")] = skill.rendered_content(
                state_dir=self.openclaw.state_dir,
                workspace=self.openclaw.workspace,
            )
            for relative_path, content in sorted(skill.assets.items()):
                files[str(skill_root / relative_path)] = rewrite_openclaw_home_paths(
                    content,
                    state_dir=self.openclaw.state_dir,
                    workspace=self.openclaw.workspace,
                )
        return dict(sorted(files.items()))

    def source_snapshot(self) -> dict[str, Any]:
        """Return a stable snapshot of the manifest inputs used to compute the lockfile."""
        return {
            "agent_files": {
                path: sha256_text(content)
                for path, content in self.workspace_files().items()
            },
            "openclaw": self.openclaw.to_dict(),
            "project": self.project.to_dict(),
            "runtime": {
                "base_image": self.runtime.base_image,
                "env": dict(sorted(self.runtime.env.items())),
                "node_packages": list(self.runtime.node_packages),
                "python_packages": list(self.runtime.python_packages),
                "python_version": self.runtime.python_version,
                "secret_refs": [secret.to_dict() for secret in self.runtime.secret_refs],
                "system_packages": list(self.runtime.system_packages),
                "user": self.runtime.user,
                "workdir": self.runtime.workdir,
            },
            "access": self.access.to_dict(),
            "skills": [
                skill.snapshot(
                    state_dir=self.openclaw.state_dir,
                    workspace=self.openclaw.workspace,
                )
                for skill in self.skills
            ],
        }


@dataclass(slots=True)
class Lockfile:
    """Resolved, deterministic artifact describing the build inputs of a manifest."""

    lock_version: int
    manifest_hash: str
    base_image: dict[str, Any]
    python_packages: list[dict[str, Any]]
    node_packages: list[dict[str, Any]]
    system_packages: list[str]
    source_snapshot: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Serialize the lockfile in the canonical structure written to disk."""
        return {
            "base_image": self.base_image,
            "lock_version": self.lock_version,
            "manifest_hash": self.manifest_hash,
            "node_packages": self.node_packages,
            "python_packages": self.python_packages,
            "source_snapshot": self.source_snapshot,
            "system_packages": self.system_packages,
        }
