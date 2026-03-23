"""Interactive bot catalog management."""

from __future__ import annotations

from collections.abc import Iterable
import shutil
from getpass import getpass
from dataclasses import dataclass, field
from pathlib import Path

from openenv.core.skills import (
    MANDATORY_SKILL_SOURCES,
    build_catalog_skill,
    is_mandatory_skill,
    merge_mandatory_skill_sources,
)
from openenv.core.errors import OpenEnvError
from openenv.core.models import (
    AccessConfig,
    AgentConfig,
    Manifest,
    OpenClawConfig,
    ProjectConfig,
    RuntimeConfig,
    SandboxConfig,
    SkillConfig,
)
from openenv.core.utils import slugify_name
from openenv.docker.builder import default_image_tag
from openenv.docker.compose import (
    AllBotsComposeSpec,
    all_bots_compose_filename,
    default_compose_filename,
    default_env_filename,
    gateway_container_name,
    render_compose,
    render_all_bots_compose,
    render_env_file,
    write_compose,
    write_env_file,
)
from openenv.docker.dockerfile import render_dockerfile
from openenv.docker.runtime import (
    CapturedSkill,
    fetch_container_logs,
    list_running_container_names,
    snapshot_installed_skills,
)
from openenv.envfiles.project_env import get_project_env_value, write_project_env_value
from openenv.envfiles.secret_env import (
    load_secret_values,
    secret_env_path,
    write_secret_env,
)
from openenv.integrations.openrouter import improve_markdown_documents_with_openrouter
from openenv.manifests.loader import load_manifest
from openenv.manifests.lockfile import (
    build_lockfile,
    dump_lockfile,
    load_lockfile,
    write_lockfile,
)
from openenv.manifests.writer import render_manifest


