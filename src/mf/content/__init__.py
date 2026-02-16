"""
Content management module for Hugo site.

Provides tools for:
- Scanning Hugo content files
- Matching content to projects
- Updating front matter safely
- Querying across content types
- Auditing linked_project references
"""

from mf.content.auditor import AuditIssue, AuditResult, AuditStats, ContentAuditor
from mf.content.frontmatter import FrontMatterEditor
from mf.content.matcher import Match, ProjectMatcher
from mf.content.scanner import ContentItem, ContentScanner

__all__ = [
    "ContentScanner",
    "ContentItem",
    "ProjectMatcher",
    "Match",
    "FrontMatterEditor",
    "ContentAuditor",
    "AuditResult",
    "AuditIssue",
    "AuditStats",
]
