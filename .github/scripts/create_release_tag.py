"""Prepare a release commit and create an annotated Git tag for it."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import shutil
import subprocess
import sys

from verify_release_tag import normalize_tag


PROJECT_VERSION_RE = re.compile(r'(?m)^(version\s*=\s*")([^"]+)(")$')


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for release preparation."""
    parser = argparse.ArgumentParser(
        description=(
            "Update release metadata, create a release commit, and create an annotated tag."
        )
    )
    parser.add_argument(
        "tag",
        help="Release tag to create, for example 1.0.2 or v1.0.2.",
    )
    parser.add_argument(
        "--message",
        help="Optional annotated tag message. A default release message is used when omitted.",
    )
    parser.add_argument(
        "--commit-message",
        help="Optional commit message. Defaults to `Release <version>`.",
    )
    return parser.parse_args()


def run_git(*args: str, capture_output: bool = False) -> subprocess.CompletedProcess[str]:
    """Run a Git command and return the completed process."""
    return subprocess.run(
        ["git", *args],
        check=True,
        text=True,
        capture_output=capture_output,
    )


def run_command(*args: str, capture_output: bool = False) -> subprocess.CompletedProcess[str]:
    """Run a generic subprocess command and return the completed process."""
    return subprocess.run(
        list(args),
        check=True,
        text=True,
        capture_output=capture_output,
    )


def ensure_clean_worktree() -> None:
    """Fail when the Git worktree contains unrelated uncommitted changes."""
    status = run_git("status", "--porcelain", capture_output=True).stdout.strip()
    if status:
        raise SystemExit(
            "Working tree is not clean. Commit or stash changes before creating a release tag."
        )


def ensure_tag_missing(tag: str) -> None:
    """Fail when the requested tag already exists."""
    existing = run_git("tag", "-l", tag, capture_output=True).stdout.strip()
    if existing:
        raise SystemExit(f"Tag {tag!r} already exists.")


def update_pyproject_version(version: str) -> bool:
    """Replace [project].version in pyproject.toml with the requested version."""
    path = Path("pyproject.toml")
    content = path.read_text(encoding="utf-8")
    updated, count = PROJECT_VERSION_RE.subn(rf'\g<1>{version}\g<3>', content, count=1)
    if count != 1:
        raise SystemExit("Unable to locate [project].version in pyproject.toml.")
    if updated == content:
        return False
    path.write_text(updated, encoding="utf-8")
    return True


def require_changelog_cli() -> str:
    """Return the `changelog` executable path or fail with an install hint."""
    candidates = [
        shutil.which("changelog"),
        shutil.which("changelog.exe"),
        str(Path(sys.executable).resolve().with_name("changelog.exe")),
        str(Path(sys.executable).resolve().with_name("changelog")),
    ]

    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate

    raise SystemExit(
        "The `changelog` executable was not found. Install dev dependencies first, "
        "for example with `python -m pip install -e .[dev]`."
    )


def split_version(version: str) -> tuple[int, int, int]:
    """Parse a semantic version string into a numeric tuple."""
    parts = version.split(".")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        raise SystemExit(f"Unsupported release version {version!r}. Expected semantic version X.Y.Z.")
    major, minor, patch = (int(part) for part in parts)
    return major, minor, patch


def read_current_changelog_version(changelog_executable: str) -> str:
    """Return the latest released version reported by changelog-cli."""
    result = run_command(changelog_executable, "current", capture_output=True)
    return result.stdout.strip()


def determine_release_kind(current_version: str, target_version: str) -> str | None:
    """Map a target semantic version to the matching changelog-cli release bump."""
    current = split_version(current_version)
    target = split_version(target_version)

    if target == current:
        return None

    if target == (current[0], current[1], current[2] + 1):
        return "patch"
    if target == (current[0], current[1] + 1, 0):
        return "minor"
    if target == (current[0] + 1, 0, 0):
        return "major"

    raise SystemExit(
        "Target version must be the same as the current release or the next patch, minor, "
        f"or major semantic version. Current version: {current_version!r}, target version: {target_version!r}."
    )


def release_changelog(changelog_executable: str, target_version: str) -> bool:
    """Use changelog-cli to create the next release entry when needed."""
    current_version = read_current_changelog_version(changelog_executable)
    release_kind = determine_release_kind(current_version, target_version)

    if release_kind is None:
        return False

    run_command(changelog_executable, "release", f"--{release_kind}", "--yes")
    released_version = read_current_changelog_version(changelog_executable)
    if released_version != target_version:
        raise SystemExit(
            "changelog-cli created a different release version than expected. "
            f"Expected {target_version!r}, got {released_version!r}."
        )
    return True


def create_release_commit(version: str, commit_message: str) -> None:
    """Commit the version and changelog updates that belong to the release."""
    run_git("add", "pyproject.toml", "CHANGELOG.md")
    run_git("commit", "-m", commit_message)
    print(f"Created release commit for version {version}.")


def create_tag(tag: str, version: str, message: str | None) -> None:
    """Create the final annotated Git tag for the prepared release commit."""
    tag_message = message or f"Open-env {version}\n\nRelease {version}."
    run_git("tag", "-a", tag, "-m", tag_message)
    print(f"Created annotated tag {tag}.")


def main() -> None:
    """Run the release preparation flow end to end."""
    args = parse_args()
    tag = args.tag
    version = normalize_tag(tag)
    changelog_executable = require_changelog_cli()

    ensure_clean_worktree()
    ensure_tag_missing(tag)

    changelog_changed = release_changelog(changelog_executable, version)
    pyproject_changed = update_pyproject_version(version)

    if pyproject_changed or changelog_changed:
        commit_message = args.commit_message or f"Release {version}"
        create_release_commit(version, commit_message)
    else:
        print(f"Release metadata already matches {version}; no commit was needed.")

    create_tag(tag, version, args.message)


if __name__ == "__main__":
    main()