DEFAULT_SYSTEM_PACKAGES = ["git", "curl", "chromium"]
DEFAULT_LANGUAGE = "pl"
MANDATORY_SKILLS_LABEL = ", ".join(MANDATORY_SKILL_SOURCES)
MANIFEST_FILENAME = "openclawenv.toml"
LEGACY_MANIFEST_FILENAME = "openenv.toml"
LOCKFILE_FILENAME = "openclawenv.lock"
LEGACY_LOCKFILE_FILENAME = "openenv.lock"
AGENT_DOC_FILENAMES = {
    "agents_md": "AGENTS.md",
    "soul_md": "SOUL.md",
    "user_md": "USER.md",
    "identity_md": "IDENTITY.md",
    "tools_md": "TOOLS.md",
    "memory_seed": "memory.md",
}
LANGUAGE_ALIASES = {
    "": DEFAULT_LANGUAGE,
    "1": "pl",
    "2": "en",
    "pl": "pl",
    "polski": "pl",
    "polish": "pl",
    "en": "en",
    "eng": "en",
    "english": "en",
}
YES_WORDS = {
    "pl": {"t", "tak", "y", "yes"},
    "en": {"y", "yes"},
}
MESSAGES = {
    "pl": {
        "language_title": "OpenClawenv - Wybierz jezyk / Choose language",
        "language_option_pl": "1. Polski",
        "language_option_en": "2. English",
        "language_prompt": "Wybierz jezyk / Choose language [1-2, domyslnie/default 1]: ",
        "language_invalid": "Nieznany wybor / Unknown choice. Wpisz / Enter 1/2 albo / or pl/en.",
        "menu_title": "OpenClawenv - Interaktywne menu",
        "menu_list": "1. Wylistuj boty",
        "menu_add": "2. Dodaj nowego bota",
        "menu_edit": "3. Edytuj bota",
        "menu_delete": "4. Usun bota",
        "menu_running": "5. Wylistuj dzialajace boty",
        "menu_exit": "6. Zakoncz",
        "menu_prompt": "Wybierz opcje [1-6]: ",
        "menu_unknown": "Nieznana opcja. Wybierz 1, 2, 3, 4, 5 lub 6.",
        "menu_exit_message": "Zamykam menu OpenClawenv.",
        "no_bots": "Brak zarejestrowanych botow.",
        "bots_header": "Zarejestrowane boty:",
        "bots_generate_stack": "A. Generuj wspolny stack dla wszystkich botow",
        "role_label": "Rola",
        "manifest_label": "Manifest",
        "compose_label": "docker-compose",
        "container_label": "Kontener",
        "browse_prompt": (
            "Podaj numer bota, wpisz A aby wygenerowac wspolny stack, "
            "albo Enter, aby wrocic: "
        ),
        "running_failed": "Nie udalo sie odczytac dzialajacych botow: {error}",
        "running_no_bots": "Brak dzialajacych botow uruchomionych z katalogu bots.",
        "running_header": "Dzialajace boty:",
        "running_prompt": (
            "Podaj numer dzialajacego bota, aby przejsc do akcji, albo Enter, aby wrocic: "
        ),
        "running_actions_title": "Dzialajacy bot `{display_name}`",
        "running_actions_logs": "1. Podglad logow",
        "running_actions_snapshot": "2. Stworz snapshot skilli",
        "running_actions_back": "3. Wroc",
        "running_actions_prompt": "Wybierz opcje [1-3]: ",
        "running_actions_unknown": "Nieznana opcja. Wybierz 1, 2 lub 3.",
        "logs_failed": "Nie udalo sie pobrac logow: {error}",
        "logs_header": "Logi dla `{display_name}`:",
        "logs_empty": "Brak logow do wyswietlenia.",
        "snapshot_failed": "Nie udalo sie stworzyc snapshota: {error}",
        "snapshot_no_changes": "Snapshot nie wykryl nowych zmian w skillach.",
        "snapshot_manifest": "Zaktualizowano manifest: {path}",
        "snapshot_lockfile": "Zaktualizowano lockfile: {path}",
        "snapshot_added_skill": "Dodano skill: {name}",
        "snapshot_hydrated_skill": "Uzupelniono skill z kontenera: {name}",
        "bot_actions_title": "Bot `{display_name}`",
        "bot_actions_generate": "1. Generuj Dockerfile + docker-compose",
        "bot_actions_improve_docs": "2. Popraw dokumenty *.md przez OpenRouter",
        "bot_actions_back": "3. Wroc",
        "bot_actions_prompt": "Wybierz opcje [1-3]: ",
        "bot_actions_unknown": "Nieznana opcja. Wybierz 1, 2 lub 3.",
        "generate_failed": "Nie udalo sie wygenerowac artefaktow: {error}",
        "generated_lockfile": "Wygenerowano lockfile: {path}",
        "generated_dockerfile": "Wygenerowano Dockerfile: {path}",
        "generated_compose": "Wygenerowano docker-compose: {path}",
        "generated_env": "Wygenerowano plik sekretow: {path}",
        "generate_all_failed": "Nie udalo sie wygenerowac wspolnego stacku: {error}",
        "generated_all_compose": "Wygenerowano wspolny stack: {path}",
        "generated_all_prepared": "Przygotowano artefakty dla {count} botow.",
        "edit_docs_prompt": (
            "Opisz, co poprawic w dokumentach *.md [Enter = popraw spojność i jakosc]: "
        ),
        "openrouter_key_missing": (
            "Brak OPENROUTER_API_KEY w zmiennych systemowych i w pliku .env projektu."
        ),
        "openrouter_key_prompt": "Podaj OPENROUTER_API_KEY: ",
        "openrouter_key_saved": "Zapisano OPENROUTER_API_KEY w {path}",
        "edit_docs_failed": "Nie udalo sie poprawic dokumentow: {error}",
        "edit_docs_done": "OpenRouter zakonczyl poprawianie dokumentow: {summary}",
        "edit_docs_updated_file": "Zaktualizowano: {path}",
        "add_title": "Dodawanie nowego bota",
        "prompt_name": "Jak ma sie nazywac bot? ",
        "prompt_role": "Jaka ma byc rola bota? ",
        "prompt_skills": (
            "Jakie dodatkowe skille ma miec bot? Podaj referencje po przecinku "
            "(np. kralsamwise/kdp-publisher). Obowiazkowe skille: "
            f"{MANDATORY_SKILLS_LABEL}: "
        ),
        "prompt_system_packages": (
            "Jakie dodatkowe pakiety systemowe zainstalowac w kontenerze? "
            "(po przecinku, Enter jesli brak): "
        ),
        "prompt_python_packages": (
            "Jakie dodatkowe pakiety Python zainstalowac? "
            "(np. requests==2.32.3, Enter jesli brak): "
        ),
        "prompt_node_packages": (
            "Jakie dodatkowe pakiety Node.js zainstalowac globalnie? "
            "(np. typescript@5.8.3, @scope/pkg@1.2.3, Enter jesli brak): "
        ),
        "prompt_secrets": (
            "Jakie sekrety / dane logowania sa potrzebne? "
            "(nazwy zmiennych env, np. OPENAI_API_KEY, DB_PASSWORD): "
        ),
        "prompt_websites": (
            "Jakie linki do witryn / endpointow powinien znac bot? "
            "(po przecinku, Enter jesli brak): "
        ),
        "prompt_databases": (
            "Jakie bazy danych lub polaczenia uprzywilejowane powinny byc opisane? "
            "(po przecinku, Enter jesli brak): "
        ),
        "prompt_access_notes": (
            "Dodatkowe notatki o poziomach dostepu lub ograniczeniach "
            "(po przecinku, Enter jesli brak): "
        ),
        "create_failed": "Nie udalo sie utworzyc bota: {error}",
        "created": "Utworzono bota `{display_name}` w {path}",
        "edit_no_bots": "Brak botow do edycji.",
        "edit_select": "Podaj numer bota do edycji: ",
        "edit_title": "Edycja bota `{display_name}`",
        "update_failed": "Nie udalo sie zaktualizowac bota: {error}",
        "updated": "Zaktualizowano bota `{display_name}` w {path}",
        "delete_no_bots": "Brak botow do usuniecia.",
        "delete_select": "Podaj numer bota do usuniecia: ",
        "delete_confirm": (
            "Czy na pewno usunac bota `{display_name}` i caly katalog `{slug}`? [t/N]: "
        ),
        "delete_cancelled": "Usuwanie anulowane.",
        "delete_failed": "Nie udalo sie usunac bota: {error}",
        "deleted": "Usunieto bota `{display_name}`.",
        "required_field": "To pole jest wymagane.",
        "invalid_number": "Podano niepoprawny numer.",
        "out_of_range": "Numer bota jest poza zakresem.",
    },
    "en": {
        "language_title": "OpenClawenv - Wybierz jezyk / Choose language",
        "language_option_pl": "1. Polski",
        "language_option_en": "2. English",
        "language_prompt": "Wybierz jezyk / Choose language [1-2, domyslnie/default 1]: ",
        "language_invalid": "Nieznany wybor / Unknown choice. Wpisz / Enter 1/2 albo / or pl/en.",
        "menu_title": "OpenClawenv - Interactive menu",
        "menu_list": "1. List bots",
        "menu_add": "2. Add a new bot",
        "menu_edit": "3. Edit a bot",
        "menu_delete": "4. Delete a bot",
        "menu_running": "5. List running bots",
        "menu_exit": "6. Exit",
        "menu_prompt": "Choose an option [1-6]: ",
        "menu_unknown": "Unknown option. Choose 1, 2, 3, 4, 5, or 6.",
        "menu_exit_message": "Closing the OpenClawenv menu.",
        "no_bots": "No registered bots.",
        "bots_header": "Registered bots:",
        "bots_generate_stack": "A. Generate a shared stack for all bots",
        "role_label": "Role",
        "manifest_label": "Manifest",
        "compose_label": "docker-compose",
        "container_label": "Container",
        "browse_prompt": (
            "Enter a bot number, press A to generate the shared stack, "
            "or press Enter to go back: "
        ),
        "running_failed": "Failed to inspect running bots: {error}",
        "running_no_bots": "No running bots launched from the bots directory were found.",
        "running_header": "Running bots:",
        "running_prompt": (
            "Enter a running bot number to open actions, or press Enter to go back: "
        ),
        "running_actions_title": "Running bot `{display_name}`",
        "running_actions_logs": "1. View logs",
        "running_actions_snapshot": "2. Create a skill snapshot",
        "running_actions_back": "3. Back",
        "running_actions_prompt": "Choose an option [1-3]: ",
        "running_actions_unknown": "Unknown option. Choose 1, 2, or 3.",
        "logs_failed": "Failed to fetch logs: {error}",
        "logs_header": "Logs for `{display_name}`:",
        "logs_empty": "No logs available.",
        "snapshot_failed": "Failed to create a snapshot: {error}",
        "snapshot_no_changes": "The snapshot did not detect any new skill changes.",
        "snapshot_manifest": "Updated manifest: {path}",
        "snapshot_lockfile": "Updated lockfile: {path}",
        "snapshot_added_skill": "Added skill: {name}",
        "snapshot_hydrated_skill": "Hydrated skill from container: {name}",
        "bot_actions_title": "Bot `{display_name}`",
        "bot_actions_generate": "1. Generate Dockerfile + docker-compose",
        "bot_actions_improve_docs": "2. Improve *.md documents via OpenRouter",
        "bot_actions_back": "3. Back",
        "bot_actions_prompt": "Choose an option [1-3]: ",
        "bot_actions_unknown": "Unknown option. Choose 1, 2, or 3.",
        "generate_failed": "Failed to generate artifacts: {error}",
        "generated_lockfile": "Generated lockfile: {path}",
        "generated_dockerfile": "Generated Dockerfile: {path}",
        "generated_compose": "Generated docker-compose: {path}",
        "generated_env": "Generated secrets env file: {path}",
        "generate_all_failed": "Failed to generate the shared stack: {error}",
        "generated_all_compose": "Generated shared stack: {path}",
        "generated_all_prepared": "Prepared artifacts for {count} bot(s).",
        "edit_docs_prompt": (
            "Describe what should be improved in the *.md documents "
            "[Enter = improve overall consistency and quality]: "
        ),
        "openrouter_key_missing": (
            "OPENROUTER_API_KEY was not found in the system environment or project .env."
        ),
        "openrouter_key_prompt": "Enter OPENROUTER_API_KEY: ",
        "openrouter_key_saved": "Saved OPENROUTER_API_KEY to {path}",
        "edit_docs_failed": "Failed to improve documents: {error}",
        "edit_docs_done": "OpenRouter finished improving the documents: {summary}",
        "edit_docs_updated_file": "Updated: {path}",
        "add_title": "Adding a new bot",
        "prompt_name": "What should the bot be called? ",
        "prompt_role": "What should the bot role be? ",
        "prompt_skills": (
            "Which additional skills should it have? Provide comma-separated references "
            "(for example kralsamwise/kdp-publisher). Mandatory skills: "
            f"{MANDATORY_SKILLS_LABEL}: "
        ),
        "prompt_system_packages": (
            "Which extra system packages should be installed in the container? "
            "(comma-separated, press Enter if none): "
        ),
        "prompt_python_packages": (
            "Which extra Python packages should be installed? "
            "(for example requests==2.32.3, press Enter if none): "
        ),
        "prompt_node_packages": (
            "Which extra Node.js packages should be installed globally? "
            "(for example typescript@5.8.3, @scope/pkg@1.2.3, press Enter if none): "
        ),
        "prompt_secrets": (
            "Which secrets / credentials are required? "
            "(env variable names such as OPENAI_API_KEY, DB_PASSWORD): "
        ),
        "prompt_websites": (
            "Which websites / endpoints should the bot know about? "
            "(comma-separated, press Enter if none): "
        ),
        "prompt_databases": (
            "Which databases or privileged connections should be described? "
            "(comma-separated, press Enter if none): "
        ),
        "prompt_access_notes": (
            "Additional access-level notes or restrictions "
            "(comma-separated, press Enter if none): "
        ),
        "create_failed": "Failed to create bot: {error}",
        "created": "Created bot `{display_name}` at {path}",
        "edit_no_bots": "There are no bots to edit.",
        "edit_select": "Enter the bot number to edit: ",
        "edit_title": "Editing bot `{display_name}`",
        "update_failed": "Failed to update bot: {error}",
        "updated": "Updated bot `{display_name}` at {path}",
        "delete_no_bots": "There are no bots to delete.",
        "delete_select": "Enter the bot number to delete: ",
        "delete_confirm": (
            "Are you sure you want to delete bot `{display_name}` and the entire `{slug}` directory? [y/N]: "
        ),
        "delete_cancelled": "Deletion cancelled.",
        "delete_failed": "Failed to delete bot: {error}",
        "deleted": "Deleted bot `{display_name}`.",
        "required_field": "This field is required.",
        "invalid_number": "The provided number is invalid.",
        "out_of_range": "The bot number is out of range.",
    },
}


