"""Tests for mf.projects.codemeta module (codemeta.json parsing)."""

import pytest

from mf.projects.codemeta import (
    CodeMetadata,
    parse_codemeta,
    codemeta_to_project_fields,
)


class TestParseCodemeta:
    """Tests for parse_codemeta function."""

    def test_parse_minimal_codemeta(self):
        """Test parsing a minimal codemeta.json with just name."""
        content = """
{
  "@context": "https://doi.org/10.5063/schema/codemeta-2.0",
  "@type": "SoftwareSourceCode",
  "name": "My Software"
}
"""
        result = parse_codemeta(content)

        assert isinstance(result, CodeMetadata)
        assert result.name == "My Software"
        assert result.authors == []
        assert result.keywords == []

    def test_parse_full_codemeta(self):
        """Test parsing a codemeta.json with all common fields."""
        content = """
{
  "@context": "https://doi.org/10.5063/schema/codemeta-2.0",
  "@type": "SoftwareSourceCode",
  "name": "Complete Software",
  "description": "A comprehensive tool for research.",
  "author": [
    {
      "@type": "Person",
      "givenName": "Jane",
      "familyName": "Smith",
      "email": "jane@example.com",
      "@id": "https://orcid.org/0000-0001-2345-6789"
    },
    {
      "@type": "Person",
      "givenName": "John",
      "familyName": "Doe"
    }
  ],
  "programmingLanguage": ["Python", "C++"],
  "license": "https://spdx.org/licenses/MIT",
  "keywords": ["machine-learning", "data-science"],
  "version": "2.0.0",
  "dateCreated": "2024-06-15",
  "dateModified": "2024-12-01",
  "codeRepository": "https://github.com/user/repo",
  "developmentStatus": "active"
}
"""
        result = parse_codemeta(content)

        assert result.name == "Complete Software"
        assert result.description == "A comprehensive tool for research."
        assert result.version == "2.0.0"
        assert result.date_created == "2024-06-15"
        assert result.date_modified == "2024-12-01"
        assert result.code_repository == "https://github.com/user/repo"
        assert result.development_status == "active"
        assert result.license == "https://spdx.org/licenses/MIT"
        assert result.license_id == "MIT"
        assert len(result.authors) == 2
        assert result.authors[0]["name"] == "Jane Smith"
        assert result.authors[0]["email"] == "jane@example.com"
        assert result.programming_languages == ["Python", "C++"]
        assert result.keywords == ["machine-learning", "data-science"]

    def test_parse_empty_content(self):
        """Test parsing empty content."""
        result = parse_codemeta("")

        assert result.name is None
        assert result.authors == []
        assert result.keywords == []

    def test_parse_whitespace_only(self):
        """Test parsing whitespace-only content."""
        result = parse_codemeta("   \n\t  ")

        assert result.name is None

    def test_parse_invalid_json(self):
        """Test parsing invalid JSON returns empty CodeMetadata."""
        result = parse_codemeta("not valid json {")

        assert result.name is None
        assert result.authors == []

    def test_parse_null_json(self):
        """Test parsing JSON null returns empty CodeMetadata."""
        result = parse_codemeta("null")

        assert result.name is None

    def test_parse_single_author(self):
        """Test parsing when author is a single object, not a list."""
        content = """
{
  "name": "Single Author Software",
  "author": {
    "@type": "Person",
    "givenName": "Solo",
    "familyName": "Developer"
  }
}
"""
        result = parse_codemeta(content)

        assert len(result.authors) == 1
        assert result.authors[0]["name"] == "Solo Developer"

    def test_parse_author_with_name_field(self):
        """Test parsing author that uses 'name' instead of givenName/familyName."""
        content = """
{
  "name": "Test",
  "author": {
    "@type": "Person",
    "name": "Full Name Already Provided"
  }
}
"""
        result = parse_codemeta(content)

        assert result.authors[0]["name"] == "Full Name Already Provided"

    def test_parse_organization_author(self):
        """Test parsing Organization type author."""
        content = """
{
  "name": "Org Project",
  "author": {
    "@type": "Organization",
    "name": "Research Institute"
  }
}
"""
        result = parse_codemeta(content)

        assert result.authors[0]["name"] == "Research Institute"
        assert result.authors[0]["type"] == "organization"

    def test_parse_string_author(self):
        """Test parsing when author is a plain string."""
        content = """
{
  "name": "Simple",
  "author": ["John Doe", "Jane Smith"]
}
"""
        result = parse_codemeta(content)

        assert len(result.authors) == 2
        assert result.authors[0]["name"] == "John Doe"
        assert result.authors[1]["name"] == "Jane Smith"

    def test_parse_author_with_affiliation_object(self):
        """Test parsing author with affiliation as an object."""
        content = """
{
  "name": "Test",
  "author": {
    "@type": "Person",
    "givenName": "Jane",
    "familyName": "Doe",
    "affiliation": {
      "@type": "Organization",
      "name": "MIT"
    }
  }
}
"""
        result = parse_codemeta(content)

        assert result.authors[0]["affiliation"] == "MIT"

    def test_parse_author_with_affiliation_string(self):
        """Test parsing author with affiliation as a string."""
        content = """
{
  "name": "Test",
  "author": {
    "@type": "Person",
    "givenName": "Jane",
    "familyName": "Doe",
    "affiliation": "Stanford University"
  }
}
"""
        result = parse_codemeta(content)

        assert result.authors[0]["affiliation"] == "Stanford University"


