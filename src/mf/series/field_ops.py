"""Field schema, coercion, validation, and change tracking for series overrides.

Series-specific SERIES_SCHEMA plus thin wrappers that bind the schema to the
generic operations in ``mf.core.field_ops``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from mf.core.field_ops import (
    ChangeResult,
    EntryDatabaseAdapter,
    FieldDef,
    FieldType,
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
    from mf.core.database import SeriesDatabase


# -- Field schema for all user-settable series fields --

SERIES_SCHEMA: dict[str, FieldDef] = {
    # Core
    "title": FieldDef(FieldType.STRING, "Series title"),
    "description": FieldDef(FieldType.STRING, "Short description for cards"),
    "created_date": FieldDef(FieldType.STRING, "Creation date (YYYY-MM-DD)"),
    # Status
    "status": FieldDef(
        FieldType.STRING,
        "Series status",
        choices=["active", "completed", "archived"],
    ),
    "featured": FieldDef(FieldType.BOOL, "Show in featured section"),
    # Classification
    "tags": FieldDef(FieldType.STRING_LIST, "Series tags"),
    "color": FieldDef(FieldType.STRING, "Hex color for UI (e.g. #667eea)"),
    "icon": FieldDef(FieldType.STRING, "Icon name for UI"),
    # Related
    "related_projects": FieldDef(FieldType.STRING_LIST, "Related project slugs"),
    # Associations
    "associations": FieldDef(FieldType.DICT, "Content associations (papers, media, links)"),
    # Source sync
    "source_dir": FieldDef(FieldType.STRING, "External source directory path"),
    "posts_subdir": FieldDef(FieldType.STRING, "Subdirectory in source containing posts"),
    "landing_page": FieldDef(FieldType.STRING, "Relative path to landing page in source"),
}


# ---------------------------------------------------------------------------
# Thin wrappers that bind the series schema
# ---------------------------------------------------------------------------


def validate_series_field(field: str, value: Any) -> list[str]:
    """Validate a field value against the series schema."""
    return _validate_field(field, value, SERIES_SCHEMA)


def set_series_field(db: SeriesDatabase, slug: str, field: str, value: Any) -> ChangeResult:
    """Set a series field, handling dot-notation for nested dicts.

    The database is mutated in memory but NOT saved -- caller must call db.save().
    """
    return _set_field(EntryDatabaseAdapter(db), slug, field, value)


def unset_series_field(db: SeriesDatabase, slug: str, field: str) -> ChangeResult:
    """Remove a series field override.

    Raises:
        KeyError: If the series doesn't exist in the database.
    """
    try:
        return _unset_field(EntryDatabaseAdapter(db), slug, field)
    except KeyError as e:
        raise KeyError(f"Series not found: {slug!r}") from e


def modify_series_list_field(
    db: SeriesDatabase,
    slug: str,
    field: str,
    *,
    add: list[str] | None = None,
    remove: list[str] | None = None,
    replace: list[str] | None = None,
) -> ChangeResult:
    """Add, remove, or replace items in a series list field.

    Raises:
        ValueError: If field is not a list type.
    """
    return _modify_list(
        EntryDatabaseAdapter(db),
        slug,
        field,
        add=add,
        remove=remove,
        replace=replace,
        schema=SERIES_SCHEMA,
    )