@dataclass(slots=True)
class BotAnswers:
    """Normalized answers collected from the interactive bot creation or edit flow."""

    display_name: str
    role: str
    skill_sources: list[str]
    system_packages: list[str]
    python_packages: list[str]
    secret_names: list[str]
    websites: list[str]
    databases: list[str]
    access_notes: list[str]
    node_packages: list[str] = field(default_factory=list)


@dataclass(slots=True)
class BotRecord:
    """Managed bot discovered from the local `bots/` catalog."""

    slug: str
    manifest_path: Path
    manifest: Manifest

    @property
    def display_name(self) -> str:
        """Return the human-facing bot name stored in the OpenClaw configuration."""
        return self.manifest.openclaw.agent_name

    @property
    def role(self) -> str:
        """Return the role/description that summarizes what the bot is expected to do."""
        return self.manifest.project.description


@dataclass(slots=True)
class GeneratedArtifacts:
    """Paths and metadata produced when rendering one bot build bundle."""

    bot: BotRecord
    lock_path: Path
    dockerfile_path: Path
    compose_path: Path
    env_path: Path
    image_tag: str


@dataclass(slots=True)
class AllBotsStackArtifacts:
    """Result of generating the shared compose stack for every managed bot."""

    stack_path: Path
    bot_artifacts: list[GeneratedArtifacts]


@dataclass(slots=True)
class DocumentImprovementResult:
    """Summary of markdown documents updated by the OpenRouter improvement flow."""

    bot: BotRecord
    summary: str
    updated_paths: list[Path]


@dataclass(slots=True)
class RunningBotRecord:
    """Managed bot enriched with runtime details about its running Docker container."""

    bot: BotRecord
    compose_path: Path
    container_name: str

    @property
    def display_name(self) -> str:
        """Return the display name of the running bot."""
        return self.bot.display_name

    @property
    def slug(self) -> str:
        """Return the managed slug of the running bot."""
        return self.bot.slug


@dataclass(slots=True)
class SkillSnapshotResult:
    """Result of reconciling installed runtime skills back into the bot manifest."""

    bot: BotRecord
    manifest_path: Path
    lock_path: Path | None
    added_skill_names: list[str]
    hydrated_skill_names: list[str]


def bots_root(root: str | Path) -> Path:
    """Return the canonical directory that stores all managed bot folders."""
    return Path(root).resolve() / "bots"


def all_bots_compose_path(root: str | Path) -> Path:
    """Return the shared compose path for all managed bots."""
    return bots_root(root) / all_bots_compose_filename()


def _resolve_bot_manifest_path(bot_dir: Path) -> Path | None:
    """Return the preferred manifest path for one bot, with legacy fallback support."""
    for candidate in (bot_dir / MANIFEST_FILENAME, bot_dir / LEGACY_MANIFEST_FILENAME):
        if candidate.exists():
            return candidate
    return None


def _preferred_lockfile_path(bot_dir: Path) -> Path:
    """Return the preferred lockfile path for a bot directory."""
    preferred = bot_dir / LOCKFILE_FILENAME
    legacy = bot_dir / LEGACY_LOCKFILE_FILENAME
    if preferred.exists() or not legacy.exists():
        return preferred
    return legacy


def discover_bots(root: str | Path) -> list[BotRecord]:
    """Discover managed bot manifests."""
    records: list[BotRecord] = []
    root_path = bots_root(root)
    if not root_path.exists():
        return records
    for bot_dir in sorted(path for path in root_path.iterdir() if path.is_dir()):
        manifest_path = _resolve_bot_manifest_path(bot_dir)
        if manifest_path is None:
            continue
        try:
            manifest, _ = load_manifest(manifest_path)
        except OpenEnvError:
            continue
        records.append(
            BotRecord(
                slug=manifest_path.parent.name,
                manifest_path=manifest_path,
                manifest=manifest,
            )
        )
    return records


def create_bot(root: str | Path, answers: BotAnswers) -> BotRecord:
    """Create a new managed bot manifest from interactive answers."""
    slug = slugify_name(answers.display_name)
    bot_dir = bots_root(root) / slug
    if bot_dir.exists():
        raise OpenEnvError(f"Bot `{slug}` already exists.")
    bot_dir.mkdir(parents=True, exist_ok=False)
    manifest = build_bot_manifest(answers)
    _write_agent_docs(bot_dir, manifest.agent)
    manifest_path = bot_dir / MANIFEST_FILENAME
    manifest_path.write_text(render_manifest(manifest), encoding="utf-8")
    write_secret_env(
        secret_env_path(bot_dir),
        answers.secret_names,
        display_name=answers.display_name,
    )
    return load_bot(root, slug)


