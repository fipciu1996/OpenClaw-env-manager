"""Deploy the generated documentation site to the repository's gh-pages branch."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit


BOT_NAME = "github-actions[bot]"
BOT_EMAIL = "41898282+github-actions[bot]@users.noreply.github.com"


def run_git(
    *args: str,
    cwd: Path | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run a git command and return its completed process object."""
    command = ["git", *_git_auth_config_args(), *args]
    try:
        return subprocess.run(
            command,
            cwd=cwd,
            check=check,
            text=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as exc:
        if not check:
            raise
        raise SystemExit(_format_git_failure(command, exc)) from exc


def parse_args() -> argparse.Namespace:
    """Parse the deployment parameters passed by the workflow."""
    parser = argparse.ArgumentParser(
        description="Publish the generated site directory to a GitHub Pages branch."
    )
    parser.add_argument(
        "--site-dir",
        default="site",
        help="Directory containing the static site to publish.",
    )
    parser.add_argument(
        "--branch",
        default="gh-pages",
        help="Target branch that backs GitHub Pages.",
    )
    parser.add_argument(
        "--commit-message",
        default="Deploy GitHub Pages site",
        help="Commit message to use for generated site updates.",
    )
    return parser.parse_args()


def remote_url() -> str:
    """Return the current repository origin URL."""
    token = os.environ.get("GITHUB_TOKEN")
    repository = os.environ.get("GITHUB_REPOSITORY")
    if token and repository:
        server_url = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
        return build_authenticated_remote_url(server_url, repository, token)
    return run_git("remote", "get-url", "origin").stdout.strip()


def build_authenticated_remote_url(server_url: str, repository: str, token: str) -> str:
    """Build an HTTPS remote URL that authenticates with GitHub Actions token auth."""
    parsed = urlsplit(server_url)
    scheme = parsed.scheme or "https"
    netloc = parsed.netloc or "github.com"
    token_part = quote(token, safe="")
    auth_netloc = f"x-access-token:{token_part}@{netloc}"
    path = "/" + repository.strip("/") + ".git"
    return urlunsplit((scheme, auth_netloc, path, "", ""))


def _git_auth_config_args() -> list[str]:
    """Return transient git config overrides needed to reuse checkout credentials."""
    try:
        completed = subprocess.run(
            ["git", "config", "--get-regexp", r"^http\..*\.extraheader$"],
            check=True,
            text=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError:
        return []

    args: list[str] = []
    for line in completed.stdout.splitlines():
        key, _, value = line.partition(" ")
        if not key or not value:
            continue
        args.extend(["-c", f"{key}={value}"])
    return args


def _format_git_failure(
    command: list[str],
    error: subprocess.CalledProcessError,
) -> str:
    """Render a concise git failure message with stderr/stdout details."""
    rendered_command = " ".join(_redact_sensitive_part(part) for part in command)
    stderr = (error.stderr or "").strip()
    stdout = (error.stdout or "").strip()
    details: list[str] = [f"Git command failed: {rendered_command}"]
    if stderr:
        details.append(f"stderr:\n{_redact_sensitive_part(stderr)}")
    if stdout:
        details.append(f"stdout:\n{_redact_sensitive_part(stdout)}")
    return "\n".join(details)


def _redact_sensitive_part(value: str) -> str:
    """Redact token-bearing auth material before surfacing command failures."""
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    rendered = value
    if token:
        rendered = rendered.replace(token, "***")
    return rendered.replace("x-access-token:***@", "x-access-token:***@")


def clone_target_branch(remote: str, branch: str, target_dir: Path) -> None:
    """Clone the publish branch when it already exists or bootstrap a fresh orphan branch."""
    probe = run_git("ls-remote", "--heads", remote, branch, check=False)
    if probe.returncode == 0 and probe.stdout.strip():
        run_git("clone", "--depth", "1", "--branch", branch, remote, str(target_dir))
        return

    run_git("clone", remote, str(target_dir))
    run_git("checkout", "--orphan", branch, cwd=target_dir)
    for entry in target_dir.iterdir():
        if entry.name == ".git":
            continue
        if entry.is_dir():
            shutil.rmtree(entry)
        else:
            entry.unlink()


def replace_site_contents(site_dir: Path, target_dir: Path) -> None:
    """Replace the branch contents with the newly generated static site."""
    for entry in target_dir.iterdir():
        if entry.name == ".git":
            continue
        if entry.is_dir():
            shutil.rmtree(entry)
        else:
            entry.unlink()

    for entry in site_dir.iterdir():
        destination = target_dir / entry.name
        if entry.is_dir():
            shutil.copytree(entry, destination)
        else:
            shutil.copy2(entry, destination)


def configure_git_identity(target_dir: Path) -> None:
    """Set the committer identity used for GitHub Actions site updates."""
    run_git("config", "user.name", BOT_NAME, cwd=target_dir)
    run_git("config", "user.email", BOT_EMAIL, cwd=target_dir)


def commit_if_needed(target_dir: Path, commit_message: str) -> bool:
    """Commit the generated site only when there are staged changes."""
    run_git("add", "--all", cwd=target_dir)
    status = run_git("status", "--short", cwd=target_dir).stdout.strip()
    if not status:
        print("GitHub Pages branch is already up to date.")
        return False

    run_git("commit", "-m", commit_message, cwd=target_dir)
    return True


def main() -> None:
    """Publish the current static site directory to the configured GitHub Pages branch."""
    args = parse_args()
    site_dir = Path(args.site_dir).resolve()
    if not site_dir.is_dir():
        raise SystemExit(f"Site directory {site_dir} does not exist.")
    if os.environ.get("GITHUB_ACTIONS") == "true" and not _git_auth_config_args():
        raise SystemExit(
            "GitHub Actions checkout credentials were not found. "
            "Ensure actions/checkout runs before the deploy step and keeps credentials enabled."
        )

    with tempfile.TemporaryDirectory(prefix="github-pages-") as temp_dir:
        target_dir = Path(temp_dir)
        branch = args.branch
        remote = remote_url()

        clone_target_branch(remote, branch, target_dir)
        configure_git_identity(target_dir)
        replace_site_contents(site_dir, target_dir)

        if commit_if_needed(target_dir, args.commit_message):
            run_git("push", "--force", "origin", f"HEAD:{branch}", cwd=target_dir)
            print(f"Published {site_dir} to {branch}.")


if __name__ == "__main__":
    main()
