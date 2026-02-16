"""Shared field schema, coercion, validation, and change tracking for database overrides.

This module provides domain-agnostic infrastructure that projects, papers, and series
each extend with their own schemas. The key abstraction is FieldDatabase -- a Protocol
that normalizes access to the three different database return types (dict vs Entry).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from rich.console import Console


class FieldType(Enum):
    """Supported field types for database overrides."""

    STRING = "string"
    INT = "int"
    BOOL = "bool"
    STRING_LIST = "string_list"
    DICT = "dict"


@dataclass
class FieldDef:
    """Schema definition for a single field."""

    field_type: FieldType
    description: str
    choices: list[str] | None = None
    min_val: int | None = None
    max_val: int | None = None


@dataclass
class ChangeResult:
    """Result of a field change operation."""

    slug: str
    field: str
    old_value: Any
    new_value: Any
    action: str  # "set", "unset", "add", "remove", "replace"


# ---------------------------------------------------------------------------
# Database adapter protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class FieldDatabase(Protocol):
    """Minimal interface for field operations on any database type.

    Adapters wrap the concrete database classes so that generic set/unset/modify
    functions don't need to know whether get() returns a dict or an Entry.
    """

    def get_data(self, slug: str) -> dict[str, Any] | None:
        """Return the raw dict for *slug*, or None."""
        ...

    def update_data(self, slug: str, **kwargs: Any) -> None:
        """Merge *kwargs* into the entry for *slug* (creating it if absent)."""
        ...

    def set_data(self, slug: str, data: dict[str, Any]) -> None:
        """Replace the entire entry for *slug*."""
        ...

    def __contains__(self, slug: str) -> bool:
        ...


class DictDatabaseAdapter:
    """Adapter for ProjectsDatabase (get() returns dict | None)."""

    def __init__(self, db: Any) -> None:
        self._db = db

    def get_data(self, slug: str) -> dict[str, Any] | None:
        result: dict[str, Any] | None = self._db.get(slug)
        return result

    def update_data(self, slug: str, **kwargs: Any) -> None:
        self._db.update(slug, **kwargs)

    def set_data(self, slug: str, data: dict[str, Any]) -> None:
        self._db.set(slug, data)

    def __contains__(self, slug: str) -> bool:
        return slug in self._db


class EntryDatabaseAdapter:
    """Adapter for PaperDatabase / SeriesDatabase (get() returns Entry | None).

    The Entry objects expose a ``.data`` dict, so we read through that.
    Writes still go through the database's own update/set methods.
    """

    def __init__(self, db: Any) -> None:
        self._db = db

    def get_data(self, slug: str) -> dict[str, Any] | None:
        entry = self._db.get(slug)
        if entry is None:
            return None
        data: dict[str, Any] = entry.data
        return data

    def update_data(self, slug: str, **kwargs: Any) -> None:
        self._db.update(slug, **kwargs)

    def set_data(self, slug: str, data: dict[str, Any]) -> None:
        self._db.set(slug, data)

    def __contains__(self, slug: str) -> bool:
        return slug in self._db


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def parse_field_path(field: str) -> tuple[str, str | None]:
    """Split a dot-notation field path into (top_level, sub_key).

    Examples:
        "stars" -> ("stars", None)
        "packages.pypi" -> ("packages", "pypi")
        "external_docs.readthedocs" -> ("external_docs", "readthedocs")
    """
    parts = field.split(".", 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return parts[0], None


# ---------------------------------------------------------------------------
# Coercion
# ---------------------------------------------------------------------------


def coerce_value(value_str: str, field_def: FieldDef) -> Any:
    """Coerce a string value to the field's expected type.

    Args:
        value_str: Raw string from CLI input.
        field_def: Schema definition for the target field.

    Returns:
        Coerced value.

    Raises:
        ValueError: If the value cannot be coerced.
    """
    ft = field_def.field_type

    if ft == FieldType.STRING:
        return value_str

    if ft == FieldType.INT:
        try:
            return int(value_str)
        except ValueError as e:
            raise ValueError(f"Expected integer, got: {value_str!r}") from e

    if ft == FieldType.BOOL:
        lower = value_str.lower()
        if lower in ("true", "yes", "1", "on"):
            return True
        if lower in ("false", "no", "0", "off"):
            return False
        raise ValueError(f"Expected boolean (true/false/yes/no/1/0/on/off), got: {value_str!r}")

    if ft == FieldType.STRING_LIST:
        # Try JSON array first, then comma-separated
        stripped = value_str.strip()
        if stripped.startswith("["):
            try:
                parsed = json.loads(stripped)
                if isinstance(parsed, list):
                    return [str(item) for item in parsed]
            except json.JSONDecodeError:
                pass
        return [item.strip() for item in value_str.split(",") if item.strip()]

    if ft == FieldType.DICT:
        # Only accept JSON objects
        stripped = value_str.strip()
        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
        raise ValueError(f"Expected JSON object, got: {value_str!r}")

    raise ValueError(f"Unknown field type: {ft}")


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_field(field: str, value: Any, schema: dict[str, FieldDef]) -> list[str]:
    """Validate a field value against a schema.

    Args:
        field: Field name (may be dot-notation).
        value: Already-coerced value.
        schema: The field schema dict (e.g. FIELD_SCHEMA, PAPERS_SCHEMA).

    Returns:
        List of error messages (empty if valid).
    """
    top, sub = parse_field_path(field)
    field_def = schema.get(top)
    if field_def is None:
        return [f"Unknown field: {top!r}"]

    errors: list[str] = []

    # For dot-notation on dict fields, the value is a string sub-key value
    if sub is not None:
        if field_def.field_type != FieldType.DICT:
            errors.append(f"Dot notation only works on dict fields, but {top!r} is {field_def.field_type.value}.")
        return errors

    # Type-specific validation
    if field_def.field_type == FieldType.INT and isinstance(value, int):
        if field_def.min_val is not None and value < field_def.min_val:
            errors.append(f"{top}: value {value} is below minimum {field_def.min_val}.")
        if field_def.max_val is not None and value > field_def.max_val:
            errors.append(f"{top}: value {value} is above maximum {field_def.max_val}.")

    if field_def.choices is not None and isinstance(value, str) and value not in field_def.choices:
            errors.append(f"{top}: {value!r} is not a valid choice. Options: {', '.join(field_def.choices)}.")

    return errors


# ---------------------------------------------------------------------------
# Generic field operations (work on any FieldDatabase)
# ---------------------------------------------------------------------------


def set_field(
    db: FieldDatabase,
    slug: str,
    field: str,
    value: Any,
    schema: dict[str, FieldDef] | None = None,
) -> ChangeResult:
    """Set a field, handling dot-notation for nested dicts.

    The database is mutated in memory but NOT saved -- caller must save.

    Args:
        db: Adapted database.
        slug: Entry slug.
        field: Field name, optionally with dot-notation (e.g. "packages.pypi").
        value: Already-coerced and validated value.
        schema: Optional field schema for validation before update.

    Returns:
        ChangeResult describing what changed.

    Raises:
        ValueError: If schema is provided and validation fails.
    """
    if schema is not None:
        errors = validate_field(field, value, schema)
        if errors:
            raise ValueError("; ".join(errors))
    top, sub = parse_field_path(field)
    current = db.get_data(slug) or {}

    if sub is not None:
        # Nested dict: packages.pypi = "my-pkg"
        old_dict: dict[str, Any] = current.get(top, {})
        old_value = old_dict.get(sub)
        new_dict = dict(old_dict)
        new_dict[sub] = value
        db.update_data(slug, **{top: new_dict})
        return ChangeResult(slug=slug, field=field, old_value=old_value, new_value=value, action="set")

    old_value = current.get(top)
    db.update_data(slug, **{top: value})
    return ChangeResult(slug=slug, field=field, old_value=old_value, new_value=value, action="set")


def unset_field(db: FieldDatabase, slug: str, field: str) -> ChangeResult:
    """Remove a field override.

    Args:
        db: Adapted database.
        slug: Entry slug.
        field: Field name, optionally with dot-notation.

    Returns:
        ChangeResult describing what was removed.

    Raises:
        KeyError: If the entry doesn't exist in the database.
    """
    top, sub = parse_field_path(field)
    current = db.get_data(slug)
    if current is None:
        raise KeyError(f"Entry not found: {slug!r}")

    if sub is not None:
        old_dict: dict[str, Any] = current.get(top, {})
        old_value = old_dict.get(sub)
        if sub in old_dict:
            new_dict = dict(old_dict)
            del new_dict[sub]
            if new_dict:
                db.update_data(slug, **{top: new_dict})
            else:
                # Remove the entire dict if empty — work on a copy to avoid mutating source
                updated = dict(current)
                del updated[top]
                db.set_data(slug, updated)
        return ChangeResult(slug=slug, field=field, old_value=old_value, new_value=None, action="unset")

    old_value = current.get(top)
    if top in current:
        # Work on a copy to avoid mutating the dict returned by get_data()
        updated = dict(current)
        del updated[top]
        db.set_data(slug, updated)
    return ChangeResult(slug=slug, field=field, old_value=old_value, new_value=None, action="unset")


def modify_list_field(
    db: FieldDatabase,
    slug: str,
    field: str,
    *,
    add: list[str] | None = None,
    remove: list[str] | None = None,
    replace: list[str] | None = None,
    schema: dict[str, FieldDef],
) -> ChangeResult:
    """Add, remove, or replace items in a list field.

    Args:
        db: Adapted database.
        slug: Entry slug.
        field: Field name (must be a STRING_LIST field).
        add: Items to add (appended, deduped).
        remove: Items to remove.
        replace: Complete replacement list (ignores add/remove).
        schema: The field schema dict.

    Returns:
        ChangeResult with old and new list values.

    Raises:
        ValueError: If field is not a list type.
    """
    field_def = schema.get(field)
    if field_def is None:
        raise ValueError(f"Unknown field: {field!r}")
    if field_def.field_type != FieldType.STRING_LIST:
        raise ValueError(f"Field {field!r} is {field_def.field_type.value}, not a list.")

    current = db.get_data(slug) or {}
    old_value = list(current.get(field, []))

    if replace is not None:
        new_value = replace
    else:
        new_value = list(old_value)
        if add:
            seen = set(new_value)
            for item in add:
                if item not in seen:
                    new_value.append(item)
                    seen.add(item)
        if remove:
            remove_set = set(remove)
            new_value = [item for item in new_value if item not in remove_set]

    db.update_data(slug, **{field: new_value})

    action = "replace" if replace is not None else "add" if add and not remove else "remove" if remove and not add else "modify"
    return ChangeResult(slug=slug, field=field, old_value=old_value, new_value=new_value, action=action)


# ---------------------------------------------------------------------------
# CLI helpers
# ---------------------------------------------------------------------------


def print_change(result: ChangeResult, console: Console) -> None:
    """Print a ChangeResult as a formatted diff."""
    console.print(f"[cyan]{result.slug}[/cyan]: {result.field}")
    if result.old_value is not None:
        console.print(f"  old: {result.old_value}")
    if result.new_value is not None:
        console.print(f"  new: {result.new_value}")
    elif result.action == "unset":
        console.print("  [dim](removed)[/dim]")