def update_bot(root: str | Path, existing_slug: str, answers: BotAnswers) -> BotRecord:
    """Update an existing managed bot manifest."""
    current_slug = slugify_name(existing_slug)
    current_dir = bots_root(root) / current_slug
    if not current_dir.exists():
        raise OpenEnvError(f"Bot `{existing_slug}` does not exist.")

    new_slug = slugify_name(answers.display_name)
    target_dir = bots_root(root) / new_slug
    if new_slug != current_slug and target_dir.exists():
        raise OpenEnvError(f"Bot `{new_slug}` already exists.")

    existing_secret_values = load_secret_values(secret_env_path(current_dir))
    manifest = build_bot_manifest(answers)
    if new_slug != current_slug:
        current_dir.rename(target_dir)
    else:
        target_dir = current_dir

    _write_agent_docs(target_dir, manifest.agent)
    manifest_path = target_dir / MANIFEST_FILENAME
    manifest_path.write_text(render_manifest(manifest), encoding="utf-8")
    legacy_manifest_path = target_dir / LEGACY_MANIFEST_FILENAME
    if legacy_manifest_path.exists():
        legacy_manifest_path.unlink()
    write_secret_env(
        secret_env_path(target_dir),
        answers.secret_names,
        existing_values=existing_secret_values,
        display_name=answers.display_name,
    )
    return load_bot(root, new_slug)


def delete_bot(root: str | Path, slug: str) -> None:
    """Delete all managed data for a bot."""
    target = bots_root(root) / slugify_name(slug)
    if not target.exists():
        raise OpenEnvError(f"Bot `{slug}` does not exist.")
    shutil.rmtree(target, ignore_errors=False)


def load_bot(root: str | Path, slug: str) -> BotRecord:
    """Load a single managed bot by slug."""
    bot_dir = bots_root(root) / slugify_name(slug)
    manifest_path = _resolve_bot_manifest_path(bot_dir)
    if manifest_path is None:
        raise OpenEnvError(f"Bot `{slug}` does not exist.")
    manifest, _ = load_manifest(manifest_path)
    return BotRecord(
        slug=manifest_path.parent.name,
        manifest_path=manifest_path,
        manifest=manifest,
    )


def discover_running_bots(root: str | Path) -> list[RunningBotRecord]:
    """Discover managed bots that currently have running Docker containers."""
    running_containers = list_running_container_names()
    records: list[RunningBotRecord] = []
    for bot in discover_bots(root):
        compose_path = _compose_path_for_bot(bot)
        if not compose_path.exists():
            continue
        container_name = _container_name_for_bot(bot)
        if container_name not in running_containers:
            continue
        records.append(
            RunningBotRecord(
                bot=bot,
                compose_path=compose_path,
                container_name=container_name,
            )
        )
    return records


def preview_running_bot_logs(root: str | Path, slug: str, *, tail: int = 120) -> str:
    """Fetch recent logs for a running managed bot."""
    running_bot = _load_running_bot(root, slug)
    return fetch_container_logs(running_bot.container_name, tail=tail)


def create_skill_snapshot(root: str | Path, slug: str) -> SkillSnapshotResult:
    """Snapshot installed skills from a running bot and update the manifest."""
    running_bot = _load_running_bot(root, slug)
    manifest = running_bot.bot.manifest
    captured_skills = snapshot_installed_skills(
        running_bot.container_name,
        workspace=manifest.openclaw.workspace,
    )
    added_skill_names, hydrated_skill_names = _apply_skill_snapshot(
        manifest,
        captured_skills,
    )

    if not added_skill_names and not hydrated_skill_names:
        return SkillSnapshotResult(
            bot=running_bot.bot,
            manifest_path=running_bot.bot.manifest_path,
            lock_path=None,
            added_skill_names=[],
            hydrated_skill_names=[],
        )

    rendered_manifest = render_manifest(manifest)
    running_bot.bot.manifest_path.write_text(rendered_manifest, encoding="utf-8")

    lock_path = _preferred_lockfile_path(running_bot.bot.manifest_path.parent)
    updated_lock_path: Path | None = None
    if lock_path.exists():
        existing_lock = load_lockfile(lock_path)
        lockfile = build_lockfile(
            manifest,
            rendered_manifest,
            resolver=lambda _: {
                "digest": existing_lock.base_image["digest"],
                "resolved_reference": existing_lock.base_image["resolved_reference"],
            },
        )
        write_lockfile(lock_path, lockfile)
        updated_lock_path = lock_path

    return SkillSnapshotResult(
        bot=load_bot(root, slug),
        manifest_path=running_bot.bot.manifest_path,
        lock_path=updated_lock_path,
        added_skill_names=added_skill_names,
        hydrated_skill_names=hydrated_skill_names,
    )


def generate_bot_artifacts(root: str | Path, slug: str) -> GeneratedArtifacts:
    """Generate lockfile, Dockerfile, compose, and env bundle for a bot."""
    bot = load_bot(root, slug)
    manifest, raw_manifest_text = load_manifest(bot.manifest_path)
    lockfile = build_lockfile(manifest, raw_manifest_text)

    lock_path = _preferred_lockfile_path(bot.manifest_path.parent)
    write_lockfile(lock_path, lockfile)
    raw_lock_text = dump_lockfile(lockfile)

    dockerfile_path = bot.manifest_path.with_name("Dockerfile")
    dockerfile_path.write_text(
        render_dockerfile(
            manifest,
            lockfile,
            raw_manifest_text=raw_manifest_text,
            raw_lock_text=raw_lock_text,
        ),
        encoding="utf-8",
    )

    image_tag = default_image_tag(manifest.project.name, manifest.project.version)
    compose_path = bot.manifest_path.parent / default_compose_filename(
        manifest.openclaw.agent_name
    )
    write_compose(compose_path, render_compose(manifest, image_tag))

    env_path = bot.manifest_path.parent / default_env_filename(manifest.openclaw.agent_name)
    sidecar_env_path = secret_env_path(bot.manifest_path.parent)
    existing_values = load_secret_values(env_path)
    if sidecar_env_path.exists():
        existing_values.update(load_secret_values(sidecar_env_path))
    write_env_file(
        env_path,
        render_env_file(manifest, image_tag, existing_values=existing_values),
    )

    return GeneratedArtifacts(
        bot=bot,
        lock_path=lock_path,
        dockerfile_path=dockerfile_path,
        compose_path=compose_path,
        env_path=env_path,
        image_tag=image_tag,
    )


def generate_all_bots_stack(root: str | Path) -> AllBotsStackArtifacts:
    """Generate a shared compose stack with one gateway and all managed bots."""
    bots = discover_bots(root)
    if not bots:
        raise OpenEnvError("No managed bots were found.")
    bot_artifacts = [generate_bot_artifacts(root, bot.slug) for bot in bots]
    specs = [
        AllBotsComposeSpec(
            slug=artifact.bot.slug,
            manifest=artifact.bot.manifest,
            image_tag=artifact.image_tag,
        )
        for artifact in bot_artifacts
    ]
    stack_path = all_bots_compose_path(root)
    write_compose(stack_path, render_all_bots_compose(specs))
    return AllBotsStackArtifacts(
        stack_path=stack_path,
        bot_artifacts=bot_artifacts,
    )


