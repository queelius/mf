"""Field schema, coercion, validation, and change tracking for paper overrides.

Paper-specific PAPERS_SCHEMA plus thin wrappers that bind the schema to the
generic operations in ``mf.core.field_ops``.

Zenodo fields (zenodo_doi, zenodo_url, etc.) are excluded -- they are managed
exclusively by ``mf papers zenodo`` commands.
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
    from mf.core.database import PaperDatabase


# -- Field schema for all user-settable paper fields --

PAPERS_SCHEMA: dict[str, FieldDef] = {
    # Core metadata
    "title": FieldDef(FieldType.STRING, "Paper title"),
    "date": FieldDef(FieldType.STRING, "Publication date (YYYY-MM-DD)"),
    "abstract": FieldDef(FieldType.STRING, "Paper abstract"),
    "year": FieldDef(FieldType.INT, "Publication year", min_val=1970, max_val=2100),
    # Authors
    "authors": FieldDef(FieldType.STRING_LIST, "Paper authors"),
    "advisors": FieldDef(FieldType.STRING_LIST, "Thesis advisors"),
    # Classification
    "tags": FieldDef(FieldType.STRING_LIST, "Paper tags"),
    "category": FieldDef(FieldType.STRING, "Paper category"),
    "stars": FieldDef(FieldType.INT, "Quality/featured rating (0-5)", min_val=0, max_val=5),
    "featured": FieldDef(FieldType.BOOL, "Show in featured section"),
    # Publication info
    "status": FieldDef(
        FieldType.STRING,
        "Publication status",
        choices=["published", "preprint", "draft", "submitted"],
    ),
    "venue": FieldDef(FieldType.STRING, "Conference or journal name"),
    "publication_type": FieldDef(
        FieldType.STRING,
        "Publication type",
        choices=["conference", "journal", "thesis", "technical-report"],
    ),
    "doi": FieldDef(FieldType.STRING, "DOI identifier"),
    "arxiv_id": FieldDef(FieldType.STRING, "arXiv identifier"),
    # Links
    "github_url": FieldDef(FieldType.STRING, "GitHub repository URL"),
    "project_url": FieldDef(FieldType.STRING, "Related project URL"),
    "related_posts": FieldDef(FieldType.STRING_LIST, "Related blog post paths"),
    # File paths
    "pdf_path": FieldDef(FieldType.STRING, "Path to PDF file (in /static/latex/)"),
    "html_path": FieldDef(FieldType.STRING, "Path to HTML version"),
    "cite_path": FieldDef(FieldType.STRING, "Path to BibTeX citation file"),
    # Source
    "source_path": FieldDef(FieldType.STRING, "Path to LaTeX source file"),
    "source_format": FieldDef(
        FieldType.STRING,
        "Source format",
        choices=["tex", "docx", "pregenerated"],
    ),
    # Hugo settings
    "aliases": FieldDef(FieldType.STRING_LIST, "Hugo URL aliases for redirects"),
}


# ---------------------------------------------------------------------------
# Thin wrappers that bind the paper schema
# ---------------------------------------------------------------------------


def validate_paper_field(field: str, value: Any) -> list[str]:
    """Validate a field value against the paper schema."""
    return _validate_field(field, value, PAPERS_SCHEMA)


def set_paper_field(db: PaperDatabase, slug: str, field: str, value: Any) -> ChangeResult:
    """Set a paper field, handling dot-notation for nested dicts.

    The database is mutated in memory but NOT saved -- caller must call db.save().
    """
    return _set_field(EntryDatabaseAdapter(db), slug, field, value)


def unset_paper_field(db: PaperDatabase, slug: str, field: str) -> ChangeResult:
    """Remove a paper field override.

    Raises:
        KeyError: If the paper doesn't exist in the database.
    """
    try:
        return _unset_field(EntryDatabaseAdapter(db), slug, field)
    except KeyError as e:
        raise KeyError(f"Paper not found: {slug!r}") from e


def modify_paper_list_field(
    db: PaperDatabase,
    slug: str,
    field: str,
    *,
    add: list[str] | None = None,
    remove: list[str] | None = None,
    replace: list[str] | None = None,
) -> ChangeResult:
    """Add, remove, or replace items in a paper list field.

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
        schema=PAPERS_SCHEMA,
    )
