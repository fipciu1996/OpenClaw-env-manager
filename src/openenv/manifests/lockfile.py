"""Lockfile creation and serialization."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any, Callable

from openenv.core.errors import LockResolutionError, ValidationError
from openenv.core.models import Lockfile, Manifest
from openenv.core.utils import sha256_text, stable_json_dumps

_DIRECT_REFERENCE_PATTERN = re.compile(
    r"^\s*([A-Za-z0-9_.-]+(?:\[[A-Za-z0-9_,.-]+\])?)\s*@\s*(\S+)\s*$"
)
_PINNED_REQUIREMENT_PATTERN = re.compile(
    r"^\s*([A-Za-z0-9_.-]+(?:\[[A-Za-z0-9_,.-]+\])?)\s*==\s*([A-Za-z0-9_.!+-]+)\s*$"
)
_PINNED_NODE_REQUIREMENT_PATTERN = re.compile(
    r"^\s*(?P<name>(?:@[A-Za-z0-9._-]+/)?[A-Za-z0-9._-]+)@(?P<version>[A-Za-z0-9][A-Za-z0-9.+_-]*)\s*$"
)
_DIGEST_PATTERN = re.compile(r"^(?P<image>.+)@(?P<digest>sha256:[a-fA-F0-9]{64})$")


def build_lockfile(
    manifest: Manifest,
    raw_manifest_text: str,
    *,
    resolver: Callable[[str], dict[str, str]] | None = None,
) -> Lockfile:
    """Create a deterministic lockfile from a manifest."""
    manifest_hash = sha256_text(stable_json_dumps(manifest.to_dict(), indent=None))
    image_info = resolve_base_image(manifest.runtime.base_image, resolver=resolver)
    python_packages = [
        _resolve_python_requirement(requirement)
        for requirement in manifest.runtime.python_packages
    ]
    node_packages = [
        _resolve_node_requirement(requirement)
        for requirement in manifest.runtime.node_packages
    ]
    return Lockfile(
        lock_version=1,
        manifest_hash=manifest_hash,
        base_image={
            "digest": image_info["digest"],
            "reference": manifest.runtime.base_image,
            "resolved_reference": image_info["resolved_reference"],
        },
        python_packages=python_packages,
        node_packages=node_packages,
        system_packages=list(manifest.runtime.system_packages),
        source_snapshot={
            **manifest.source_snapshot(),
            "raw_manifest_sha256": sha256_text(raw_manifest_text),
        },
    )


def resolve_base_image(
    base_image: str,
    *,
    resolver: Callable[[str], dict[str, str]] | None = None,
) -> dict[str, str]:
    """Resolve the Docker base image to a content-addressed reference."""
    if resolver is not None:
        return resolver(base_image)

    digest_match = _DIGEST_PATTERN.match(base_image)
    if digest_match:
        return {
            "digest": digest_match.group("digest"),
            "resolved_reference": base_image,
        }

    try:
        completed = _inspect_base_image(base_image)
    except OSError as exc:
        raise LockResolutionError(
            "Docker is required to resolve an unpinned base image. "
            "Pin runtime.base_image with @sha256 or make docker available."
        ) from exc
    except subprocess.CalledProcessError as exc:
        if _is_missing_local_image_error(exc):
            completed = _pull_and_inspect_base_image(base_image)
        else:
            raise LockResolutionError(
                "Unable to resolve runtime.base_image. "
                "Pin it with @sha256 or ensure the image is present locally. "
                f"Docker said: {_docker_error_detail(exc)}"
            ) from exc

    try:
        repo_digests = json.loads(completed.stdout.strip() or "[]")
    except json.JSONDecodeError as exc:
        raise LockResolutionError(
            "Docker returned an unreadable RepoDigests payload while resolving the base image."
        ) from exc
    if not repo_digests:
        raise LockResolutionError(
            "Docker did not return a RepoDigest for the base image. "
            "Pin runtime.base_image with @sha256 for deterministic locks."
        )

    resolved_reference = repo_digests[0]
    digest_match = _DIGEST_PATTERN.match(resolved_reference)
    if digest_match is None:
        raise LockResolutionError(
            f"Resolved base image did not include a digest: {resolved_reference}"
        )
    digest = digest_match.group("digest")
    return {
        "digest": digest,
        "resolved_reference": _attach_digest(base_image, digest),
    }


def _inspect_base_image(base_image: str) -> subprocess.CompletedProcess[str]:
    """Inspect a local Docker image and return the raw `RepoDigests` response."""
    return subprocess.run(
        [
            "docker",
            "image",
            "inspect",
            base_image,
            "--format",
            "{{json .RepoDigests}}",
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def _pull_and_inspect_base_image(base_image: str) -> subprocess.CompletedProcess[str]:
    """Pull a missing base image and then inspect it locally to obtain its digest."""
    try:
        subprocess.run(
            ["docker", "image", "pull", base_image],
            check=True,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        raise LockResolutionError(
            "Docker is required to pull and resolve an unpinned base image. "
            "Pin runtime.base_image with @sha256 or make docker available."
        ) from exc
    except subprocess.CalledProcessError as exc:
        raise LockResolutionError(
            "Unable to resolve runtime.base_image locally and docker pull failed. "
            f"Docker said: {_docker_error_detail(exc)}"
        ) from exc

    try:
        return _inspect_base_image(base_image)
    except OSError as exc:
        raise LockResolutionError(
            "Docker is required to inspect the pulled base image. "
            "Pin runtime.base_image with @sha256 or make docker available."
        ) from exc
    except subprocess.CalledProcessError as exc:
        raise LockResolutionError(
            "Docker pulled runtime.base_image but it still could not be inspected locally. "
            f"Docker said: {_docker_error_detail(exc)}"
        ) from exc


def _is_missing_local_image_error(exc: subprocess.CalledProcessError) -> bool:
    """Return whether Docker reported that the requested image is absent locally."""
    detail = _docker_error_detail(exc).lower()
    return "no such image" in detail or "no such object" in detail


def _docker_error_detail(exc: subprocess.CalledProcessError) -> str:
    """Extract a human-readable stderr message from a failed Docker command."""
    return exc.stderr.strip() if exc.stderr else "unknown docker error"


def _attach_digest(base_image: str, digest: str) -> str:
    """Attach a resolved digest to the original image reference while preserving its tag."""
    return f"{base_image}@{digest}"


def _resolve_python_requirement(requirement: str) -> dict[str, str]:
    """Normalize a pinned Python requirement into the lockfile package schema."""
    direct_match = _DIRECT_REFERENCE_PATTERN.match(requirement)
    if direct_match is not None:
        return {
            "kind": "direct",
            "name": direct_match.group(1).lower(),
            "requirement": requirement,
            "url": direct_match.group(2),
        }

    pinned_match = _PINNED_REQUIREMENT_PATTERN.match(requirement)
    if pinned_match is not None:
        return {
            "kind": "pinned",
            "name": pinned_match.group(1).lower(),
            "requirement": requirement,
            "version": pinned_match.group(2),
        }

    raise LockResolutionError(
        "OpenClawenv v1 locks only exact Python requirements. "
        f"Use 'package==version' or 'name @ URL': {requirement}"
    )


def _resolve_node_requirement(requirement: str) -> dict[str, str]:
    """Normalize a pinned Node.js requirement into the lockfile package schema."""
    pinned_match = _PINNED_NODE_REQUIREMENT_PATTERN.match(requirement)
    if pinned_match is not None:
        return {
            "kind": "pinned",
            "name": pinned_match.group("name"),
            "requirement": requirement,
            "version": pinned_match.group("version"),
        }

    raise LockResolutionError(
        "OpenClawenv v1 locks only exact Node requirements. "
        f"Use 'package@version' or '@scope/package@version': {requirement}"
    )


def dump_lockfile(lockfile: Lockfile) -> str:
    """Serialize a lockfile deterministically."""
    return stable_json_dumps(lockfile.to_dict(), indent=2) + "\n"


def write_lockfile(path: str | Path, lockfile: Lockfile) -> None:
    """Write a lockfile to disk."""
    Path(path).write_text(dump_lockfile(lockfile), encoding="utf-8")


def load_lockfile(path: str | Path) -> Lockfile:
    """Load a lockfile from JSON."""
    lock_path = Path(path)
    try:
        data = json.loads(lock_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValidationError(f"Lockfile not found: {lock_path}") from exc
    except json.JSONDecodeError as exc:
        raise ValidationError(f"Invalid JSON in {lock_path}: {exc}") from exc
    return parse_lockfile(data)


def parse_lockfile(data: dict[str, Any]) -> Lockfile:
    """Validate a parsed lockfile payload."""
    if not isinstance(data, dict):
        raise ValidationError("Lockfile root must be an object.")
    required_keys = {
        "lock_version",
        "manifest_hash",
        "base_image",
        "python_packages",
        "node_packages",
        "system_packages",
        "source_snapshot",
    }
    missing = sorted(required_keys - set(data))
    if missing:
        raise ValidationError(f"Lockfile is missing required keys: {', '.join(missing)}")
    if data["lock_version"] != 1:
        raise ValidationError("lock_version must be set to 1.")
    if not isinstance(data["base_image"], dict):
        raise ValidationError("lockfile.base_image must be an object.")
    if not isinstance(data["python_packages"], list):
        raise ValidationError("lockfile.python_packages must be a list.")
    if not isinstance(data["node_packages"], list):
        raise ValidationError("lockfile.node_packages must be a list.")
    if not isinstance(data["system_packages"], list):
        raise ValidationError("lockfile.system_packages must be a list.")
    if not isinstance(data["source_snapshot"], dict):
        raise ValidationError("lockfile.source_snapshot must be an object.")
    return Lockfile(
        lock_version=data["lock_version"],
        manifest_hash=_require_string(data, "manifest_hash"),
        base_image=data["base_image"],
        python_packages=data["python_packages"],
        node_packages=data["node_packages"],
        system_packages=data["system_packages"],
        source_snapshot=data["source_snapshot"],
    )


def _require_string(data: dict[str, Any], key: str) -> str:
    """Require a non-empty string when validating deserialized lockfile payloads."""
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{key} must be a non-empty string.")
    return value
