"""Field schema, coercion, validation, and change tracking for package overrides.

Package-specific PACKAGES_SCHEMA plus thin wrappers that bind the schema to the
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
    from mf.packages.database import PackageDatabase


# -- Field schema for all user-settable package fields --

PACKAGES_SCHEMA: dict[str, FieldDef] = {
    # Core
    "name": FieldDef(FieldType.STRING, "Package name on registry"),
    "registry": FieldDef(
        FieldType.STRING,
        "Package registry",
        choices=["pypi", "cran"],
    ),
    "project": FieldDef(FieldType.STRING, "Linked mf project slug"),
    "description": FieldDef(FieldType.STRING, "Package description"),
    "latest_version": FieldDef(FieldType.STRING, "Latest version string"),
    "install_command": FieldDef(FieldType.STRING, "Install command for users"),
    "registry_url": FieldDef(FieldType.STRING, "URL to package on registry"),
    "license": FieldDef(FieldType.STRING, "License identifier"),
    # Numeric
    "downloads": FieldDef(FieldType.INT, "Download count"),
    "stars": FieldDef(FieldType.INT, "Quality rating (0-5)", min_val=0, max_val=5),
    # Classification
    "tags": FieldDef(FieldType.STRING_LIST, "Package tags"),
    # Visibility
    "featured": FieldDef(FieldType.BOOL, "Show in featured section"),
    # Hugo settings
    "aliases": FieldDef(FieldType.STRING_LIST, "Hugo URL aliases"),
}


# ---------------------------------------------------------------------------
# Thin wrappers that bind the package schema
# ---------------------------------------------------------------------------


def validate_package_field(field: str, value: Any) -> list[str]:
    """Validate a field value against the package schema."""
    return _validate_field(field, value, PACKAGES_SCHEMA)


def set_package_field(db: PackageDatabase, slug: str, field: str, value: Any) -> ChangeResult:
    """Set a package field, handling dot-notation for nested dicts.

    The database is mutated in memory but NOT saved -- caller must call db.save().
    """
    return _set_field(EntryDatabaseAdapter(db), slug, field, value)


def unset_package_field(db: PackageDatabase, slug: str, field: str) -> ChangeResult:
    """Remove a package field override.

    Raises:
        KeyError: If the package doesn't exist in the database.
    """
    try:
        return _unset_field(EntryDatabaseAdapter(db), slug, field)
    except KeyError as e:
        raise KeyError(f"Package not found: {slug!r}") from e


def modify_package_list_field(
    db: PackageDatabase,
    slug: str,
    field: str,
    *,
    add: list[str] | None = None,
    remove: list[str] | None = None,
    replace: list[str] | None = None,
) -> ChangeResult:
    """Add, remove, or replace items in a package list field.

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
        schema=PACKAGES_SCHEMA,
    )
