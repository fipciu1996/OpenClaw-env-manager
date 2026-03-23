"""Dockerfile generation for OpenClawenv."""

from __future__ import annotations

import json
from pathlib import PurePosixPath

from openenv.core.models import Lockfile, Manifest
from openenv.core.skills import FREERIDE_SKILL_NAME, FREERIDE_SKILL_SOURCE
from openenv.core.utils import encode_payload, stable_json_dumps


SKILL_SCANNER_REQUIREMENT = "cisco-ai-skill-scanner==2.0.4"
OPENCLAW_GATEWAY_RUNTIME_IMAGE = "alpine/openclaw:main"
DEFAULT_NODE_PACKAGES = ("nodejs", "npm")
DEFAULT_PYTHON_PACKAGES_APT = ("python3", "python3-pip", "bash")
DEFAULT_PYTHON_PACKAGES_APK = ("python3", "py3-pip", "bash")
DEFAULT_GLOBAL_NODE_TOOLS = ("agent-browser",)
DEFAULT_SKILL_SCAN_FORMAT = "summary"
DEFAULT_SKILL_SCAN_POLICY = "balanced"
DEFAULT_SKILL_SCAN_FAIL_ON_SEVERITY = "high"
DEFAULT_OPENCLAW_RUNTIME_USER = "node"
DEFAULT_OPENCLAW_RUNTIME_HOME = "/home/node"


def render_dockerfile(
    manifest: Manifest,
    lockfile: Lockfile,
    *,
    raw_manifest_text: str,
    raw_lock_text: str,
) -> str:
    """Render a standalone Dockerfile from a manifest and lockfile."""
    sandbox_reference = lockfile.base_image["resolved_reference"]
    payload = _render_payload(
        manifest,
        raw_manifest_text=raw_manifest_text,
        raw_lock_text=raw_lock_text,
        base_reference=sandbox_reference,
    )
    payload_b64 = encode_payload(payload)
    lines: list[str] = [
        "# syntax=docker/dockerfile:1",
        f"FROM {OPENCLAW_GATEWAY_RUNTIME_IMAGE}",
        f'LABEL org.opencontainers.image.title="{_escape_label(manifest.project.name)}"',
        f'LABEL org.opencontainers.image.version="{_escape_label(manifest.project.version)}"',
        f'LABEL io.openclawenv.manifest-hash="{lockfile.manifest_hash}"',
        f'LABEL io.openclawenv.sandbox-image="{_escape_label(sandbox_reference)}"',
        "ENV PYTHONDONTWRITEBYTECODE=1",
        "USER root",
    ]
    for key, value in sorted(manifest.runtime.env.items()):
        lines.append(f"ENV {key}={json.dumps(value)}")
    lines.extend(_package_install_lines(manifest.runtime.system_packages))
    lines.extend(_python_binary_link_lines())
    lines.append(
        "RUN if ! command -v npx >/dev/null 2>&1; then "
        "printf '%s\\n' '#!/bin/sh' 'exec npm exec --yes -- \"$@\"' "
        "> /usr/local/bin/npx && chmod +x /usr/local/bin/npx; fi"
    )
    requirements = [
        SKILL_SCANNER_REQUIREMENT,
        *(_python_package_argument(package) for package in lockfile.python_packages),
    ]
    lines.append(
        "RUN python -m pip install --no-cache-dir " + " ".join(requirements)
    )
    node_requirements = _global_node_requirements(lockfile)
    if node_requirements:
        lines.append(
            "RUN npm install --global --no-fund --no-update-notifier "
            + " ".join(node_requirements)
        )
        lines.append("RUN agent-browser install")
    lines.extend(_state_link_lines(manifest))
    lines.append("RUN mkdir -p /opt/openclawenv")
    lines.append(
        'RUN ["python", "-c", '
        f'{json.dumps(_payload_writer_script(payload_b64))}'
        "]"
    )
    lines.extend(_freeride_install_lines(manifest))
    lines.extend(_skill_scan_lines(manifest))
    lines.extend(_runtime_permission_lines(manifest))
    lines.append(f"USER {DEFAULT_OPENCLAW_RUNTIME_USER}")
    return "\n".join(lines) + "\n"


