"""Dockerfile generation for OpenClawenv."""

from __future__ import annotations

import json
from pathlib import PurePosixPath

from openenv.core.models import Lockfile, Manifest
from openenv.core.skills import catalog_install_dir_name, catalog_skill_specs
from openenv.core.utils import encode_payload, stable_json_dumps


SKILL_SCANNER_REQUIREMENT = "cisco-ai-skill-scanner==2.0.4"
OPENCLAW_GATEWAY_RUNTIME_IMAGE = "ghcr.io/openclaw/openclaw:latest"
DEFAULT_NODE_PACKAGES = ("nodejs", "npm")
DEFAULT_PYTHON_PACKAGES_APT = ("python3", "python3-pip", "python3-venv", "bash")
DEFAULT_PYTHON_PACKAGES_APK = ("python3", "py3-pip", "py3-virtualenv", "bash")
DEFAULT_GLOBAL_NODE_TOOLS = ("agent-browser",)
DEFAULT_SKILL_SCAN_FORMAT = "summary"
DEFAULT_SKILL_SCAN_POLICY = "balanced"
DEFAULT_SKILL_SCAN_FAIL_ON_SEVERITY = "high"
DEFAULT_OPENCLAW_RUNTIME_USER = "node"
DEFAULT_OPENCLAW_RUNTIME_HOME = "/home/node"
ROOT_RUNTIME_USER = "root"
ROOT_RUNTIME_HOME = "/root"
DEFAULT_PYTHON_VENV_PATH = "/opt/openclawenv/.venv"
DEFAULT_OPENCLAW_DOCKER_GPG_FINGERPRINT = "9DC858229FC7DD38854AE2D88D81803C0EBFCD88"
CLAWHUB_NPX_PACKAGE = "clawhub@latest"


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
        image_reference="${OPENCLAW_IMAGE}",
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
    lines.extend(_python_venv_lines())
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
    lines.extend(_optional_browser_install_lines())
    lines.extend(_optional_docker_cli_install_lines())
    lines.extend(_state_link_lines(manifest))
    lines.append("RUN mkdir -p /opt/openclawenv")
    lines.append(
        'RUN ["python", "-c", '
        f'{json.dumps(_payload_writer_script(payload_b64))}'
        "]"
    )
    lines.extend(_catalog_skill_install_lines(manifest))
    lines.extend(_skill_scan_lines(manifest))
    lines.extend(_runtime_permission_lines(manifest))
    lines.append(f"USER {_effective_runtime_user(manifest)}")
    return "\n".join(lines) + "\n"


def render_runtime_payload(
    manifest: Manifest,
    lockfile: Lockfile,
    *,
    raw_manifest_text: str,
    raw_lock_text: str,
) -> dict[str, object]:
    """Return the file payload embedded into the runtime image."""
    return _render_payload(
        manifest,
        raw_manifest_text=raw_manifest_text,
        raw_lock_text=raw_lock_text,
        image_reference="${OPENCLAW_IMAGE}",
    )


