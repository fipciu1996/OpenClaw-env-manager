"""Utility helpers."""

from __future__ import annotations

import base64
import hashlib
import json
import re
from typing import Any


_NAME_NORMALIZER = re.compile(r"[^a-z0-9]+")
_HOME_OPENCLAW_WORKSPACE_PATTERN = re.compile(
    r"(?:/home/[A-Za-z0-9._-]+|/root|\$HOME|\$\{HOME\}|~)/\.openclaw/workspace(?=(?:/|\b|$))"
)
_HOME_OPENCLAW_STATE_PATTERN = re.compile(
    r"(?:/home/[A-Za-z0-9._-]+|/root|\$HOME|\$\{HOME\}|~)/\.openclaw(?=(?:/|\b|$))"
)


def stable_json_dumps(value: Any, *, indent: int | None = None) -> str:
    """Serialize data deterministically."""
    return json.dumps(value, indent=indent, sort_keys=True, ensure_ascii=True)


def sha256_text(text: str) -> str:
    """Return the SHA-256 digest of UTF-8 text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def slugify_name(value: str) -> str:
    """Normalize a project name for file and image tags."""
    normalized = _NAME_NORMALIZER.sub("-", value.strip().lower()).strip("-")
    return normalized or "openclawenv-agent"


def encode_payload(value: Any) -> str:
    """Encode JSON payload as base64 for embedding in Dockerfile."""
    encoded = stable_json_dumps(value, indent=None).encode("utf-8")
    return base64.b64encode(encoded).decode("ascii")


def rewrite_openclaw_home_paths(text: str, *, state_dir: str, workspace: str) -> str:
    """Rewrite hard-coded home-based OpenClaw paths to runtime-specific directories."""
    rewritten = _HOME_OPENCLAW_WORKSPACE_PATTERN.sub(workspace, text)
    return _HOME_OPENCLAW_STATE_PATTERN.sub(state_dir, rewritten)