def _render_payload(
    manifest: Manifest,
    *,
    raw_manifest_text: str,
    raw_lock_text: str,
    base_reference: str,
) -> dict[str, object]:
    """Assemble the file payload embedded into the generated Dockerfile."""
    files = manifest.workspace_files()
    files[manifest.openclaw.config_path()] = (
        stable_json_dumps(manifest.openclaw.to_openclaw_json(base_reference), indent=2)
        + "\n"
    )
    files[str(PurePosixPath("/opt/openclawenv") / "openclawenv.toml")] = raw_manifest_text
    files[str(PurePosixPath("/opt/openclawenv") / "openclawenv.lock")] = raw_lock_text
    files = dict(sorted(files.items()))
    return {"directories": _directories_for(files), "files": files}


def _directories_for(files: dict[str, str]) -> list[str]:
    """Return the unique parent directories that must exist before payload extraction."""
    directories = {str(PurePosixPath(path).parent) for path in files}
    return sorted(directory for directory in directories if directory not in {".", ""})


def _python_package_argument(package: dict[str, str]) -> str:
    """Render one locked Python package entry as a `pip install` argument."""
    if package["kind"] == "direct":
        return package["requirement"]
    return f"{package['name']}=={package['version']}"


def _system_packages(packages: list[str]) -> str:
    """Merge caller packages with default Node requirements while preserving order."""
    ordered: list[str] = []
    seen: set[str] = set()
    for package in [*packages, *DEFAULT_NODE_PACKAGES]:
        if package not in seen:
            seen.add(package)
            ordered.append(package)
    return " ".join(ordered)


def _package_install_lines(packages: list[str]) -> list[str]:
    """Render OS package installation commands for both Debian-like and Alpine images."""
    apt_packages = _system_packages([*packages, *DEFAULT_PYTHON_PACKAGES_APT])
    apk_packages = _apk_system_packages(packages)
    return [
        "RUN if command -v apt-get >/dev/null 2>&1; then "
        "apt-get update && apt-get install -y --no-install-recommends "
        f"{apt_packages} && rm -rf /var/lib/apt/lists/*; "
        "elif command -v apk >/dev/null 2>&1; then "
        f"apk add --no-cache {apk_packages}; "
        "else echo 'Unsupported base image: no apt-get or apk available.' >&2; exit 1; fi"
    ]


def _apk_system_packages(packages: list[str]) -> str:
    """Return the deduplicated package list used by the Alpine installation branch."""
    ordered: list[str] = []
    seen: set[str] = set()
    for package in [*packages, *DEFAULT_NODE_PACKAGES, *DEFAULT_PYTHON_PACKAGES_APK]:
        if package not in seen:
            seen.add(package)
            ordered.append(package)
    return " ".join(ordered)


def _python_binary_link_lines() -> list[str]:
    """Render compatibility symlinks so `python` and `pip` are always available."""
    return [
        "RUN mkdir -p /usr/local/bin && "
        "if ! command -v python >/dev/null 2>&1 && command -v python3 >/dev/null 2>&1; then "
        'ln -sf "$(command -v python3)" /usr/local/bin/python; fi',
        "RUN mkdir -p /usr/local/bin && "
        "if ! command -v pip >/dev/null 2>&1 && command -v pip3 >/dev/null 2>&1; then "
        'ln -sf "$(command -v pip3)" /usr/local/bin/pip; fi',
    ]


def _global_node_requirements(lockfile: Lockfile) -> list[str]:
    """Return the default and user-requested global Node tools for the image."""
    ordered = list(DEFAULT_GLOBAL_NODE_TOOLS)
    seen = set(ordered)
    for package in lockfile.node_packages:
        requirement = package["requirement"]
        if requirement not in seen:
            seen.add(requirement)
            ordered.append(requirement)
    return ordered


def _payload_writer_script(payload_b64: str) -> str:
    """Build the inline Python extraction script embedded in the Dockerfile."""
    return (
        "import base64, json, pathlib; "
        f"payload=json.loads(base64.b64decode({payload_b64!r}).decode('utf-8')); "
        "[pathlib.Path(directory).mkdir(parents=True, exist_ok=True) "
        "for directory in payload['directories']]; "
        "[pathlib.Path(path).write_text(content, encoding='utf-8') "
        "for path, content in payload['files'].items()]"
    )


