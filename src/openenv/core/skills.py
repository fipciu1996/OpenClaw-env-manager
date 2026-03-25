"""Shared skill defaults and normalization helpers."""

from __future__ import annotations

from collections.abc import Iterable

from openenv.core.models import SkillConfig
from openenv.core.utils import slugify_name


FREERIDE_SKILL_SOURCE = "freeride"
AGENT_BROWSER_SKILL_SOURCE = "agent-browser-clawdbot"
SKILL_SOURCE_NAME_OVERRIDES: dict[str, str] = {
    FREERIDE_SKILL_SOURCE: "free-ride",
}
FREERIDE_SKILL_NAME = SKILL_SOURCE_NAME_OVERRIDES[FREERIDE_SKILL_SOURCE]
MANDATORY_SKILL_SOURCES: tuple[str, ...] = (
    "deus-context-engine",
    "self-improving-agent",
    "skill-security-review",
    FREERIDE_SKILL_SOURCE,
    AGENT_BROWSER_SKILL_SOURCE,
)


def mandatory_skill_names() -> tuple[str, ...]:
    """Return the canonical skill directory names for mandatory skill sources."""
    return tuple(skill_name_for_source(source) for source in MANDATORY_SKILL_SOURCES)


def catalog_install_dir_name(source: str) -> str:
    """Return the default directory name created by ClawHub for a catalog source."""
    source_name = source.rsplit("/", 1)[-1]
    return slugify_name(source_name)


def skill_name_for_source(source: str) -> str:
    """Convert a catalog source into the local skill directory name."""
    source_name = source.rsplit("/", 1)[-1]
    return SKILL_SOURCE_NAME_OVERRIDES.get(source_name, catalog_install_dir_name(source))


def build_catalog_skill(source: str, *, mandatory: bool = False) -> SkillConfig:
    """Build a manifest skill entry for an externally referenced catalog skill."""
    descriptor = "Always-installed skill" if mandatory else "Skill"
    return SkillConfig(
        name=skill_name_for_source(source),
        description=f"{descriptor} referenced from catalog source {source}",
        source=source,
    )


def merge_mandatory_skill_sources(skill_sources: Iterable[str]) -> list[str]:
    """Merge extra skill sources with the mandatory skill set without duplicates."""
    ordered_sources = list(MANDATORY_SKILL_SOURCES)
    seen = set(ordered_sources)
    for source in skill_sources:
        if source not in seen:
            seen.add(source)
            ordered_sources.append(source)
    return ordered_sources


def ensure_mandatory_skills(skills: Iterable[SkillConfig]) -> list[SkillConfig]:
    """Append mandatory skills when they are missing from the manifest."""
    normalized = list(skills)
    present_sources = {skill.source for skill in normalized if skill.source is not None}
    present_names = {skill.name for skill in normalized}
    for source in MANDATORY_SKILL_SOURCES:
        skill_name = skill_name_for_source(source)
        if source in present_sources or skill_name in present_names:
            continue
        normalized.append(build_catalog_skill(source, mandatory=True))
    return normalized


def catalog_skill_specs(skills: Iterable[SkillConfig]) -> list[tuple[str, str]]:
    """Return ordered `(name, source)` pairs for skills referenced from an external catalog."""
    ordered: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for skill in skills:
        if skill.source is None:
            continue
        spec = (skill.name, skill.source)
        if spec in seen:
            continue
        seen.add(spec)
        ordered.append(spec)
    return ordered


def is_mandatory_skill_reference(reference: str) -> bool:
    """Return whether a source or local skill name belongs to the mandatory set."""
    return reference in MANDATORY_SKILL_SOURCES or reference in mandatory_skill_names()


def is_mandatory_skill(skill: SkillConfig) -> bool:
    """Return whether a skill entry belongs to the mandatory skill set."""
    if skill.source is not None and skill.source in MANDATORY_SKILL_SOURCES:
        return True
    return skill.name in mandatory_skill_names()