class TestParseLicense:
    """Tests for license parsing."""

    def test_parse_spdx_url_license(self):
        """Test extracting SPDX ID from URL."""
        content = """
{
  "name": "MIT Project",
  "license": "https://spdx.org/licenses/MIT"
}
"""
        result = parse_codemeta(content)

        assert result.license == "https://spdx.org/licenses/MIT"
        assert result.license_id == "MIT"

    def test_parse_license_object(self):
        """Test parsing license as an object."""
        content = """
{
  "name": "Test",
  "license": {
    "@type": "CreativeWork",
    "name": "Apache License 2.0",
    "@id": "https://spdx.org/licenses/Apache-2.0"
  }
}
"""
        result = parse_codemeta(content)

        assert result.license == "Apache License 2.0"
        assert result.license_id == "Apache-2.0"

    def test_extract_mit_from_text(self):
        """Test extracting MIT from license text."""
        content = '{"name": "Test", "license": "MIT License"}'
        result = parse_codemeta(content)
        assert result.license_id == "MIT"

    def test_extract_apache2_from_text(self):
        """Test extracting Apache-2.0 from license text."""
        content = '{"name": "Test", "license": "Apache License Version 2.0"}'
        result = parse_codemeta(content)
        assert result.license_id == "Apache-2.0"

    def test_extract_gpl3_from_text(self):
        """Test extracting GPL-3.0 from license text."""
        content = '{"name": "Test", "license": "GNU General Public License v3"}'
        result = parse_codemeta(content)
        assert result.license_id == "GPL-3.0"

    def test_extract_bsd3_from_text(self):
        """Test extracting BSD-3-Clause from license text."""
        content = '{"name": "Test", "license": "BSD 3-Clause License"}'
        result = parse_codemeta(content)
        assert result.license_id == "BSD-3-Clause"


class TestParseDevStatus:
    """Tests for development status parsing."""

    def test_parse_simple_status(self):
        """Test parsing simple status string."""
        content = '{"name": "Test", "developmentStatus": "active"}'
        result = parse_codemeta(content)
        assert result.development_status == "active"

    def test_parse_repostatus_url(self):
        """Test extracting status from repostatus.org URL."""
        content = """
{
  "name": "Test",
  "developmentStatus": "https://www.repostatus.org/#active"
}
"""
        result = parse_codemeta(content)
        assert result.development_status == "active"

    def test_parse_repostatus_wip(self):
        """Test extracting wip status from repostatus.org URL."""
        content = """
{
  "name": "Test",
  "developmentStatus": "https://www.repostatus.org/#wip"
}
"""
        result = parse_codemeta(content)
        assert result.development_status == "wip"


