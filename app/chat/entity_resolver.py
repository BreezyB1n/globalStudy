from __future__ import annotations

from collections import OrderedDict
import re

from app.chat.models import EntityResolution, ProjectCatalogEntry
from app.schemas.chat import ChatMessage

COMPARE_KEYWORDS = ("compare", "comparison", "difference", "different", "相比", "比较", "差别", "区别")

SCHOOL_ALIAS_OVERRIDES: dict[str, tuple[str, ...]] = {
    "mit": ("mit", "massachusetts institute of technology", "麻省理工"),
    "imperial": ("imperial", "imperial college", "imperial college london", "帝国理工", "帝国理工学院"),
    "oxford": ("oxford", "university of oxford", "牛津"),
    "cambridge": ("cambridge", "university of cambridge", "剑桥"),
    "harvard": ("harvard", "哈佛"),
    "stanford": ("stanford", "斯坦福"),
    "edinburgh": ("edinburgh", "university of edinburgh", "爱丁堡"),
    "ucl": ("ucl", "university college london", "伦敦大学学院"),
    "nus": ("nus", "national university of singapore", "新加坡国立"),
    "eth-zurich": ("eth", "eth zurich", "苏黎世联邦理工"),
}


class EntityResolver:
    def __init__(self, projects: list[ProjectCatalogEntry]) -> None:
        self.projects = projects

    def resolve(self, *, current_question: str, messages: list[ChatMessage]) -> EntityResolution:
        current_matches = self._find_projects_in_text(current_question)
        historical_matches = self._collect_historical_matches(messages[:-1])
        is_comparison = _looks_like_comparison(current_question)

        primary_project: ProjectCatalogEntry | None = None
        comparison_project: ProjectCatalogEntry | None = None

        if len(current_matches) >= 2:
            primary_project = current_matches[0]
            comparison_project = current_matches[1]
        elif len(current_matches) == 1:
            primary_project = current_matches[0]
            if is_comparison:
                comparison_project = _first_different_project(historical_matches, primary_project)
        else:
            if historical_matches:
                primary_project = historical_matches[0]
            if is_comparison and len(historical_matches) >= 2:
                comparison_project = _first_different_project(historical_matches[1:], primary_project)

        if primary_project is None:
            return EntityResolution(unresolved_reason="missing_project")
        if is_comparison and comparison_project is None:
            return EntityResolution(primary_project=primary_project, unresolved_reason="missing_comparison")

        return EntityResolution(
            primary_project=primary_project,
            comparison_project=comparison_project,
        )

    def _collect_historical_matches(self, messages: list[ChatMessage]) -> list[ProjectCatalogEntry]:
        ordered: OrderedDict[str, ProjectCatalogEntry] = OrderedDict()
        for message in reversed(messages):
            for project in self._find_projects_in_text(message.content):
                ordered.setdefault(_project_key(project), project)
        return list(ordered.values())

    def _find_projects_in_text(self, text: str) -> list[ProjectCatalogEntry]:
        normalized_text = _normalize_text(text)
        matched_by_program: list[ProjectCatalogEntry] = []
        matched_by_school: list[ProjectCatalogEntry] = []

        for project in self.projects:
            if any(_alias_matches(normalized_text, alias) for alias in _program_aliases(project)):
                matched_by_program.append(project)
                continue
            if any(_alias_matches(normalized_text, alias) for alias in _school_aliases(project)):
                matched_by_school.append(project)

        deduped: OrderedDict[str, ProjectCatalogEntry] = OrderedDict()
        for project in [*matched_by_program, *matched_by_school]:
            deduped.setdefault(_project_key(project), project)
        return list(deduped.values())


def _first_different_project(
    projects: list[ProjectCatalogEntry],
    current_project: ProjectCatalogEntry | None,
) -> ProjectCatalogEntry | None:
    if current_project is None:
        return projects[0] if projects else None
    current_key = _project_key(current_project)
    for project in projects:
        if _project_key(project) != current_key:
            return project
    return None


def _project_key(project: ProjectCatalogEntry) -> str:
    return f"{project.school_slug}:{project.program_slug}"


def _school_aliases(project: ProjectCatalogEntry) -> tuple[str, ...]:
    aliases = {
        _normalize_text(project.school_name),
        _normalize_text(project.school_slug.replace("-", " ")),
    }
    aliases.update(_normalize_text(alias) for alias in SCHOOL_ALIAS_OVERRIDES.get(project.school_slug, ()))
    return tuple(alias for alias in aliases if alias)


def _program_aliases(project: ProjectCatalogEntry) -> tuple[str, ...]:
    aliases = {
        _normalize_text(project.program_name),
        _normalize_text(project.program_slug.replace("-", " ")),
    }
    program_name = _normalize_text(project.program_name)
    if "artificial intelligence" in program_name:
        aliases.update({"ai", "ai 硕士", "人工智能", "人工智能硕士"})
    if project.degree_type:
        aliases.add(_normalize_text(f"{project.degree_type} {project.program_name}"))
    return tuple(alias for alias in aliases if alias)


def _looks_like_comparison(question: str) -> bool:
    normalized = _normalize_text(question)
    return any(keyword in normalized for keyword in COMPARE_KEYWORDS)


def _alias_matches(normalized_text: str, alias: str) -> bool:
    if not alias:
        return False
    if _contains_cjk(alias):
        return alias in normalized_text
    pattern = rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])"
    return re.search(pattern, normalized_text) is not None


def _contains_cjk(value: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in value)


def _normalize_text(value: str) -> str:
    return " ".join(value.lower().strip().split())
