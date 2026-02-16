"""Tests for mf.papers.citation module (CITATION.cff parsing)."""

import pytest

from mf.papers.citation import (
    CitationMetadata,
    parse_cff,
    cff_to_paper_fields,
)


class TestParseCff:
    """Tests for parse_cff function."""

    def test_parse_minimal_cff(self):
        """Test parsing a minimal CITATION.cff with just required fields."""
        content = """
cff-version: 1.2.0
message: "If you use this software, please cite it as below."
title: "My Research Software"
authors:
  - family-names: "Doe"
    given-names: "John"
"""
        result = parse_cff(content)

        assert isinstance(result, CitationMetadata)
        assert result.title == "My Research Software"
        assert len(result.authors) == 1
        assert result.authors[0]["family-names"] == "Doe"
        assert result.authors[0]["given-names"] == "John"

    def test_parse_full_cff(self):
        """Test parsing a CITATION.cff with all common fields."""
        content = """
cff-version: 1.2.0
message: "Please cite this work"
title: "Complete Research Software"
type: software
abstract: "A comprehensive tool for research."
authors:
  - family-names: "Smith"
    given-names: "Jane"
    orcid: "https://orcid.org/0000-0001-2345-6789"
    email: "jane@example.com"
    affiliation: "Research University"
  - family-names: "Doe"
    given-names: "John"
date-released: "2024-06-15"
version: "2.0.0"
doi: "10.5281/zenodo.1234567"
license: MIT
repository-code: "https://github.com/user/repo"
keywords:
  - machine-learning
  - data-science
  - python
"""
        result = parse_cff(content)

        assert result.title == "Complete Research Software"
        assert result.abstract == "A comprehensive tool for research."
        assert result.date_released == "2024-06-15"
        assert result.version == "2.0.0"
        assert result.doi == "10.5281/zenodo.1234567"
        assert result.license == "MIT"
        assert result.repository_code == "https://github.com/user/repo"
        assert result.cff_type == "software"
        assert len(result.authors) == 2
        assert result.authors[0]["orcid"] == "https://orcid.org/0000-0001-2345-6789"
        assert result.keywords == ["machine-learning", "data-science", "python"]

    def test_parse_empty_cff(self):
        """Test parsing an empty CITATION.cff."""
        content = ""
        result = parse_cff(content)

        assert result.title is None
        assert result.authors == []
        assert result.keywords == []

    def test_parse_cff_missing_optional_fields(self):
        """Test that missing optional fields return None/empty lists."""
        content = """
cff-version: 1.2.0
title: "Simple Software"
"""
        result = parse_cff(content)

        assert result.title == "Simple Software"
        assert result.abstract is None
        assert result.doi is None
        assert result.date_released is None
        assert result.version is None
        assert result.keywords == []
        assert result.authors == []


class TestCffToPaperFields:
    """Tests for cff_to_paper_fields conversion."""

    def test_convert_basic_fields(self):
        """Test converting basic CFF fields to paper_db format."""
        cff = CitationMetadata(
            title="My Paper",
            authors=[],
            date_released="2024-06-15",
            doi="10.5281/zenodo.1234567",
            version="1.0.0",
            keywords=["ai", "ml"],
            repository_code=None,
            license=None,
            cff_type=None,
            abstract="Paper abstract here.",
        )

        result = cff_to_paper_fields(cff)

        assert result["title"] == "My Paper"
        assert result["abstract"] == "Paper abstract here."
        assert result["doi"] == "10.5281/zenodo.1234567"
        assert result["date"] == "2024-06-15"
        assert result["tags"] == ["ai", "ml"]

    def test_convert_authors(self):
        """Test converting CFF author format to paper_db format."""
        cff = CitationMetadata(
            title="Authored Paper",
            authors=[
                {
                    "given-names": "Jane",
                    "family-names": "Smith",
                    "orcid": "https://orcid.org/0000-0001-2345-6789",
                    "email": "jane@example.com",
                    "affiliation": "MIT",
                },
                {
                    "given-names": "John",
                    "family-names": "Doe",
                },
            ],
            date_released=None,
            doi=None,
            version=None,
            keywords=[],
            repository_code=None,
            license=None,
            cff_type=None,
            abstract=None,
        )

        result = cff_to_paper_fields(cff)

        assert "authors" in result
        assert len(result["authors"]) == 2

        # First author should have all fields
        assert result["authors"][0]["name"] == "Jane Smith"
        assert result["authors"][0]["orcid"] == "https://orcid.org/0000-0001-2345-6789"
        assert result["authors"][0]["email"] == "jane@example.com"
        assert result["authors"][0]["affiliation"] == "MIT"

        # Second author should have just name
        assert result["authors"][1]["name"] == "John Doe"
        assert "orcid" not in result["authors"][1]

    def test_convert_empty_cff(self):
        """Test converting empty CFF returns empty dict."""
        cff = CitationMetadata(
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

        result = cff_to_paper_fields(cff)

        # Empty CFF should return empty dict (no fields to merge)
        assert result == {}

    def test_only_filled_fields_converted(self):
        """Test that only non-empty fields are included in result."""
        cff = CitationMetadata(
            title="Title Only",
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

        result = cff_to_paper_fields(cff)

        assert "title" in result
        # Empty/None fields should not be present
        assert "abstract" not in result
        assert "doi" not in result
        assert "date" not in result
        assert "tags" not in result
        assert "authors" not in result

    def test_author_with_only_family_name(self):
        """Test handling author with only family name (no given name)."""
        cff = CitationMetadata(
            title="Test",
            authors=[{"family-names": "LastNameOnly"}],
            date_released=None,
            doi=None,
            version=None,
            keywords=[],
            repository_code=None,
            license=None,
            cff_type=None,
            abstract=None,
        )

        result = cff_to_paper_fields(cff)

        assert result["authors"][0]["name"] == "LastNameOnly"

    def test_author_with_only_given_name(self):
        """Test handling author with only given name (no family name)."""
        cff = CitationMetadata(
            title="Test",
            authors=[{"given-names": "FirstNameOnly"}],
            date_released=None,
            doi=None,
            version=None,
            keywords=[],
            repository_code=None,
            license=None,
            cff_type=None,
            abstract=None,
        )

        result = cff_to_paper_fields(cff)

        assert result["authors"][0]["name"] == "FirstNameOnly"


class TestCitationMetadata:
    """Tests for CitationMetadata dataclass."""

    def test_dataclass_fields(self):
        """Test that all expected fields exist on CitationMetadata."""
        metadata = CitationMetadata(
            title="Test",
            authors=[],
            date_released="2024-01-01",
            doi="10.1234/test",
            version="1.0",
            keywords=["test"],
            repository_code="https://github.com/test/repo",
            license="MIT",
            cff_type="software",
            abstract="Test abstract",
        )

        # All fields should be accessible
        assert metadata.title == "Test"
        assert metadata.authors == []
        assert metadata.date_released == "2024-01-01"
        assert metadata.doi == "10.1234/test"
        assert metadata.version == "1.0"
        assert metadata.keywords == ["test"]
        assert metadata.repository_code == "https://github.com/test/repo"
        assert metadata.license == "MIT"
        assert metadata.cff_type == "software"
        assert metadata.abstract == "Test abstract"
