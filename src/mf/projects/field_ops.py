"""Field schema, coercion, validation, and change tracking for project overrides.

This module re-exports shared infrastructure from ``mf.core.field_ops`` and adds
the project-specific FIELD_SCHEMA plus thin wrappers that bind the schema.  All
public names used by ``projects/commands.py`` are preserved for backward
compatibility.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

# Re-export shared types so existing imports keep working
from mf.core.field_ops import (  # noqa: F401 -- re-exports
    ChangeResult,
    DictDatabaseAdapter,
    FieldDef,
    FieldType,
    coerce_value,
    parse_field_path,
    print_change,
)
from mf.core.field_ops import (
    modify_list_field as _modify_list,
)
from mf.core.field_ops import (
    set_field as _set_field,
)
from mf.core.field_ops import (
    unset_field as _unset_field,
)
from mf.core.field_ops import (
    validate_field as _validate_field,
)

if TYPE_CHECKING:
    from mf.core.database import ProjectsDatabase


# -- Field schema for all known project override fields --

FIELD_SCHEMA: dict[str, FieldDef] = {
    # Core metadata
    "title": FieldDef(FieldType.STRING, "Project display title"),
    "name": FieldDef(FieldType.STRING, "Project name"),
    "abstract": FieldDef(FieldType.STRING, "Project description/abstract"),
    "description": FieldDef(FieldType.STRING, "Short description"),
    # Classification
    "category": FieldDef(
        FieldType.STRING,
        "Project category",
        choices=[
            "library",
            "tool",
            "language",
            "framework",
            "application",
            "research",
            "other",
        ],
    ),
    "maturity": FieldDef(
        FieldType.STRING,
        "Project maturity level",
        choices=["experimental", "alpha", "beta", "stable", "maintenance", "archived"],
    ),
    "stars": FieldDef(FieldType.INT, "Featured rating (0-5)", min_val=0, max_val=5),
    # Visibility
    "featured": FieldDef(FieldType.BOOL, "Show in featured section"),
    "hide": FieldDef(FieldType.BOOL, "Hide from listings"),
    # Lists
    "tags": FieldDef(FieldType.STRING_LIST, "Project tags"),
    "languages": FieldDef(FieldType.STRING_LIST, "Programming languages"),
    "content_sections": FieldDef(FieldType.STRING_LIST, "Rich project content sections"),
    "related_posts": FieldDef(FieldType.STRING_LIST, "Related blog post paths"),
    "related_papers": FieldDef(FieldType.STRING_LIST, "Related paper paths"),
    "authors": FieldDef(FieldType.STRING_LIST, "Project authors"),
    # Rich project
    "rich_project": FieldDef(FieldType.BOOL, "Enable branch bundle (rich project)"),
    # Nested dicts
    "external_docs": FieldDef(FieldType.DICT, "External documentation URLs"),
    "packages": FieldDef(FieldType.DICT, "Package registry names (pypi, npm, crates)"),
    "sources": FieldDef(FieldType.DICT, "Source URLs (github, documentation)"),
    "metrics": FieldDef(FieldType.DICT, "Project metrics (stars, downloads, citations)"),
    # Strings
    "primary_language": FieldDef(FieldType.STRING, "Primary programming language"),
    "demo_url": FieldDef(FieldType.STRING, "Demo or live site URL"),
    "github": FieldDef(FieldType.STRING, "GitHub repository URL"),
    "year_started": FieldDef(FieldType.INT, "Year project started", min_val=1970, max_val=2100),
    "status": FieldDef(
        FieldType.STRING,
        "Project status",
        choices=["active", "inactive", "archived", "maintenance"],
    ),
    "type": FieldDef(
        FieldType.STRING,
        "Project type",
        choices=["library", "tool", "language", "framework", "application"],
    ),
    "license": FieldDef(FieldType.STRING, "License identifier (e.g. MIT, Apache-2.0)"),
    # Hugo settings
    "aliases": FieldDef(FieldType.STRING_LIST, "Hugo URL aliases for redirects"),
}


# ---------------------------------------------------------------------------
# Thin wrappers that bind the project schema
# ---------------------------------------------------------------------------


def validate_field(field: str, value: Any) -> list[str]:
    """Validate a field value against the project schema."""
    return _validate_field(field, value, FIELD_SCHEMA)


def set_project_field(db: ProjectsDatabase, slug: str, field: str, value: Any) -> ChangeResult:
    """Set a project field, handling dot-notation for nested dicts.

    The database is mutated in memory but NOT saved -- caller must call db.save().
    """
    return _set_field(DictDatabaseAdapter(db), slug, field, value)


def unset_project_field(db: ProjectsDatabase, slug: str, field: str) -> ChangeResult:
    """Remove a project field override.

    Raises:
        KeyError: If the project doesn't exist in the database.
    """
    try:
        return _unset_field(DictDatabaseAdapter(db), slug, field)
    except KeyError as e:
        raise KeyError(f"Project not found: {slug!r}") from e


def modify_list_field(
    db: ProjectsDatabase,
    slug: str,
    field: str,
    *,
    add: list[str] | None = None,
    remove: list[str] | None = None,
    replace: list[str] | None = None,
) -> ChangeResult:
    """Add, remove, or replace items in a list field.

    Raises:
        ValueError: If field is not a list type.
    """
    return _modify_list(
        DictDatabaseAdapter(db),
        slug,
        field,
        add=add,
        remove=remove,
        replace=replace,
        schema=FIELD_SCHEMA,
    )