def improve_bot_markdown_documents(
    root: str | Path,
    slug: str,
    *,
    instruction: str,
    api_key: str,
) -> DocumentImprovementResult:
    """Improve bot markdown documents via OpenRouter tool calling."""
    bot = _ensure_bot_agent_documents_materialized(load_bot(root, slug))
    updated_paths: list[Path] = []

    def write_document(relative_path: str, content: str) -> None:
        """Persist one markdown update produced by OpenRouter into the bot directory."""
        target = bot.manifest_path.parent / relative_path
        target.write_text(_normalize_markdown_content(content), encoding="utf-8")
        updated_paths.append(target)

    summary = improve_markdown_documents_with_openrouter(
        api_key=api_key,
        bot_name=bot.display_name,
        context_payload=_bot_document_context(bot),
        instruction=instruction,
        write_document=write_document,
    )
    return DocumentImprovementResult(
        bot=load_bot(root, bot.slug),
        summary=summary,
        updated_paths=_unique_paths(updated_paths),
    )


def build_bot_manifest(answers: BotAnswers) -> Manifest:
    """Build a manifest from bot creation answers."""
    slug = slugify_name(answers.display_name)
    system_packages = _unique_preserving_order(
        [*DEFAULT_SYSTEM_PACKAGES, *answers.system_packages]
    )
    skill_sources = merge_mandatory_skill_sources(answers.skill_sources)
    skills = [
        build_catalog_skill(source, mandatory=source in MANDATORY_SKILL_SOURCES)
        for source in skill_sources
    ]
    tools_md = _render_tools_markdown(
        skill_sources,
        answers.websites,
        answers.databases,
        answers.access_notes,
    )
    memory_seed = [
        f"Primary role: {answers.role}",
        *[f"Website access: {website}" for website in answers.websites],
        *[f"Database access: {database}" for database in answers.databases],
        *answers.access_notes,
    ]
    return Manifest(
        schema_version=1,
        project=ProjectConfig(
            name=slug,
            version="0.1.0",
            description=answers.role,
            runtime="openclaw",
        ),
        runtime=RuntimeConfig(
            base_image="python:3.12-slim",
            python_version="3.12",
            system_packages=system_packages,
            python_packages=answers.python_packages,
            node_packages=answers.node_packages,
            env={"OPENCLAWENV_PROJECT": slug, "PYTHONUNBUFFERED": "1"},
            user="agent",
            workdir="/workspace",
            secret_refs=[],
        ),
        agent=AgentConfig(
            agents_md=(
                "# Agent Contract\n\n"
                f"- Primary role: {answers.role}\n"
                "- Review SOUL.md, USER.md and memory.md before acting.\n"
                "- Never expose secrets or credentials in output.\n"
                "- Prefer reproducible, auditable commands.\n"
            ),
            soul_md=f"# Soul\n\n{answers.role}\n",
            user_md=(
                "# User\n\n"
                f"Bot `{answers.display_name}` supports the workspace and follows its role.\n"
            ),
            identity_md=(
                "# Identity\n\n"
                f"You are {answers.display_name}.\n"
                f"Your primary role is: {answers.role}\n"
            ),
            tools_md=tools_md,
            memory_seed=[item for item in memory_seed if item],
            agents_md_ref=AGENT_DOC_FILENAMES["agents_md"],
            soul_md_ref=AGENT_DOC_FILENAMES["soul_md"],
            user_md_ref=AGENT_DOC_FILENAMES["user_md"],
            identity_md_ref=AGENT_DOC_FILENAMES["identity_md"],
            tools_md_ref=AGENT_DOC_FILENAMES["tools_md"],
            memory_seed_ref=AGENT_DOC_FILENAMES["memory_seed"],
        ),
        skills=skills,
        openclaw=OpenClawConfig(
            agent_id=slug,
            agent_name=answers.display_name,
            workspace="/opt/openclaw/workspace",
            state_dir="/opt/openclaw",
            tools_allow=["shell_command"],
            tools_deny=[],
            sandbox=SandboxConfig(),
        ),
        access=AccessConfig(
            websites=answers.websites,
            databases=answers.databases,
            notes=answers.access_notes,
        ),
    )


def interactive_menu(root: str | Path, language: str | None = None) -> int:
    """Run the interactive menu."""
    base = Path(root).resolve()
    lang = _select_language() if language is None else _require_language(language)
    while True:
        print(f"\n{_message(lang, 'menu_title')}")
        print(_message(lang, "menu_list"))
        print(_message(lang, "menu_add"))
        print(_message(lang, "menu_edit"))
        print(_message(lang, "menu_delete"))
        print(_message(lang, "menu_running"))
        print(_message(lang, "menu_exit"))
        choice = input(_message(lang, "menu_prompt")).strip()

        if choice == "1":
            _interactive_browse_bots(base, lang)
            continue
        if choice == "2":
            _interactive_add_bot(base, lang)
            continue
        if choice == "3":
            _interactive_edit_bot(base, lang)
            continue
        if choice == "4":
            _interactive_delete_bot(base, lang)
            continue
        if choice == "5":
            _interactive_browse_running_bots(base, lang)
            continue
        if choice == "6":
            print(_message(lang, "menu_exit_message"))
            return 0
        print(_message(lang, "menu_unknown"))


def _interactive_browse_bots(root: Path, lang: str) -> None:
    """Show the managed bot list and dispatch to bot-specific actions or shared stack generation."""
    bots = discover_bots(root)
    if not bots:
        print(_message(lang, "no_bots"))
        return
    _show_bots(root, lang)
    selection = input(_message(lang, "browse_prompt")).strip()
    if not selection:
        return
    if selection.lower() == "a":
        try:
            stack = generate_all_bots_stack(root)
        except OpenEnvError as exc:
            print(_message(lang, "generate_all_failed", error=exc))
            return
        print(_message(lang, "generated_all_compose", path=stack.stack_path))
        print(_message(lang, "generated_all_prepared", count=len(stack.bot_artifacts)))
        return
    bot = _bot_from_selection(bots, selection, lang)
    if bot is None:
        return
    _interactive_bot_actions(root, bot, lang)


def _interactive_browse_running_bots(root: Path, lang: str) -> None:
    """Show running managed bots and dispatch to runtime-specific actions."""
    try:
        running_bots = discover_running_bots(root)
    except OpenEnvError as exc:
        print(_message(lang, "running_failed", error=exc))
        return
    if not running_bots:
        print(_message(lang, "running_no_bots"))
        return
    _show_running_bots(running_bots, lang)
    selection = input(_message(lang, "running_prompt")).strip()
    if not selection:
        return
    running_bot = _running_bot_from_selection(running_bots, selection, lang)
    if running_bot is None:
        return
    _interactive_running_bot_actions(root, running_bot, lang)


def _show_bots(root: Path, lang: str) -> None:
    """Print a localized summary of all managed bots."""
    bots = discover_bots(root)
    if not bots:
        print(_message(lang, "no_bots"))
        return
    print(f"\n{_message(lang, 'bots_header')}")
    for index, bot in enumerate(bots, start=1):
        print(f"{index}. {bot.display_name} [{bot.slug}]")
        print(f"   {_message(lang, 'role_label')}: {bot.role}")
        print(f"   {_message(lang, 'manifest_label')}: {bot.manifest_path}")
    print(_message(lang, "bots_generate_stack"))


