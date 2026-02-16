"""
Metadata extraction from HTML and PDF files.

Consolidates extraction logic from generate_raw_papers.py and extract_paper_metadata.py.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

# Optional PDF support
try:
    from pypdf import PdfReader
    HAS_PYPDF = True
except ImportError:
    try:
        from PyPDF2 import PdfReader  # type: ignore[assignment]
        HAS_PYPDF = True
    except ImportError:
        HAS_PYPDF = False


@dataclass
class PaperMetadata:
    """Extracted paper metadata."""

    title: str | None = None
    abstract: str | None = None
    authors: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    date: str | None = None
    page_count: int | None = None
    file_size_mb: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary, excluding None values."""
        d: dict[str, Any] = {}
        if self.title:
            d["title"] = self.title
        if self.abstract:
            d["abstract"] = self.abstract
        if self.authors:
            d["authors"] = self.authors
        if self.keywords:
            d["tags"] = self.keywords
        if self.date:
            d["date"] = self.date
        if self.page_count:
            d["page_count"] = self.page_count
        if self.file_size_mb:
            d["file_size_mb"] = self.file_size_mb
        return d


class HTMLMetadataExtractor(HTMLParser):
    """Extract metadata from HTML files (tex2any, pkgdown, etc.)."""

    def __init__(self):
        super().__init__()
        self.title: str | None = None
        self.description: str | None = None
        self.authors: list[str] = []
        self.keywords: list[str] = []
        self.generated_date: str | None = None
        self.document_date: str | None = None
        self.tex2any_config: dict | None = None

        self._in_title = False
        self._title_text = ""
        self._current_tag = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._current_tag = tag
        attrs_dict = dict(attrs)

        if tag == "title":
            self._in_title = True

        elif tag == "meta":
            name = attrs_dict.get("name", "")
            content = attrs_dict.get("content", "")
            prop = attrs_dict.get("property", "")

            # tex2any footer config (contains author, year, etc.)
            if name == "tex2any-footer-config" and content:
                try:
                    self.tex2any_config = json.loads(content)
                    if "author" in self.tex2any_config:
                        author = self.tex2any_config["author"]
                        if isinstance(author, list):
                            self.authors = author
                        elif isinstance(author, str):
                            self.authors = [a.strip() for a in author.split(",")]
                except json.JSONDecodeError:
                    pass

            # Description/abstract
            if name == "description" or prop == "og:description":
                self.description = content

            # Keywords
            if name == "keywords" and content:
                self.keywords = [k.strip() for k in content.split(",")]

            # Author
            if name == "author" and content:
                self.authors = [a.strip() for a in content.split(",")]

            # Date
            if name == "date" and content:
                self.document_date = content

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._title_text += data

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
            if self._title_text.strip():
                # Clean up title
                title = self._title_text.strip()
                # Remove generic package name suffixes
                title = re.sub(r"\s*•\s*[a-z][a-z0-9._-]+$", "", title)
                if title and title != "Contents":
                    self.title = title
        self._current_tag = None

    def handle_comment(self, data: str) -> None:
        # Extract dates from comments
        if "Generated on" in data:
            match = re.search(r"Generated on .+ (\d{4})", data)
            if match:
                self.generated_date = match.group(1)

        if "Document created on" in data:
            match = re.search(r"Document created on .+, (\d{4})", data)
            if match:
                self.document_date = match.group(1)


def extract_from_html(html_path: Path) -> PaperMetadata:
    """Extract metadata from an HTML file.

    Args:
        html_path: Path to HTML file

    Returns:
        Extracted metadata
    """
    metadata = PaperMetadata()

    try:
        with open(html_path, encoding="utf-8", errors="ignore") as f:
            content = f.read()

        parser = HTMLMetadataExtractor()
        parser.feed(content)

        metadata.title = parser.title
        metadata.abstract = parser.description
        metadata.authors = parser.authors
        metadata.keywords = parser.keywords
        metadata.date = parser.document_date or parser.generated_date

    except Exception:
        pass

    return metadata


def extract_from_pdf(pdf_path: Path) -> PaperMetadata:
    """Extract metadata from a PDF file.

    Args:
        pdf_path: Path to PDF file

    Returns:
        Extracted metadata (page count, file size, and any PDF metadata)
    """
    metadata = PaperMetadata()

    if not HAS_PYPDF:
        return metadata

    try:
        reader = PdfReader(str(pdf_path))

        # Page count
        metadata.page_count = len(reader.pages)

        # File size
        file_size = pdf_path.stat().st_size
        metadata.file_size_mb = round(file_size / (1024 * 1024), 2)

        # PDF metadata
        if reader.metadata:
            if reader.metadata.title:
                metadata.title = reader.metadata.title
            if reader.metadata.author:
                metadata.authors = [a.strip() for a in reader.metadata.author.split(",")]
            if reader.metadata.subject:
                metadata.abstract = reader.metadata.subject

    except Exception:
        pass

    return metadata


def extract_meta_tag(html_content: str, name: str) -> str | None:
    """Extract a specific meta tag from HTML content.

    Args:
        html_content: HTML string
        name: Meta tag name to extract

    Returns:
        Meta tag content or None
    """
    # Try name attribute
    pattern = rf'<meta\s+name="{name}"\s+content="([^"]*)"'
    match = re.search(pattern, html_content, re.IGNORECASE)
    if match:
        return match.group(1)

    # Try property attribute (for Open Graph)
    pattern = rf'<meta\s+property="{name}"\s+content="([^"]*)"'
    match = re.search(pattern, html_content, re.IGNORECASE)
    if match:
        return match.group(1)

    return None


def extract_title_from_html(html_content: str) -> str | None:
    """Extract title from HTML content.

    Args:
        html_content: HTML string

    Returns:
        Title or None
    """
    # Try <title> tag
    match = re.search(r"<title>([^<]+)</title>", html_content, re.IGNORECASE)
    if match:
        title = match.group(1).strip()
        # Clean up common suffixes
        title = re.sub(r"\s*•\s*[a-z][a-z0-9._-]+$", "", title)
        if title and title != "Contents":
            return title

    # Try og:title
    title = extract_meta_tag(html_content, "og:title")
    if title:
        return title

    return None