class TestParseProgrammingLanguages:
    """Tests for programming language parsing."""

    def test_parse_single_language_string(self):
        """Test parsing when programmingLanguage is a single string."""
        content = '{"name": "Test", "programmingLanguage": "Python"}'
        result = parse_codemeta(content)
        assert result.programming_languages == ["Python"]

    def test_parse_language_list(self):
        """Test parsing list of programming languages."""
        content = '{"name": "Test", "programmingLanguage": ["Python", "R", "C++"]}'
        result = parse_codemeta(content)
        assert result.programming_languages == ["Python", "R", "C++"]

    def test_parse_language_objects(self):
        """Test parsing languages as objects with name field."""
        content = """
{
  "name": "Test",
  "programmingLanguage": [
    {"@type": "ComputerLanguage", "name": "Python"},
    {"@type": "ComputerLanguage", "name": "JavaScript"}
  ]
}
"""
        result = parse_codemeta(content)
        assert result.programming_languages == ["Python", "JavaScript"]


class TestParseFunding:
    """Tests for funding parsing."""

    def test_parse_single_funding(self):
        """Test parsing single funding object."""
        content = """
{
  "name": "Test",
  "funding": {
    "@type": "Grant",
    "name": "Research Grant 123",
    "funder": {
      "@type": "Organization",
      "name": "NSF"
    }
  }
}
"""
        result = parse_codemeta(content)
        assert len(result.funding) == 1
        assert result.funding[0]["name"] == "Research Grant 123"
        assert result.funding[0]["funder"] == "NSF"

    def test_parse_funding_list(self):
        """Test parsing list of funding sources."""
        content = """
{
  "name": "Test",
  "funding": [
    {"name": "Grant A", "funder": "NSF"},
    {"name": "Grant B", "funder": "NIH"}
  ]
}
"""
        result = parse_codemeta(content)
        assert len(result.funding) == 2