def _show_running_bots(running_bots: Iterable[RunningBotRecord], lang: str) -> None:
    """Print a localized summary of running bot containers and their compose artifacts."""
    print(f"\n{_message(lang, 'running_header')}")
    for index, running_bot in enumerate(running_bots, start=1):
        print(f"{index}. {running_bot.display_name} [{running_bot.slug}]")
        print(f"   {_message(lang, 'role_label')}: {running_bot.bot.role}")
        print(f"   {_message(lang, 'manifest_label')}: {running_bot.bot.manifest_path}")
        print(f"   {_message(lang, 'compose_label')}: {running_bot.compose_path}")
        print(f"   {_message(lang, 'container_label')}: {running_bot.container_name}")


def _interactive_bot_actions(root: Path, bot: BotRecord, lang: str) -> None:
    """Handle artifact generation and document improvement actions for one managed bot."""
    print(f"\n{_message(lang, 'bot_actions_title', display_name=bot.display_name)}")
    print(_message(lang, "bot_actions_generate"))
    print(_message(lang, "bot_actions_improve_docs"))
    print(_message(lang, "bot_actions_back"))
    choice = input(_message(lang, "bot_actions_prompt")).strip()
    if choice == "1":
        try:
            artifacts = generate_bot_artifacts(root, bot.slug)
        except OpenEnvError as exc:
            print(_message(lang, "generate_failed", error=exc))
            return
        print(_message(lang, "generated_lockfile", path=artifacts.lock_path))
        print(_message(lang, "generated_dockerfile", path=artifacts.dockerfile_path))
        print(_message(lang, "generated_compose", path=artifacts.compose_path))
        print(_message(lang, "generated_env", path=artifacts.env_path))
        return
    if choice == "2":
        instruction = input(_message(lang, "edit_docs_prompt")).strip()
        try:
            api_key = _resolve_openrouter_api_key(root, lang)
            result = improve_bot_markdown_documents(
                root,
                bot.slug,
                instruction=instruction,
                api_key=api_key,
            )
        except OpenEnvError as exc:
            print(_message(lang, "edit_docs_failed", error=exc))
            return
        print(_message(lang, "edit_docs_done", summary=result.summary))
        for path in result.updated_paths:
            print(_message(lang, "edit_docs_updated_file", path=path))
        return
    if choice == "3":
        return
    print(_message(lang, "bot_actions_unknown"))


def _interactive_running_bot_actions(root: Path, running_bot: RunningBotRecord, lang: str) -> None:
    """Handle runtime actions such as log viewing and skill snapshots for a running bot."""
    print(
        f"\n{_message(lang, 'running_actions_title', display_name=running_bot.display_name)}"
    )
    print(_message(lang, "running_actions_logs"))
    print(_message(lang, "running_actions_snapshot"))
    print(_message(lang, "running_actions_back"))
    choice = input(_message(lang, "running_actions_prompt")).strip()
    if choice == "1":
        try:
            logs = preview_running_bot_logs(root, running_bot.slug)
        except OpenEnvError as exc:
            print(_message(lang, "logs_failed", error=exc))
            return
        print(_message(lang, "logs_header", display_name=running_bot.display_name))
        print(logs.rstrip() if logs.strip() else _message(lang, "logs_empty"))
        return
    if choice == "2":
        try:
            result = create_skill_snapshot(root, running_bot.slug)
        except OpenEnvError as exc:
            print(_message(lang, "snapshot_failed", error=exc))
            return
        if not result.added_skill_names and not result.hydrated_skill_names:
            print(_message(lang, "snapshot_no_changes"))
            return
        print(_message(lang, "snapshot_manifest", path=result.manifest_path))
        if result.lock_path is not None:
            print(_message(lang, "snapshot_lockfile", path=result.lock_path))
        for name in result.added_skill_names:
            print(_message(lang, "snapshot_added_skill", name=name))
        for name in result.hydrated_skill_names:
            print(_message(lang, "snapshot_hydrated_skill", name=name))
        return
    if choice == "3":
        return
    print(_message(lang, "running_actions_unknown"))


def _interactive_add_bot(root: Path, lang: str) -> None:
    """Collect localized prompts required to create a new managed bot."""
    print(f"\n{_message(lang, 'add_title')}")
    answers = BotAnswers(
        display_name=_prompt_nonempty(_message(lang, "prompt_name"), lang),
        role=_prompt_nonempty(_message(lang, "prompt_role"), lang),
        skill_sources=_prompt_csv(_message(lang, "prompt_skills")),
        system_packages=_prompt_csv(_message(lang, "prompt_system_packages")),
        python_packages=_prompt_csv(_message(lang, "prompt_python_packages")),
        node_packages=_prompt_csv(_message(lang, "prompt_node_packages")),
        secret_names=_prompt_csv(_message(lang, "prompt_secrets")),
        websites=_prompt_csv(_message(lang, "prompt_websites")),
        databases=_prompt_csv(_message(lang, "prompt_databases")),
        access_notes=_prompt_csv(_message(lang, "prompt_access_notes")),
    )
    try:
        record = create_bot(root, answers)
    except OpenEnvError as exc:
        print(_message(lang, "create_failed", error=exc))
        return
    print(_message(lang, "created", display_name=record.display_name, path=record.manifest_path))


def _interactive_edit_bot(root: Path, lang: str) -> None:
    """Collect localized prompts required to update an existing managed bot."""
    bots = discover_bots(root)
    if not bots:
        print(_message(lang, "edit_no_bots"))
        return
    bot = _select_bot(root, _message(lang, "edit_select"), lang)
    if bot is None:
        return

    current = _answers_from_record(bot)
    print(f"\n{_message(lang, 'edit_title', display_name=bot.display_name)}")
    answers = BotAnswers(
        display_name=_prompt_with_default(
            _message(lang, "prompt_name"),
            current.display_name,
        ),
        role=_prompt_with_default(_message(lang, "prompt_role"), current.role),
        skill_sources=_prompt_csv_with_default(
            _message(lang, "prompt_skills"),
            current.skill_sources,
        ),
        system_packages=_prompt_csv_with_default(
            _message(lang, "prompt_system_packages"),
            current.system_packages,
        ),
        python_packages=_prompt_csv_with_default(
            _message(lang, "prompt_python_packages"),
            current.python_packages,
        ),
        node_packages=_prompt_csv_with_default(
            _message(lang, "prompt_node_packages"),
            current.node_packages,
        ),
        secret_names=_prompt_csv_with_default(
            _message(lang, "prompt_secrets"),
            current.secret_names,
        ),
        websites=_prompt_csv_with_default(
            _message(lang, "prompt_websites"),
            current.websites,
        ),
        databases=_prompt_csv_with_default(
            _message(lang, "prompt_databases"),
            current.databases,
        ),
        access_notes=_prompt_csv_with_default(
            _message(lang, "prompt_access_notes"),
            current.access_notes,
        ),
    )
    try:
        record = update_bot(root, bot.slug, answers)
    except OpenEnvError as exc:
        print(_message(lang, "update_failed", error=exc))
        return
    print(_message(lang, "updated", display_name=record.display_name, path=record.manifest_path))