def _skill_scan_lines(manifest: Manifest) -> list[str]:
    """Render build-time skill scanning commands when the manifest contains skills."""
    if not manifest.skills:
        return []
    skills_root = PurePosixPath(manifest.openclaw.workspace) / "skills"
    return [
        f"ARG OPENCLAWENV_SKILL_SCAN_FORMAT={DEFAULT_SKILL_SCAN_FORMAT}",
        f"ARG OPENCLAWENV_SKILL_SCAN_POLICY={DEFAULT_SKILL_SCAN_POLICY}",
        "ARG OPENCLAWENV_SKILL_SCAN_FAIL_ON_SEVERITY="
        f"{DEFAULT_SKILL_SCAN_FAIL_ON_SEVERITY}",
        "RUN if [ -d "
        f'"{skills_root}"'
        " ] && find "
        f'"{skills_root}"'
        " -mindepth 1 -maxdepth 1 -type d -print -quit | grep -q .; then "
        "skill-scanner scan-all "
        f'"{skills_root}"'
        ' --recursive --check-overlap --format "$OPENCLAWENV_SKILL_SCAN_FORMAT"'
        ' --policy "$OPENCLAWENV_SKILL_SCAN_POLICY"'
        ' --fail-on-severity "$OPENCLAWENV_SKILL_SCAN_FAIL_ON_SEVERITY"; '
        "else echo 'No skills to scan; skipping skill-scanner.'; fi",
    ]


def _state_link_lines(manifest: Manifest) -> list[str]:
    """Render symlinks that expose the OpenClaw state directory under common home paths."""
    state_dir = manifest.openclaw.state_dir
    lines = [
        "RUN mkdir -p "
        f'"{state_dir}" /root "{DEFAULT_OPENCLAW_RUNTIME_HOME}" '
        f'&& ln -sfn "{state_dir}" /root/.openclaw '
        f'&& ln -sfn "{state_dir}" "{DEFAULT_OPENCLAW_RUNTIME_HOME}/.openclaw"'
    ]
    if manifest.runtime.user not in {"root", DEFAULT_OPENCLAW_RUNTIME_USER}:
        lines.append(
            "RUN if id -u "
            f'"{manifest.runtime.user}"'
            " >/dev/null 2>&1; then mkdir -p "
            f'"/home/{manifest.runtime.user}" && ln -sfn "{state_dir}" '
            f'"/home/{manifest.runtime.user}/.openclaw"; fi'
        )
    return lines


def _freeride_install_lines(manifest: Manifest) -> list[str]:
    """Render the special installation steps required for the mandatory FreeRide skill."""
    if not _has_freeride_skill(manifest):
        return []
    skill_path = PurePosixPath(manifest.openclaw.workspace) / "skills" / FREERIDE_SKILL_NAME
    return [
        f'RUN rm -rf "{skill_path}" && npx clawhub@latest install {FREERIDE_SKILL_SOURCE}',
        f'RUN python -m pip install --no-cache-dir -e "{skill_path}"',
    ]


def _runtime_permission_lines(manifest: Manifest) -> list[str]:
    """Render the final directory ownership adjustments for the OpenClaw runtime user."""
    return [
        "RUN mkdir -p "
        f'"{manifest.runtime.workdir}" && '
        "if id -u "
        f'"{DEFAULT_OPENCLAW_RUNTIME_USER}"'
        " >/dev/null 2>&1; then chown -R "
        f"{DEFAULT_OPENCLAW_RUNTIME_USER}:{DEFAULT_OPENCLAW_RUNTIME_USER} "
        f'"{manifest.openclaw.state_dir}" "{manifest.runtime.workdir}"; fi'
    ]


def _has_freeride_skill(manifest: Manifest) -> bool:
    """Return whether the manifest includes the FreeRide skill by source or workspace name."""
    return any(
        skill.source == FREERIDE_SKILL_SOURCE or skill.name == FREERIDE_SKILL_NAME
        for skill in manifest.skills
    )


def _escape_label(value: str) -> str:
    """Escape Docker label values so they can be embedded safely in the Dockerfile."""
    return value.replace("\\", "\\\\").replace('"', '\\"')
