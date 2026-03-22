"""Verify that the provided Git tag matches the package version."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import tomllib


def resolve_tag_name(explicit_tag: str | None) -> str:
    """Return the tag name from an explicit argument or the workflow environment."""
    if explicit_tag:
        return explicit_tag

    try:
        return os.environ["GITHUB_REF_NAME"]
    except KeyError as exc:
        raise SystemExit(
            "Tag name is required. Pass it as an argument or define GITHUB_REF_NAME."
        ) from exc


def normalize_tag(tag_name: str) -> str:
    """Normalize an optional `v` prefix away so tags map to package versions."""
    return tag_name[1:] if tag_name.startswith("v") else tag_name


def parse_args() -> argparse.Namespace:
    """Parse the optional explicit tag argument."""
    parser = argparse.ArgumentParser(
        description="Verify that a release tag matches [project].version in pyproject.toml."
    )
    parser.add_argument(
        "tag",
        nargs="?",
        help="Release tag to validate. Falls back to GITHUB_REF_NAME when omitted.",
    )
    return parser.parse_args()


def main() -> None:
    """Fail when the Git tag and the package version are out of sync."""
    args = parse_args()
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    project_version = pyproject["project"]["version"]
    tag_name = resolve_tag_name(args.tag)
    normalized_tag = normalize_tag(tag_name)

    if normalized_tag != project_version:
        raise SystemExit(
            f"Tag {tag_name!r} does not match pyproject version {project_version!r}."
        )

    print(f"Publishing version {project_version} from tag {tag_name}.")


if __name__ == "__main__":
    main()