def _interactive_delete_bot(root: Path, lang: str) -> None:
    """Confirm and delete a managed bot from the local catalog."""
    bots = discover_bots(root)
    if not bots:
        print(_message(lang, "delete_no_bots"))
        return
    bot = _select_bot(root, _message(lang, "delete_select"), lang)
    if bot is None:
        return
    confirm = input(
        _message(
            lang,
            "delete_confirm",
            display_name=bot.display_name,
            slug=bot.slug,
        )
    ).strip().lower()
    if confirm not in YES_WORDS[lang]:
        print(_message(lang, "delete_cancelled"))
        return
    try:
        delete_bot(root, bot.slug)
    except OpenEnvError as exc:
        print(_message(lang, "delete_failed", error=exc))
        return
    print(_message(lang, "deleted", display_name=bot.display_name))


def _prompt_nonempty(prompt: str, lang: str) -> str:
    """Prompt until the user provides a non-empty value."""
    while True:
        value = input(prompt).strip()
        if value:
            return value
        print(_message(lang, "required_field"))


def _prompt_with_default(prompt: str, default: str) -> str:
    """Prompt once and fall back to a default value when the input is empty."""
    value = input(f"{prompt}[{default}] ").strip()
    return value or default


def _prompt_csv(prompt: str) -> list[str]:
    """Parse a comma-separated prompt response into a list of trimmed values."""
    raw = input(prompt).strip()
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def _prompt_csv_with_default(prompt: str, default: list[str]) -> list[str]:
    """Parse a comma-separated prompt response while allowing the caller to keep defaults."""
    default_text = ", ".join(default)
    raw = input(f"{prompt}[{default_text}] ").strip()
    if not raw:
        return list(default)
    return [item.strip() for item in raw.split(",") if item.strip()]


def _select_bot(root: Path, prompt: str, lang: str) -> BotRecord | None:
    """Display bots, collect a selection, and resolve it to a managed bot record."""
    bots = discover_bots(root)
    _show_bots(root, lang)
    selection = _prompt_nonempty(prompt, lang)
    return _bot_from_selection(bots, selection, lang)


def _bot_from_selection(
    bots: list[BotRecord],
    selection: str,
    lang: str,
) -> BotRecord | None:
    """Convert a one-based menu selection into a managed bot record."""
    if not selection.isdigit():
        print(_message(lang, "invalid_number"))
        return None
    index = int(selection) - 1
    if index < 0 or index >= len(bots):
        print(_message(lang, "out_of_range"))
        return None
    return bots[index]


def _running_bot_from_selection(
    bots: list[RunningBotRecord],
    selection: str,
    lang: str,
) -> RunningBotRecord | None:
    """Convert a one-based menu selection into a running bot record."""
    if not selection.isdigit():
        print(_message(lang, "invalid_number"))
        return None
    index = int(selection) - 1
    if index < 0 or index >= len(bots):
        print(_message(lang, "out_of_range"))
        return None
    return bots[index]


def _select_language() -> str:
    """Prompt for the menu language until a supported alias is chosen."""
    while True:
        print(f"\n{_message('pl', 'language_title')}")
        print(_message("pl", "language_option_pl"))
        print(_message("pl", "language_option_en"))
        selection = input(_message("pl", "language_prompt")).strip()
        language = _normalize_language(selection)
        if language is not None:
            return language
        print(_message("pl", "language_invalid"))


def _normalize_language(selection: str) -> str | None:
    """Map a free-form language selection to the canonical `pl` or `en` code."""
    return LANGUAGE_ALIASES.get(selection.strip().lower())


def _require_language(language: str) -> str:
    """Validate and normalize a language code used by non-interactive callers."""
    normalized = _normalize_language(language)
    if normalized is None:
        raise OpenEnvError(f"Unsupported menu language: {language}")
    return normalized


def _message(language: str, key: str, **kwargs: object) -> str:
    """Return one localized UI message formatted with the supplied keyword values."""
    return MESSAGES[language][key].format(**kwargs)


def _answers_from_record(bot: BotRecord) -> BotAnswers:
    """Convert a stored bot manifest back into editable interactive answers."""
    system_packages = [
        package
        for package in bot.manifest.runtime.system_packages
        if package not in DEFAULT_SYSTEM_PACKAGES
    ]
    return BotAnswers(
        display_name=bot.display_name,
        role=bot.role,
        skill_sources=[
            skill.source or skill.name
            for skill in bot.manifest.skills
            if not is_mandatory_skill(skill)
        ],
        system_packages=system_packages,
        python_packages=list(bot.manifest.runtime.python_packages),
        node_packages=list(bot.manifest.runtime.node_packages),
        secret_names=[secret.name for secret in bot.manifest.runtime.secret_refs],
        websites=list(bot.manifest.access.websites),
        databases=list(bot.manifest.access.databases),
        access_notes=list(bot.manifest.access.notes),
    )


def _write_agent_docs(bot_dir: Path, agent: AgentConfig) -> None:
    """Write all agent markdown documents referenced by the manifest into the bot directory."""
    _write_agent_doc(bot_dir, agent.agents_md_ref, agent.agents_md)
    _write_agent_doc(bot_dir, agent.soul_md_ref, agent.soul_md)
    _write_agent_doc(bot_dir, agent.user_md_ref, agent.user_md)
    if agent.identity_md is not None:
        _write_agent_doc(bot_dir, agent.identity_md_ref, agent.identity_md)
    if agent.tools_md is not None:
        _write_agent_doc(bot_dir, agent.tools_md_ref, agent.tools_md)
    if agent.memory_seed_ref is not None:
        _write_agent_doc(bot_dir, agent.memory_seed_ref, _memory_seed_text(agent.memory_seed))


def _write_agent_doc(bot_dir: Path, relative_path: str | None, content: str) -> None:
    """Write one referenced agent markdown file when the manifest defines a target path."""
    if relative_path is None:
        return
    target_path = bot_dir / relative_path
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(content, encoding="utf-8")


def _memory_seed_text(lines: list[str]) -> str:
    """Render memory seed entries back into the newline-separated markdown file format."""
    if not lines:
        return ""
    return "\n".join(lines).strip() + "\n"


def _resolve_openrouter_api_key(root: Path, lang: str) -> str:
    """Load the OpenRouter API key from the environment or prompt and persist it."""
    api_key = get_project_env_value(root, "OPENROUTER_API_KEY")
    if api_key:
        return api_key
    print(_message(lang, "openrouter_key_missing"))
    provided = getpass(_message(lang, "openrouter_key_prompt")).strip()
    if not provided:
        raise OpenEnvError("OPENROUTER_API_KEY is required for this action.")
    env_path = write_project_env_value(root, "OPENROUTER_API_KEY", provided)
    print(_message(lang, "openrouter_key_saved", path=env_path))
    return provided


