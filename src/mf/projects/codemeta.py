"""
CodeMeta JSON-LD parsing for projects.

This module provides read-only support for parsing codemeta.json files
from GitHub repositories and converting the metadata to projects_db format.

CodeMeta is a structured metadata standard for software:
https://codemeta.github.io/

Example codemeta.json:
```json
{
  "@context": "https://doi.org/10.5063/schema/codemeta-2.0",
  "@type": "SoftwareSourceCode",
  "name": "My Software",
  "description": "A tool for doing things",
  "author": [
    {
      "@type": "Person",
      "givenName": "Jane",
      "familyName": "Doe",
      "email": "jane@example.com"
    }
  ],
  "programmingLanguage": ["Python", "C++"],
  "license": "https://spdx.org/licenses/MIT",
  "keywords": ["data-science", "machine-learning"],
  "codeRepository": "https://github.com/user/repo",
  "developmentStatus": "active"
}
```
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CodeMetadata:
    """Parsed codemeta.json data.

    This dataclass mirrors the CodeMeta schema with commonly used fields.
    See https://codemeta.github.io/terms/
    """

    name: str | None = None
    description: str | None = None
    authors: list[dict[str, Any]] = field(default_factory=list)
    programming_languages: list[str] = field(default_factory=list)
    license: str | None = None
    license_id: str | None = None  # SPDX identifier
    keywords: list[str] = field(default_factory=list)
    version: str | None = None
    date_created: str | None = None
    date_modified: str | None = None
    code_repository: str | None = None
    development_status: str | None = None
    software_requirements: list[str] = field(default_factory=list)
    runtime_platform: list[str] = field(default_factory=list)
    operating_system: list[str] = field(default_factory=list)
    identifier: str | None = None  # DOI or other identifier
    citation: str | None = None
    readme: str | None = None
    issue_tracker: str | None = None
    funding: list[dict[str, Any]] = field(default_factory=list)


def parse_codemeta(content: str) -> CodeMetadata:
    """Parse codemeta.json content.

    Args:
        content: Raw JSON content from codemeta.json file

    Returns:
        CodeMetadata with parsed fields
    """
    if not content or not content.strip():
        return CodeMetadata()

    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return CodeMetadata()

    if not data or not isinstance(data, dict):
        return CodeMetadata()

    return CodeMetadata(
        name=data.get("name"),
        description=data.get("description"),
        authors=_parse_authors(data.get("author", [])),
        programming_languages=_parse_list_or_string(data.get("programmingLanguage", [])),
        license=_parse_license(data.get("license")),
        license_id=_extract_spdx_id(data.get("license")),
        keywords=_parse_list_or_string(data.get("keywords", [])),
        version=data.get("version"),
        date_created=data.get("dateCreated"),
        date_modified=data.get("dateModified"),
        code_repository=data.get("codeRepository"),
        development_status=_parse_dev_status(data.get("developmentStatus")),
        software_requirements=_parse_list_or_string(data.get("softwareRequirements", [])),
        runtime_platform=_parse_list_or_string(data.get("runtimePlatform", [])),
        operating_system=_parse_list_or_string(data.get("operatingSystem", [])),
        identifier=data.get("identifier"),
        citation=data.get("citation"),
        readme=data.get("readme"),
        issue_tracker=data.get("issueTracker"),
        funding=_parse_funding(data.get("funding", [])),
    )


def _parse_authors(author_data: Any) -> list[dict[str, Any]]:
    """Parse author field which can be a single object or list."""
    if not author_data:
        return []

    # Normalize to list
    if isinstance(author_data, dict):
        author_data = [author_data]

    if not isinstance(author_data, list):
        return []

    result = []
    for author in author_data:
        if isinstance(author, dict):
            entry: dict[str, Any] = {}
            # Handle Person type
            if author.get("@type") == "Person":
                given = author.get("givenName", "")
                family = author.get("familyName", "")
                name = author.get("name") or f"{given} {family}".strip()
                if name:
                    entry["name"] = name
                if author.get("email"):
                    entry["email"] = author["email"]
                if author.get("@id"):  # ORCID or other ID
                    entry["id"] = author["@id"]
                if author.get("affiliation"):
                    aff = author["affiliation"]
                    if isinstance(aff, dict):
                        entry["affiliation"] = aff.get("name", str(aff))
                    else:
                        entry["affiliation"] = str(aff)
            # Handle Organization type
            elif author.get("@type") == "Organization":
                if author.get("name"):
                    entry["name"] = author["name"]
                    entry["type"] = "organization"
            # Handle simple string in dict
            elif author.get("name"):
                entry["name"] = author["name"]

            if entry:
                result.append(entry)
        elif isinstance(author, str):
            result.append({"name": author})

    return result


def _parse_list_or_string(value: Any) -> list[str]:
    """Parse a field that can be a string or list of strings."""
    if not value:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        result = []
        for item in value:
            if isinstance(item, str):
                result.append(item)
            elif isinstance(item, dict) and item.get("name"):
                result.append(item["name"])
        return result
    return []


def _parse_license(license_data: Any) -> str | None:
    """Parse license field which can be a URL, string, or object."""
    if not license_data:
        return None
    if isinstance(license_data, str):
        return license_data
    if isinstance(license_data, dict):
        return license_data.get("name") or license_data.get("url") or license_data.get("@id")
    return None


def _extract_spdx_id(license_data: Any) -> str | None:
    """Extract SPDX license identifier if present."""
    if not license_data:
        return None

    license_str = None
    if isinstance(license_data, str):
        license_str = license_data
    elif isinstance(license_data, dict):
        license_str = license_data.get("@id") or license_data.get("url")

    if not license_str:
        return None

    # Extract from SPDX URL like https://spdx.org/licenses/MIT
    if "spdx.org/licenses/" in license_str:
        return license_str.split("spdx.org/licenses/")[-1].rstrip("/")

    # Common license names
    license_upper = license_str.upper()
    if "MIT" in license_upper:
        return "MIT"
    if "APACHE" in license_upper and "2" in license_str:
        return "Apache-2.0"
    # Handle both "GPL" and "GNU General Public License"
    if "GPL" in license_upper or "GENERAL PUBLIC LICENSE" in license_upper:
        if "3" in license_str:
            return "GPL-3.0"
        if "2" in license_str:
            return "GPL-2.0"
    if "BSD" in license_upper:
        if "3" in license_str:
            return "BSD-3-Clause"
        if "2" in license_str:
            return "BSD-2-Clause"

    return None


def _parse_dev_status(status: Any) -> str | None:
    """Parse developmentStatus field."""
    if not status:
        return None
    if isinstance(status, str):
        # Handle repostatus.org URLs
        if "repostatus.org" in status:
            # Extract status from URL like https://www.repostatus.org/#active
            parts = status.split("#")
            if len(parts) > 1:
                return parts[-1]
        return status
    return None


def _parse_funding(funding_data: Any) -> list[dict[str, Any]]:
    """Parse funding field."""
    if not funding_data:
        return []
    if isinstance(funding_data, dict):
        funding_data = [funding_data]
    if not isinstance(funding_data, list):
        return []

    result = []
    for fund in funding_data:
        if isinstance(fund, dict):
            entry = {}
            if fund.get("name"):
                entry["name"] = fund["name"]
            if fund.get("@type"):
                entry["type"] = fund["@type"]
            if fund.get("funder"):
                funder = fund["funder"]
                if isinstance(funder, dict):
                    entry["funder"] = funder.get("name", str(funder))
                else:
                    entry["funder"] = str(funder)
            if entry:
                result.append(entry)
    return result


def codemeta_to_project_fields(cm: CodeMetadata) -> dict[str, Any]:
    """Convert CodeMeta to projects_db fields (for merging).

    Only includes non-empty fields in the result. This allows
    selective merging where CodeMeta data fills gaps in existing
    projects_db entries.

    Args:
        cm: Parsed CodeMetadata

    Returns:
        Dict of projects_db fields (only non-empty values)
    """
    fields: dict[str, Any] = {}

    if cm.name:
        fields["name"] = cm.name
    if cm.description:
        fields["description"] = cm.description
    if cm.programming_languages:
        fields["languages"] = cm.programming_languages
    if cm.keywords:
        fields["tags"] = cm.keywords
    if cm.license_id:
        fields["license"] = cm.license_id
    if cm.version:
        fields["version"] = cm.version
    if cm.development_status:
        fields["status"] = _map_dev_status(cm.development_status)
    if cm.date_created:
        # Extract year from date
        try:
            year = int(cm.date_created[:4])
            fields["year_started"] = year
        except (ValueError, TypeError):
            pass
    if cm.code_repository and "github.com" in cm.code_repository:
        fields["github"] = cm.code_repository
    if cm.identifier and ("doi.org" in str(cm.identifier) or cm.identifier.startswith("10.")):
            fields["doi"] = cm.identifier
    if cm.authors:
        fields["authors"] = cm.authors

    return fields


def _map_dev_status(status: str) -> str:
    """Map CodeMeta/repostatus.org status to projects_db status values.

    projects_db uses: active, inactive, archived, maintenance
    repostatus.org uses: concept, wip, suspended, abandoned, active, inactive, unsupported, moved
    """
    status_lower = status.lower()

    status_map = {
        "active": "active",
        "wip": "active",
        "concept": "active",
        "inactive": "inactive",
        "suspended": "inactive",
        "abandoned": "archived",
        "unsupported": "archived",
        "moved": "archived",
        "maintenance": "maintenance",
        "stable": "maintenance",
    }

    return status_map.get(status_lower, status_lower)
