"""Command line interface for OpenClawenv."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from loguru import logger

from openenv.bots.manager import interactive_menu
from openenv.core.errors import CommandError, OpenEnvError
from openenv.core.models import Lockfile, Manifest
from openenv.docker.builder import build_image_with_args, default_image_tag
from openenv.docker.compose import (
    default_compose_filename,
    default_env_filename,
    render_compose,
    render_env_file,
    write_compose,
    write_env_file,
)
from openenv.docker.dockerfile import (
    DEFAULT_SKILL_SCAN_FAIL_ON_SEVERITY,
    DEFAULT_SKILL_SCAN_FORMAT,
    DEFAULT_SKILL_SCAN_POLICY,
    render_dockerfile,
)
from openenv.envfiles.secret_env import load_secret_values, secret_env_path
from openenv.integrations.scanner import run_skill_scanner
from openenv.manifests.loader import load_manifest
from openenv.manifests.lockfile import (
    build_lockfile,
    dump_lockfile,
    load_lockfile,
    write_lockfile,
)
from openenv.templates.sample import SAMPLE_MANIFEST


DEFAULT_MANIFEST_FILENAME = "openclawenv.toml"
LEGACY_MANIFEST_FILENAME = "openenv.toml"
DEFAULT_LOCKFILE_FILENAME = "openclawenv.lock"
LEGACY_LOCKFILE_FILENAME = "openenv.lock"
DEFAULT_SCAN_ARTIFACTS_DIRNAME = ".openclawenv-scan"


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI parser."""
    parser = argparse.ArgumentParser(prog="clawopenenv", description="OpenClawenv CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help=f"Create a starter {DEFAULT_MANIFEST_FILENAME}")
    init_parser.add_argument("--path", default=DEFAULT_MANIFEST_FILENAME, help="Manifest output path")
    init_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing manifest file",
    )

    validate_parser = subparsers.add_parser("validate", help=f"Validate {DEFAULT_MANIFEST_FILENAME}")
    validate_parser.add_argument("--path", default=DEFAULT_MANIFEST_FILENAME, help="Manifest path")

    lock_parser = subparsers.add_parser("lock", help=f"Generate {DEFAULT_LOCKFILE_FILENAME}")
    lock_parser.add_argument("--path", default=DEFAULT_MANIFEST_FILENAME, help="Manifest path")
    lock_parser.add_argument("--output", default=DEFAULT_LOCKFILE_FILENAME, help="Lockfile output path")

    scan_parser = subparsers.add_parser("scan", help="Run skill-scanner against inline skills")
    scan_parser.add_argument("--path", default=DEFAULT_MANIFEST_FILENAME, help="Manifest path")
    scan_parser.add_argument(
        "--scanner-bin",
        default="skill-scanner",
        help="Path to the skill-scanner executable",
    )
    scan_parser.add_argument(
        "--keep-artifacts",
        action="store_true",
        help=f"Keep the materialized skill directory in {DEFAULT_SCAN_ARTIFACTS_DIRNAME}",
    )
    scan_parser.add_argument(
        "scanner_args",
        nargs=argparse.REMAINDER,
        help="Additional arguments passed to skill-scanner after --",
    )

    export_parser = subparsers.add_parser("export", help="Export generated artifacts")
    export_subparsers = export_parser.add_subparsers(dest="export_command", required=True)
    dockerfile_parser = export_subparsers.add_parser(
        "dockerfile",
        help="Render the deterministic Dockerfile",
    )
    dockerfile_parser.add_argument("--path", default=DEFAULT_MANIFEST_FILENAME, help="Manifest path")
    dockerfile_parser.add_argument("--lock", default=DEFAULT_LOCKFILE_FILENAME, help="Lockfile path")
    dockerfile_parser.add_argument("--output", help="Optional Dockerfile output path")
    compose_parser = export_subparsers.add_parser(
        "compose",
        help="Render the docker-compose file for the bot image",
    )
    compose_parser.add_argument("--path", default=DEFAULT_MANIFEST_FILENAME, help="Manifest path")
    compose_parser.add_argument("--lock", default=DEFAULT_LOCKFILE_FILENAME, help="Lockfile path")
    compose_parser.add_argument("--tag", help="Docker image tag to reference")
    compose_parser.add_argument("--output", help="Optional compose output path")

    build_parser_cmd = subparsers.add_parser("build", help="Build the Docker image")
    build_parser_cmd.add_argument("--path", default=DEFAULT_MANIFEST_FILENAME, help="Manifest path")
    build_parser_cmd.add_argument("--lock", default=DEFAULT_LOCKFILE_FILENAME, help="Lockfile path")
    build_parser_cmd.add_argument("--tag", help="Docker image tag")
    build_parser_cmd.add_argument(
        "--scan-format",
        default=DEFAULT_SKILL_SCAN_FORMAT,
        help="Build-time skill scan format passed to the Dockerfile",
    )
    build_parser_cmd.add_argument(
        "--scan-policy",
        default=DEFAULT_SKILL_SCAN_POLICY,
        help="Build-time skill scan policy passed to the Dockerfile",
    )
    build_parser_cmd.add_argument(
        "--scan-fail-on-severity",
        default=DEFAULT_SKILL_SCAN_FAIL_ON_SEVERITY,
        help="Build-time skill scan severity threshold passed to the Dockerfile",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    """Program entry point."""
    _configure_logging()
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        return interactive_menu(Path.cwd())
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            return _handle_init(args)
        if args.command == "validate":
            return _handle_validate(args)
        if args.command == "lock":
            return _handle_lock(args)
        if args.command == "scan":
            return _handle_scan(args)
        if args.command == "export" and args.export_command == "dockerfile":
            return _handle_export_dockerfile(args)
        if args.command == "export" and args.export_command == "compose":
            return _handle_export_compose(args)
        if args.command == "build":
            return _handle_build(args)
        parser.error("unknown command")
    except CommandError as exc:
        logger.error("error: {}", exc)
        return exc.exit_code or 1
    except OpenEnvError as exc:
        logger.error("error: {}", exc)
        return 1
    return 0


def _handle_init(args: argparse.Namespace) -> int:
    """Create a starter manifest file at the requested path."""
    path = Path(args.path)
    if path.exists() and not args.force:
        raise OpenEnvError(f"Refusing to overwrite existing file: {path}")
    path.write_text(SAMPLE_MANIFEST, encoding="utf-8")
    logger.info("Created starter manifest at {}", path)
    return 0


def _handle_validate(args: argparse.Namespace) -> int:
    """Validate a manifest and print a short summary for the operator."""
    manifest, _ = load_manifest(_resolve_manifest_path_argument(args.path))
    logger.info(
        "Manifest valid: "
        f"{manifest.project.name} {manifest.project.version} "
        f"with {len(manifest.runtime.python_packages)} Python packages "
        f"and {len(manifest.skills)} skill(s)."
    )
    return 0


def _handle_lock(args: argparse.Namespace) -> int:
    """Resolve the manifest into a deterministic lockfile and write it to disk."""
    manifest_path = _resolve_manifest_path_argument(args.path)
    manifest, raw_manifest_text = load_manifest(manifest_path)
    lockfile = build_lockfile(manifest, raw_manifest_text)
    write_lockfile(args.output, lockfile)
    logger.info("Wrote lockfile to {}", args.output)
    return 0


def _handle_scan(args: argparse.Namespace) -> int:
    """Materialize skills from the manifest and run the external skill scanner."""
    manifest_path = _resolve_manifest_path_argument(args.path)
    manifest, _ = load_manifest(manifest_path)
    scan_dir = run_skill_scanner(
        manifest_path,
        manifest,
        scanner_bin=args.scanner_bin,
        scanner_args=args.scanner_args,
        keep_artifacts=args.keep_artifacts,
    )
    if scan_dir is not None:
        logger.info("Kept materialized scan artifacts in {}", scan_dir)
    logger.info("skill-scanner completed successfully")
    return 0


def _handle_export_dockerfile(args: argparse.Namespace) -> int:
    """Render the locked Dockerfile and either print it or save it to disk."""
    dockerfile_text = _render_locked_dockerfile(
        manifest_path=args.path,
        lock_path=args.lock,
    )
    if args.output:
        Path(args.output).write_text(dockerfile_text, encoding="utf-8")
        logger.info("Wrote Dockerfile to {}", args.output)
    else:
        sys.stdout.write(dockerfile_text)
    return 0


def _handle_build(args: argparse.Namespace) -> int:
    """Build the Docker image and emit the compose bundle beside the manifest."""
    manifest_path = _resolve_manifest_path_argument(args.path)
    manifest, _ = load_manifest(manifest_path)
    dockerfile_text = _render_locked_dockerfile(
        manifest_path=manifest_path,
        lock_path=_resolve_lock_path_argument(args.lock, manifest_path=manifest_path),
    )
    tag = args.tag or default_image_tag(manifest.project.name, manifest.project.version)
    build_image_with_args(
        dockerfile_text,
        tag,
        build_args={
            "OPENCLAWENV_SKILL_SCAN_FORMAT": args.scan_format,
            "OPENCLAWENV_SKILL_SCAN_POLICY": args.scan_policy,
            "OPENCLAWENV_SKILL_SCAN_FAIL_ON_SEVERITY": args.scan_fail_on_severity,
        },
    )
    dockerfile_path, compose_path, env_path = _write_compose_bundle(
        manifest_path=manifest_path,
        manifest=manifest,
        image_tag=tag,
        dockerfile_text=dockerfile_text,
    )
    logger.info("Wrote Dockerfile to {}", dockerfile_path)
    logger.info("Wrote docker-compose file to {}", compose_path)
    logger.info("Wrote secrets env file to {}", env_path)
    logger.info("Built image {}", tag)
    return 0


def _handle_export_compose(args: argparse.Namespace) -> int:
    """Render the compose/env bundle that references a previously locked image build."""
    manifest_path = _resolve_manifest_path_argument(args.path)
    lock_path = _resolve_lock_path_argument(args.lock, manifest_path=manifest_path)
    manifest, _ = load_manifest(manifest_path)
    _load_and_verify_lockfile(manifest_path, lock_path)
    tag = args.tag or default_image_tag(manifest.project.name, manifest.project.version)
    compose_path = Path(args.output) if args.output else None
    dockerfile_text = _render_locked_dockerfile(
        manifest_path=manifest_path,
        lock_path=lock_path,
    )
    dockerfile_path, compose_path, env_path = _write_compose_bundle(
        manifest_path=manifest_path,
        manifest=manifest,
        image_tag=tag,
        compose_path=compose_path,
        dockerfile_text=dockerfile_text,
    )
    logger.info("Wrote Dockerfile to {}", dockerfile_path)
    logger.info("Wrote docker-compose file to {}", compose_path)
    logger.info("Wrote secrets env file to {}", env_path)
    return 0


def _configure_logging() -> None:
    """Configure plain CLI logging via loguru."""
    logger.remove()
    logger.add(
        sys.stdout,
        level="INFO",
        format="{message}",
        filter=lambda record: record["level"].no < 40,
    )
    logger.add(
        sys.stderr,
        level="ERROR",
        format="{message}",
    )


def _render_locked_dockerfile(*, manifest_path: str, lock_path: str) -> str:
    """Load the manifest and verified lockfile, then render the effective Dockerfile."""
    manifest, lockfile, raw_manifest_text = _load_and_verify_lockfile(
        _resolve_manifest_path_argument(manifest_path),
        _resolve_lock_path_argument(lock_path, manifest_path=manifest_path),
    )
    raw_lock_text = dump_lockfile(lockfile)
    return render_dockerfile(
        manifest,
        lockfile,
        raw_manifest_text=raw_manifest_text,
        raw_lock_text=raw_lock_text,
    )


def _load_and_verify_lockfile(
    manifest_path: str,
    lock_path: str,
) -> tuple[Manifest, Lockfile, str]:
    """Load a manifest/lockfile pair and ensure the lock matches the current manifest."""
    resolved_manifest_path = _resolve_manifest_path_argument(manifest_path)
    manifest, raw_manifest_text = load_manifest(resolved_manifest_path)
    lockfile = load_lockfile(_resolve_lock_path_argument(lock_path, manifest_path=resolved_manifest_path))
    expected_hash = build_lockfile(
        manifest,
        raw_manifest_text,
        resolver=lambda _: {
            "digest": lockfile.base_image["digest"],
            "resolved_reference": lockfile.base_image["resolved_reference"],
        },
    ).manifest_hash
    if expected_hash != lockfile.manifest_hash:
        raise OpenEnvError(
            "The lockfile does not match the current manifest. Run `clawopenenv lock` again."
        )
    return manifest, lockfile, raw_manifest_text


def _default_compose_path(manifest_path: str, agent_name: str) -> Path:
    """Return the default compose destination located next to the manifest."""
    return Path(manifest_path).resolve().parent / default_compose_filename(agent_name)


def _resolve_manifest_path_argument(path: str | Path) -> str:
    """Resolve the manifest path, falling back to the legacy filename when present."""
    candidate = Path(path)
    if candidate.name == DEFAULT_MANIFEST_FILENAME and not candidate.exists():
        legacy = candidate.with_name(LEGACY_MANIFEST_FILENAME)
        if legacy.exists():
            return str(legacy)
    return str(candidate)


def _resolve_lock_path_argument(lock_path: str | Path, *, manifest_path: str | Path | None = None) -> str:
    """Resolve the lockfile path, falling back to legacy or sibling lockfile names."""
    candidate = Path(lock_path)
    search_paths: list[Path] = []
    if candidate.name == DEFAULT_LOCKFILE_FILENAME:
        search_paths.append(candidate)
        search_paths.append(candidate.with_name(LEGACY_LOCKFILE_FILENAME))
    else:
        search_paths.append(candidate)
    if manifest_path is not None:
        manifest_candidate = Path(manifest_path)
        search_paths.extend(
            [
                manifest_candidate.with_name(DEFAULT_LOCKFILE_FILENAME),
                manifest_candidate.with_name(LEGACY_LOCKFILE_FILENAME),
            ]
        )
    for path in search_paths:
        if path.exists():
            return str(path)
    return str(candidate)


def _write_compose_bundle(
    *,
    manifest_path: str,
    manifest: Manifest,
    image_tag: str,
    compose_path: Path | None = None,
    dockerfile_text: str | None = None,
) -> tuple[Path | None, Path, Path]:
    """Write the Dockerfile, compose file, and env file associated with one bot build."""
    compose_target = compose_path or _default_compose_path(
        manifest_path,
        manifest.openclaw.agent_name,
    )
    dockerfile_target: Path | None = None
    if dockerfile_text is not None:
        dockerfile_target = compose_target.resolve().parent / "Dockerfile"
        dockerfile_target.write_text(dockerfile_text, encoding="utf-8")
    env_target = compose_target.resolve().parent / default_env_filename(
        manifest.openclaw.agent_name
    )
    write_compose(compose_target, render_compose(manifest, image_tag))
    source_env_path = secret_env_path(Path(manifest_path).resolve().parent)
    existing_values = load_secret_values(env_target)
    if source_env_path.exists():
        existing_values.update(load_secret_values(source_env_path))
    write_env_file(
        env_target,
        render_env_file(manifest, image_tag, existing_values=existing_values),
    )
    return dockerfile_target, compose_target, env_target