def _ensure_bot_agent_documents_materialized(bot: BotRecord) -> BotRecord:
    """Ensure every agent document exists as a file before document-improvement workflows run."""
    bot_dir = bot.manifest_path.parent
    manifest = bot.manifest
    changed = False
    agent = manifest.agent
    document_specs = [
        ("agents_md", "agents_md_ref", AGENT_DOC_FILENAMES["agents_md"], agent.agents_md),
        ("soul_md", "soul_md_ref", AGENT_DOC_FILENAMES["soul_md"], agent.soul_md),
        ("user_md", "user_md_ref", AGENT_DOC_FILENAMES["user_md"], agent.user_md),
        (
            "identity_md",
            "identity_md_ref",
            AGENT_DOC_FILENAMES["identity_md"],
            agent.identity_md,
        ),
        ("tools_md", "tools_md_ref", AGENT_DOC_FILENAMES["tools_md"], agent.tools_md),
        (
            "memory_seed",
            "memory_seed_ref",
            AGENT_DOC_FILENAMES["memory_seed"],
            _memory_seed_text(agent.memory_seed),
        ),
    ]
    for _, ref_attr, default_ref, content in document_specs:
        if content is None:
            continue
        reference = getattr(agent, ref_attr)
        if reference is None:
            setattr(agent, ref_attr, default_ref)
            reference = default_ref
            changed = True
        target = bot_dir / reference
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
    if changed:
        bot.manifest_path.write_text(render_manifest(manifest), encoding="utf-8")
        return load_bot(bot.manifest_path.parent.parent.parent, bot.slug)
    return bot


def _bot_document_context(bot: BotRecord) -> dict[str, object]:
    """Build the structured context payload sent to OpenRouter for document editing."""
    documents = _bot_documents(bot.manifest)
    return {
        "bot": {
            "name": bot.display_name,
            "slug": bot.slug,
            "project_name": bot.manifest.project.name,
            "version": bot.manifest.project.version,
            "role": bot.manifest.project.description,
            "skills": [
                {
                    "name": skill.name,
                    "description": skill.description,
                    "source": skill.source,
                }
                for skill in bot.manifest.skills
            ],
            "websites": list(bot.manifest.access.websites),
            "databases": list(bot.manifest.access.databases),
            "notes": list(bot.manifest.access.notes),
            "secret_names": [
                secret.name for secret in bot.manifest.runtime.secret_refs
            ],
            "system_packages": list(bot.manifest.runtime.system_packages),
            "python_packages": list(bot.manifest.runtime.python_packages),
            "node_packages": list(bot.manifest.runtime.node_packages),
        },
        "documents": documents,
    }


def _bot_documents(manifest: Manifest) -> dict[str, str]:
    """Return the markdown documents that OpenRouter is allowed to inspect and rewrite."""
    documents = {
        manifest.agent.agents_md_ref or AGENT_DOC_FILENAMES["agents_md"]: manifest.agent.agents_md,
        manifest.agent.soul_md_ref or AGENT_DOC_FILENAMES["soul_md"]: manifest.agent.soul_md,
        manifest.agent.user_md_ref or AGENT_DOC_FILENAMES["user_md"]: manifest.agent.user_md,
        manifest.agent.memory_seed_ref
        or AGENT_DOC_FILENAMES["memory_seed"]: _memory_seed_text(manifest.agent.memory_seed),
    }
    if manifest.agent.identity_md is not None:
        documents[
            manifest.agent.identity_md_ref or AGENT_DOC_FILENAMES["identity_md"]
        ] = manifest.agent.identity_md
    if manifest.agent.tools_md is not None:
        documents[manifest.agent.tools_md_ref or AGENT_DOC_FILENAMES["tools_md"]] = (
            manifest.agent.tools_md
        )
    return dict(sorted(documents.items()))


def _normalize_markdown_content(content: str) -> str:
    """Normalize saved markdown so files end with exactly one trailing newline."""
    return content.rstrip() + "\n"


def _unique_paths(paths: list[Path]) -> list[Path]:
    """Deduplicate updated document paths while preserving their first-seen order."""
    seen: set[Path] = set()
    result: list[Path] = []
    for path in paths:
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            result.append(path)
    return result


def _render_tools_markdown(
    skill_sources: list[str],
    websites: list[str],
    databases: list[str],
    access_notes: list[str],
) -> str:
    """Render the default `TOOLS.md` document derived from bot answers."""
    lines = ["# Tools", ""]
    if skill_sources:
        lines.append("## Skill Sources")
        lines.extend(f"- {source}" for source in skill_sources)
        lines.append("")
    if websites:
        lines.append("## Websites")
        lines.extend(f"- {website}" for website in websites)
        lines.append("")
    if databases:
        lines.append("## Databases")
        lines.extend(f"- {database}" for database in databases)
        lines.append("")
    if access_notes:
        lines.append("## Access Notes")
        lines.extend(f"- {note}" for note in access_notes)
        lines.append("")
    lines.append("Use the allowed tools with least privilege and document important actions.")
    return "\n".join(lines).strip() + "\n"


def _unique_preserving_order(items: list[str]) -> list[str]:
    """Deduplicate text items while preserving the original user-provided order."""
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _compose_path_for_bot(bot: BotRecord) -> Path:
    """Return the expected compose file path for a managed bot."""
    return bot.manifest_path.parent / default_compose_filename(bot.display_name)


def _container_name_for_bot(bot: BotRecord) -> str:
    """Return the expected gateway container name for a managed bot."""
    return gateway_container_name(bot.display_name)


def _load_running_bot(root: str | Path, slug: str) -> RunningBotRecord:
    """Load a managed bot and verify that its compose bundle is currently running."""
    bot = load_bot(root, slug)
    compose_path = _compose_path_for_bot(bot)
    if not compose_path.exists():
        raise OpenEnvError(f"Compose file not found for bot `{bot.slug}`: {compose_path}")
    container_name = _container_name_for_bot(bot)
    running_containers = list_running_container_names()
    if container_name not in running_containers:
        raise OpenEnvError(f"Bot `{bot.slug}` is not currently running.")
    return RunningBotRecord(
        bot=bot,
        compose_path=compose_path,
        container_name=container_name,
    )


def _apply_skill_snapshot(
    manifest: Manifest,
    captured_skills: Iterable[CapturedSkill],
) -> tuple[list[str], list[str]]:
    """Merge captured runtime skills into the manifest and report what changed."""
    existing_by_name = {skill.name: skill for skill in manifest.skills}
    added_skill_names: list[str] = []
    hydrated_skill_names: list[str] = []
    for captured in sorted(captured_skills, key=lambda item: item.name):
        existing = existing_by_name.get(captured.name)
        if existing is None:
            manifest.skills.append(
                SkillConfig(
                    name=captured.name,
                    description=captured.description,
                    content=captured.content,
                    source=captured.source,
                    assets=dict(captured.assets),
                )
            )
            added_skill_names.append(captured.name)
            continue
        if _hydrate_skill_from_snapshot(existing, captured):
            hydrated_skill_names.append(captured.name)
    return added_skill_names, hydrated_skill_names


def _hydrate_skill_from_snapshot(skill: SkillConfig, captured: CapturedSkill) -> bool:
    """Fill missing skill fields from a runtime snapshot without overwriting authored content."""
    changed = False
    if skill.content is None and captured.content.strip():
        skill.content = captured.content
        changed = True
    if not skill.assets and captured.assets:
        skill.assets = dict(captured.assets)
        changed = True
    if skill.source is None and captured.source is not None:
        skill.source = captured.source
        changed = True
    if (
        changed
        and captured.description
        and (
            skill.description.startswith("Always-installed skill referenced")
            or skill.description.startswith("Skill referenced from catalog source")
        )
    ):
        skill.description = captured.description
    return changed