class TestCodemetaToProjectFields:
    """Tests for codemeta_to_project_fields conversion."""

    def test_convert_basic_fields(self):
        """Test converting basic CodeMeta fields to projects_db format."""
        cm = CodeMetadata(
            name="My Project",
            description="Project description",
            programming_languages=["Python", "C++"],
            keywords=["ai", "ml"],
            license_id="MIT",
            version="1.0.0",
            development_status="active",
            date_created="2024-01-15",
            code_repository="https://github.com/user/repo",
        )

        result = codemeta_to_project_fields(cm)

        assert result["name"] == "My Project"
        assert result["description"] == "Project description"
        assert result["languages"] == ["Python", "C++"]
        assert result["tags"] == ["ai", "ml"]
        assert result["license"] == "MIT"
        assert result["version"] == "1.0.0"
        assert result["status"] == "active"
        assert result["year_started"] == 2024
        assert result["github"] == "https://github.com/user/repo"

    def test_convert_doi(self):
        """Test converting DOI identifier."""
        cm = CodeMetadata(identifier="10.5281/zenodo.1234567")
        result = codemeta_to_project_fields(cm)
        assert result["doi"] == "10.5281/zenodo.1234567"

    def test_convert_doi_url(self):
        """Test converting DOI as URL."""
        cm = CodeMetadata(identifier="https://doi.org/10.5281/zenodo.1234567")
        result = codemeta_to_project_fields(cm)
        assert result["doi"] == "https://doi.org/10.5281/zenodo.1234567"

    def test_convert_authors(self):
        """Test converting authors list."""
        cm = CodeMetadata(
            authors=[
                {"name": "Jane Smith", "email": "jane@example.com"},
                {"name": "John Doe"},
            ]
        )

        result = codemeta_to_project_fields(cm)

        assert "authors" in result
        assert len(result["authors"]) == 2
        assert result["authors"][0]["name"] == "Jane Smith"

    def test_convert_empty_codemeta(self):
        """Test converting empty CodeMetadata returns empty dict."""
        cm = CodeMetadata()
        result = codemeta_to_project_fields(cm)
        assert result == {}

    def test_only_filled_fields_converted(self):
        """Test that only non-empty fields are included in result."""
        cm = CodeMetadata(name="Only Name")

        result = codemeta_to_project_fields(cm)

        assert "name" in result
        # Empty/None fields should not be present
        assert "description" not in result
        assert "languages" not in result
        assert "tags" not in result

    def test_status_mapping_wip(self):
        """Test that wip status maps to active."""
        cm = CodeMetadata(development_status="wip")
        result = codemeta_to_project_fields(cm)
        assert result["status"] == "active"

    def test_status_mapping_abandoned(self):
        """Test that abandoned status maps to archived."""
        cm = CodeMetadata(development_status="abandoned")
        result = codemeta_to_project_fields(cm)
        assert result["status"] == "archived"

    def test_status_mapping_stable(self):
        """Test that stable status maps to maintenance."""
        cm = CodeMetadata(development_status="stable")
        result = codemeta_to_project_fields(cm)
        assert result["status"] == "maintenance"

    def test_status_mapping_unknown_preserved(self):
        """Test that unknown status values are preserved."""
        cm = CodeMetadata(development_status="beta")
        result = codemeta_to_project_fields(cm)
        assert result["status"] == "beta"

    def test_non_github_repo_not_included(self):
        """Test that non-GitHub repositories are not included in github field."""
        cm = CodeMetadata(code_repository="https://gitlab.com/user/repo")
        result = codemeta_to_project_fields(cm)
        assert "github" not in result

    def test_invalid_date_handled(self):
        """Test that invalid date_created doesn't cause error."""
        cm = CodeMetadata(date_created="not-a-date")
        result = codemeta_to_project_fields(cm)
        assert "year_started" not in result


class TestCodeMetadata:
    """Tests for CodeMetadata dataclass."""

    def test_default_values(self):
        """Test that default values are set correctly."""
        metadata = CodeMetadata()

        assert metadata.name is None
        assert metadata.description is None
        assert metadata.authors == []
        assert metadata.programming_languages == []
        assert metadata.keywords == []
        assert metadata.funding == []

    def test_all_fields_accessible(self):
        """Test that all expected fields exist on CodeMetadata."""
        metadata = CodeMetadata(
            name="Test",
            description="Desc",
            authors=[{"name": "Test Author"}],
            programming_languages=["Python"],
            license="MIT License",
            license_id="MIT",
            keywords=["test"],
            version="1.0",
            date_created="2024-01-01",
            date_modified="2024-02-01",
            code_repository="https://github.com/test/repo",
            development_status="active",
            software_requirements=["numpy"],
            runtime_platform=["Linux"],
            operating_system=["Ubuntu"],
            identifier="10.1234/test",
            citation="Test Citation",
            readme="README.md",
            issue_tracker="https://github.com/test/repo/issues",
            funding=[{"name": "Grant"}],
        )

        # All fields should be accessible
        assert metadata.name == "Test"
        assert metadata.description == "Desc"
        assert metadata.license == "MIT License"
        assert metadata.license_id == "MIT"
        assert metadata.software_requirements == ["numpy"]
        assert metadata.runtime_platform == ["Linux"]
        assert metadata.operating_system == ["Ubuntu"]
        assert metadata.citation == "Test Citation"
        assert metadata.readme == "README.md"
        assert metadata.issue_tracker == "https://github.com/test/repo/issues"
