"""CITATION.cff parsing for papers.

This module provides read-only support for parsing CITATION.cff files
from GitHub repositories and converting the metadata to paper_db format.

CITATION.cff is a standardized format for software/research citation:
https://citation-file-format.github.io/

Example CITATION.cff:
```yaml
cff-version: 1.2.0
title: "My Research Software"
authors:
  - family-names: "Doe"
    given-names: "John"
    orcid: "https://orcid.org/0000-0001-2345-6789"
doi: "10.5281/zenodo.1234567"
date-released: "2024-06-15"
keywords:
  - machine-learning
  - python
```
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import yaml


@dataclass
class CitationMetadata:
    """Parsed CITATION.cff data.

    This dataclass mirrors the CFF schema with commonly used fields.
    See https://github.com/citation-file-format/citation-file-format
    """

    title: str | None
    authors: list[dict[str, Any]] = field(default_factory=list)
    date_released: str | None = None
    doi: str | None = None
    version: str | None = None
    keywords: list[str] = field(default_factory=list)
    repository_code: str | None = None
    license: str | None = None
    cff_type: str | None = None  # software, dataset, article
    abstract: str | None = None


def parse_cff(content: str) -> CitationMetadata:
    """Parse CITATION.cff YAML content.

    Args:
        content: Raw YAML content from CITATION.cff file

    Returns:
        CitationMetadata with parsed fields
    """
    if not content or not content.strip():
        return CitationMetadata(
            title=None,
            authors=[],
            date_released=None,
            doi=None,
            version=None,
            keywords=[],
            repository_code=None,
            license=None,
            cff_type=None,
            abstract=None,
        )

    data = yaml.safe_load(content)
    if not data:
        return CitationMetadata(
            title=None,
            authors=[],
            date_released=None,
            doi=None,
            version=None,
            keywords=[],
            repository_code=None,
            license=None,
            cff_type=None,
            abstract=None,
        )

    return CitationMetadata(
        title=data.get("title"),
        authors=data.get("authors", []),
        date_released=data.get("date-released"),
        doi=data.get("doi"),
        version=data.get("version"),
        keywords=data.get("keywords", []),
        repository_code=data.get("repository-code"),
        license=data.get("license"),
        cff_type=data.get("type"),
        abstract=data.get("abstract"),
    )


def cff_to_paper_fields(cff: CitationMetadata) -> dict[str, Any]:
    """Convert CFF metadata to paper_db fields (for merging).

    Only includes non-empty fields in the result. This allows
    selective merging where CFF data fills gaps in existing
    paper_db entries.

    Args:
        cff: Parsed CitationMetadata

    Returns:
        Dict of paper_db fields (only non-empty values)
    """
    fields: dict[str, Any] = {}

    if cff.title:
        fields["title"] = cff.title
    if cff.abstract:
        fields["abstract"] = cff.abstract
    if cff.doi:
        fields["doi"] = cff.doi
    if cff.date_released:
        fields["date"] = cff.date_released
    if cff.keywords:
        fields["tags"] = cff.keywords
    if cff.authors:
        fields["authors"] = _convert_authors(cff.authors)

    return fields


def _convert_authors(cff_authors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert CFF author format to paper_db format.

    CFF format uses:
    - given-names: "John"
    - family-names: "Doe"
    - orcid: "https://orcid.org/..."
    - email: "john@example.com"
    - affiliation: "University"

    Paper_db format uses:
    - name: "John Doe"
    - orcid: "https://orcid.org/..."
    - email: "john@example.com"
    - affiliation: "University"

    Args:
        cff_authors: List of CFF author dicts

    Returns:
        List of paper_db author dicts
    """
    result = []
    for author in cff_authors:
        entry: dict[str, Any] = {}

        # Combine given-names and family-names into name
        given = author.get("given-names", "")
        family = author.get("family-names", "")
        full_name = f"{given} {family}".strip()
        if full_name:
            entry["name"] = full_name

        # Copy optional fields if present
        if "orcid" in author:
            entry["orcid"] = author["orcid"]
        if "email" in author:
            entry["email"] = author["email"]
        if "affiliation" in author:
            entry["affiliation"] = author["affiliation"]

        if entry:  # Only add if we have at least some data
            result.append(entry)

    return result