def _render_payload(
    manifest: Manifest,
    *,
    raw_manifest_text: str,
    raw_lock_text: str,
    image_reference: str,
) -> dict[str, object]:
    """Assemble the file payload embedded into the generated Dockerfile."""
    files = manifest.workspace_files()
    files[manifest.openclaw.config_path()] = (
        stable_json_dumps(manifest.openclaw.to_openclaw_json(image_reference), indent=2)
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


def _python_venv_lines() -> list[str]:
    """Create and activate an image-local virtualenv for Python package installation."""
    return [
        "RUN python -m venv "
        f'"{DEFAULT_PYTHON_VENV_PATH}"'
        " 2>/dev/null || python -m virtualenv "
        f'"{DEFAULT_PYTHON_VENV_PATH}"',
        f'ENV VIRTUAL_ENV="{DEFAULT_PYTHON_VENV_PATH}"',
        f'ENV PATH="{DEFAULT_PYTHON_VENV_PATH}/bin:$PATH"',
    ]


def _optional_browser_install_lines() -> list[str]:
    """Render opt-in Playwright browser installation steps for the wrapper image."""
    return [
        'ARG OPENCLAW_INSTALL_BROWSER=""',
        "RUN if [ -n \"$OPENCLAW_INSTALL_BROWSER\" ]; then "
        "if ! command -v apt-get >/dev/null 2>&1; then "
        "echo 'OPENCLAW_INSTALL_BROWSER requires an apt-get based image.' >&2; exit 1; "
        "fi && "
        "apt-get update && "
        "DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends xvfb && "
        "mkdir -p /home/node/.cache/ms-playwright && "
        "PLAYWRIGHT_BROWSERS_PATH=/home/node/.cache/ms-playwright "
        "node /app/node_modules/playwright-core/cli.js install --with-deps chromium && "
        "chown -R node:node /home/node/.cache/ms-playwright; "
        "fi",
    ]


def _optional_docker_cli_install_lines() -> list[str]:
    """Render opt-in Docker CLI installation steps for sandbox-enabled deployments."""
    return [
        'ARG OPENCLAW_INSTALL_DOCKER_CLI=""',
        f'ARG OPENCLAW_DOCKER_GPG_FINGERPRINT="{DEFAULT_OPENCLAW_DOCKER_GPG_FINGERPRINT}"',
        "RUN if [ -n \"$OPENCLAW_INSTALL_DOCKER_CLI\" ]; then "
        "if ! command -v apt-get >/dev/null 2>&1; then "
        "echo 'OPENCLAW_INSTALL_DOCKER_CLI requires an apt-get based image.' >&2; exit 1; "
        "fi && "
        "apt-get update && "
        "DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "
        "ca-certificates curl gnupg && "
        "install -m 0755 -d /etc/apt/keyrings && "
        "curl -fsSL https://download.docker.com/linux/debian/gpg -o /tmp/docker.gpg.asc && "
        "expected_fingerprint=\"$(printf '%s' \"$OPENCLAW_DOCKER_GPG_FINGERPRINT\" | tr '[:lower:]' '[:upper:]' | tr -d '[:space:]')\" && "
        "actual_fingerprint=\"$(gpg --batch --show-keys --with-colons /tmp/docker.gpg.asc | awk -F: '$1 == \\\"fpr\\\" { print toupper($10); exit }')\" && "
        "if [ -z \"$actual_fingerprint\" ] || [ \"$actual_fingerprint\" != \"$expected_fingerprint\" ]; then "
        "echo \"ERROR: Docker apt key fingerprint mismatch (expected $expected_fingerprint, got ${actual_fingerprint:-<empty>})\" >&2; exit 1; "
        "fi && "
        "gpg --dearmor -o /etc/apt/keyrings/docker.gpg /tmp/docker.gpg.asc && "
        "rm -f /tmp/docker.gpg.asc && "
        "chmod a+r /etc/apt/keyrings/docker.gpg && "
        "printf 'deb [arch=%s signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian bookworm stable\\n' "
        "\"$(dpkg --print-architecture)\" > /etc/apt/sources.list.d/docker.list && "
        "apt-get update && "
        "DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "
        "docker-ce-cli docker-compose-plugin; "
        "fi",
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
        f'"{state_dir}" "{ROOT_RUNTIME_HOME}" "{DEFAULT_OPENCLAW_RUNTIME_HOME}" '
        f'&& ln -sfn "{state_dir}" "{ROOT_RUNTIME_HOME}/.openclaw" '
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


def _catalog_skill_install_lines(manifest: Manifest) -> list[str]:
    """Render build-time installation steps for skills sourced from an external catalog."""
    workdir = manifest.openclaw.workspace
    lines: list[str] = []
    for skill_name, source in catalog_skill_specs(manifest.skills):
        skill_path = PurePosixPath(workdir) / "skills" / skill_name
        installed_name = catalog_install_dir_name(source)
        lines.append(
            "RUN "
            + _catalog_skill_install_script(
                source=source,
                workdir=workdir,
                skill_path=skill_path,
                installed_name=installed_name,
            )
        )
    return lines


def _runtime_permission_lines(manifest: Manifest) -> list[str]:
    """Render the final directory ownership adjustments for the OpenClaw runtime user."""
    runtime_user = _effective_runtime_user(manifest)
    command = "RUN mkdir -p " f'"{manifest.runtime.workdir}"'
    if runtime_user != ROOT_RUNTIME_USER:
        command += (
            " && if id -u "
            f'"{runtime_user}"'
            " >/dev/null 2>&1; then chown -R "
            f"{runtime_user}:{runtime_user} "
            f'"{manifest.openclaw.state_dir}" "{manifest.runtime.workdir}"; fi'
        )
    return [command]


def _effective_runtime_user(manifest: Manifest) -> str:
    """Return the runtime user supported by the generated OpenClaw wrapper image."""
    if manifest.runtime.user.strip().casefold() == ROOT_RUNTIME_USER:
        return ROOT_RUNTIME_USER
    return DEFAULT_OPENCLAW_RUNTIME_USER


def _clawhub_install_command(source: str, workdir: str) -> str:
    """Return the ClawHub install command used for catalog-backed skills."""
    workdir_json = json.dumps(workdir)
    source_json = json.dumps(source)
    return (
        "npx --yes "
        f"{CLAWHUB_NPX_PACKAGE} install {source_json} --workdir {workdir_json} "
        "--force --no-input"
    )


def _catalog_skill_install_script(
    *,
    source: str,
    workdir: str,
    skill_path: PurePosixPath,
    installed_name: str,
) -> str:
    """Return a resilient shell script that installs a catalog skill or keeps its placeholder."""
    skill_md = skill_path / "SKILL.md"
    install_root_var = "openclawenv_install_root"
    installed_root = f'${install_root_var}/skills/{installed_name}'
    cleanup_targets = _rm_target_arguments(skill_path, PurePosixPath(workdir) / "skills" / installed_name)
    skills_root = json.dumps(str(PurePosixPath(workdir) / "skills"))
    skill_md_json = json.dumps(str(skill_md))
    placeholder_marker = json.dumps("This skill is referenced from an external catalog.")
    install_command = _clawhub_install_command(source, f"${install_root_var}")
    install_warning = json.dumps(
        f"WARNING: ClawHub install for {source!r} did not materialize an expected skill directory; "
        f"keeping placeholder at {skill_path}."
    )
    install_error = json.dumps(
        f"ERROR: ClawHub install for {source!r} did not materialize an expected skill directory and "
        f"no placeholder exists at {skill_path}."
    )
    source_warning = json.dumps(
        f"WARNING: ClawHub skill source {source!r} was not found; keeping placeholder at {skill_path}."
    )
    source_error = json.dumps(
        f"ERROR: ClawHub skill source {source!r} was not found and no placeholder exists at {skill_path}."
    )
    return (
        f"mkdir -p {skills_root} && "
        f"if [ ! -f {skill_md_json} ] || grep -qF {placeholder_marker} {skill_md_json}; then "
        f'{install_root_var}="$(mktemp -d)" && '
        f"if ({install_command}); then "
        f'if [ -d "{installed_root}" ]; then rm -rf {cleanup_targets} && mv "{installed_root}" "{skill_path}"; '
        f"elif [ -f {skill_md_json} ]; then echo {install_warning} >&2; "
        f"else echo {install_error} >&2; exit 1; fi; "
        f"else if [ -f {skill_md_json} ]; then echo {source_warning} >&2; "
        f"else echo {source_error} >&2; exit 1; fi; fi "
        f'&& rm -rf "${install_root_var}"; '
        "fi"
    )


def _clawhub_post_install_move(skill_path: PurePosixPath, installed_path: PurePosixPath) -> str:
    """Return an optional rename step when ClawHub's directory differs from the wrapper name."""
    if skill_path == installed_path:
        return ""
    return (
        " && if [ -d "
        f'"{installed_path}"'
        " ]; then mv "
        f'"{installed_path}" "{skill_path}"; '
        "fi"
    )


def _rm_target_arguments(skill_path: PurePosixPath, installed_path: PurePosixPath) -> str:
    """Render unique `rm -rf` target arguments for pre-install cleanup."""
    targets: list[str] = [f'"{skill_path}"']
    if installed_path != skill_path:
        targets.append(f'"{installed_path}"')
    return " ".join(targets)


def _escape_label(value: str) -> str:
    """Escape Docker label values so they can be embedded safely in the Dockerfile."""
    return value.replace("\\", "\\\\").replace('"', '\\"')
