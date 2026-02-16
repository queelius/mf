"""
Hugo frontmatter templates for papers.

Provides templates for generating Hugo content pages from paper metadata.
"""

from __future__ import annotations

from typing import Any

PAPER_TEMPLATE = '''---
title: "{title}"
slug: "{slug}"
{aliases}{draft}date: {date}
{authors}{abstract}{keywords}{genres}{category}{stars}{venue}{status}{featured}{arxiv_id}{doi}{github_url}{project_url}{external_url}{image}pdf_file: "{pdf_file}"
pdf_size: "{pdf_size}"
page_count: {page_count}
pdf_only: false
---

<style>
.iframe-wrap {{
  width: 100%;
  max-width: 100%;
  margin: 0;
  padding: 0;
}}
.iframe-wrap iframe {{
  display: block;
  width: 100%;
  border: 0;
  min-height: 120vh;
}}
.action-bar {{
  margin: 0 0 1rem 0;
  padding: 0 1rem;
  display: flex;
  gap: .75rem;
  flex-wrap: wrap;
}}
.action-bar a {{
  text-decoration: none;
  padding: .5rem .75rem;
  border: 1px solid var(--color-border-default, #ddd);
  border-radius: .4rem;
  display: inline-block;
  color: var(--color-accent-primary, #007acc);
}}
.action-bar a:hover {{
  background: var(--color-bg-secondary, #f5f5f5);
}}
</style>

<div class="action-bar">
  <a href="/latex/{slug}/index.html" target="_blank" rel="noopener">Open full page</a>
  {pdf_link}{arxiv_link}
</div>

<div class="iframe-wrap">
  <iframe id="ltx" src="/latex/{slug}/index.html" loading="lazy" scrolling="no"></iframe>
</div>

<script>
(function () {{
  const iframe = document.getElementById('ltx');

  if (location.hash) {{
    const u = new URL(iframe.src, location.origin);
    u.hash = location.hash;
    iframe.src = u.toString();
  }}

  let lastScrollHeight = 0;

  function setHeight(h) {{
    const newH = Math.ceil(h);
    if (newH > lastScrollHeight + 5) {{
      iframe.style.height = newH + 'px';
      lastScrollHeight = newH;
    }}
  }}

  function measure(doc) {{
    const h = Math.max(
      doc.body?.scrollHeight || 0,
      doc.documentElement?.scrollHeight || 0
    );
    if (h > 0) setHeight(h);
  }}

  iframe.addEventListener('load', () => {{
    const doc = iframe.contentDocument || iframe.contentWindow.document;
    if (!doc) return;

    setTimeout(() => measure(doc), 100);
    setTimeout(() => measure(doc), 500);

    doc.fonts?.ready?.then(() => {{
      setTimeout(() => measure(doc), 50);
    }}).catch(() => {{}});

    const images = Array.from(doc.images || []);
    if (images.length > 0) {{
      let loadedCount = 0;
      images.forEach(img => {{
        if (img.complete) {{
          loadedCount++;
        }} else {{
          img.addEventListener('load', () => {{
            loadedCount++;
            if (loadedCount === images.length) {{
              setTimeout(() => measure(doc), 50);
            }}
          }}, {{ once: true }});
        }}
      }});
    }}

    let resizeTimeout;
    window.addEventListener('resize', () => {{
      clearTimeout(resizeTimeout);
      resizeTimeout = setTimeout(() => {{
        lastScrollHeight = 0;
        measure(doc);
      }}, 300);
    }});
  }});
}})();
</script>
'''

PDF_ONLY_TEMPLATE = '''---
title: "{title}"
slug: "{slug}"
{aliases}{draft}date: {date}
{authors}{abstract}{keywords}{genres}{category}{stars}{venue}{status}{featured}{arxiv_id}{doi}{github_url}{project_url}{external_url}{image}pdf_file: "{pdf_file}"
pdf_size: "{pdf_size}"
page_count: {page_count}
pdf_only: true
---

<style>
.pdf-container {{
  width: 100%;
  margin: 0;
}}
.pdf-container embed {{
  width: 100%;
  min-height: 90vh;
  border: 1px solid var(--color-border-default, #ddd);
  border-radius: 0.5rem;
}}
.action-bar {{
  margin: 0 0 1rem 0;
  display: flex;
  gap: .75rem;
  flex-wrap: wrap;
}}
.action-bar a {{
  text-decoration: none;
  padding: .5rem .75rem;
  border: 1px solid var(--color-border-default, #ddd);
  border-radius: .4rem;
  display: inline-block;
  color: var(--color-accent-primary, #007acc);
}}
.action-bar a:hover {{
  background: var(--color-bg-secondary, #f5f5f5);
}}
</style>

<div class="action-bar">
  <a href="/latex/{slug}/{pdf_file}" target="_blank" rel="noopener">Download PDF</a>
  {arxiv_link}
</div>

<div class="pdf-container">
  <embed src="/latex/{slug}/{pdf_file}" type="application/pdf">
</div>
'''


def format_yaml_list(items: list[str], indent: int = 2) -> str:
    """Format a list as YAML array.

    Args:
        items: List of strings
        indent: Indentation level

    Returns:
        YAML formatted string
    """
    if not items:
        return "[]"
    prefix = " " * indent
    return "\n" + "\n".join(f'{prefix}- "{item}"' for item in items)


def render_frontmatter_field(
    key: str,
    value: Any,
    as_list: bool = False,
) -> str:
    """Render a single frontmatter field.

    Args:
        key: Field name
        value: Field value
        as_list: Whether to format as YAML list

    Returns:
        Formatted frontmatter line or empty string
    """
    if value is None:
        return ""

    if as_list and isinstance(value, list):
        if not value:
            return ""
        return f"{key}:{format_yaml_list(value)}\n"

    if isinstance(value, bool):
        return f"{key}: {str(value).lower()}\n"

    if isinstance(value, (int, float)):
        return f"{key}: {value}\n"

    # String value - escape quotes
    value = str(value).replace('"', '\\"')
    return f'{key}: "{value}"\n'


def render_paper_frontmatter(
    slug: str,
    metadata: dict[str, Any],
    pdf_file: str,
    pdf_size: str,
    page_count: int,
) -> dict[str, str]:
    """Render frontmatter substitution variables.

    Args:
        slug: Paper slug
        metadata: Paper metadata dict
        pdf_file: PDF filename
        pdf_size: Human-readable PDF size
        page_count: Number of pages

    Returns:
        Dict of template substitution variables
    """
    # Escape title for YAML
    title = metadata.get("title", slug).replace('"', '\\"')

    # Format authors
    authors = metadata.get("authors", [])
    authors_str = ""
    if authors:
        authors_str = "authors:\n" + "\n".join(f'  - "{a}"' for a in authors) + "\n"

    # Format abstract
    abstract = metadata.get("abstract", "")
    abstract_str = ""
    if abstract:
        # Escape for YAML
        abstract = abstract.replace('"', '\\"').replace("\n", " ")
        abstract_str = f'abstract: "{abstract}"\n'

    # Format keywords/tags
    keywords = metadata.get("tags", [])
    keywords_str = ""
    if keywords:
        keywords_str = "tags:\n" + "\n".join(f'  - "{k}"' for k in keywords) + "\n"

    # Format genres taxonomy
    genres = metadata.get("genres", [])
    genres_str = ""
    if genres:
        genres_str = "genres:\n" + "\n".join(f'  - "{g}"' for g in genres) + "\n"

    # Optional fields
    category = metadata.get("category", "")
    category_str = f'category: "{category}"\n' if category else ""

    stars = metadata.get("stars")
    stars_str = f"stars: {stars}\n" if stars else ""

    venue = metadata.get("venue", "")
    venue_str = f'venue: "{venue}"\n' if venue else ""

    status = metadata.get("status", "")
    status_str = f'status: "{status}"\n' if status else ""

    featured = metadata.get("featured", False)
    featured_str = "featured: true\n" if featured else ""

    arxiv_id = metadata.get("arxiv_id", "")
    arxiv_str = f'arxiv_id: "{arxiv_id}"\n' if arxiv_id else ""

    doi = metadata.get("doi", "")
    doi_str = f'doi: "{doi}"\n' if doi else ""

    github_url = metadata.get("github_url", "")
    github_str = f'github_url: "{github_url}"\n' if github_url else ""

    project_url = metadata.get("project_url", "")
    project_str = f'project_url: "{project_url}"\n' if project_url else ""

    external_url = metadata.get("external_url", "")
    external_str = f'external_url: "{external_url}"\n' if external_url else ""

    image = metadata.get("image", "")
    image_str = f'image: "{image}"\n' if image else ""

    # Date
    date = metadata.get("date", "2024-01-01")

    # Aliases for Hugo redirects
    aliases = metadata.get("aliases", [])
    aliases_str = ""
    if aliases:
        aliases_str = "aliases:\n" + "\n".join(f'  - {a}' for a in aliases) + "\n"

    # Draft status
    draft = metadata.get("draft", False)
    draft_str = "draft: true\n" if draft else ""

    # Action bar links
    pdf_link = f'<a href="/latex/{slug}/{pdf_file}" target="_blank" rel="noopener">Download PDF</a>\n  '
    arxiv_link = ""
    if arxiv_id:
        arxiv_link = f'<a href="https://arxiv.org/abs/{arxiv_id}" target="_blank" rel="noopener">arXiv</a>'

    return {
        "title": title,
        "slug": slug,
        "date": date,
        "aliases": aliases_str,
        "draft": draft_str,
        "authors": authors_str,
        "abstract": abstract_str,
        "keywords": keywords_str,
        "genres": genres_str,
        "category": category_str,
        "stars": stars_str,
        "venue": venue_str,
        "status": status_str,
        "featured": featured_str,
        "arxiv_id": arxiv_str,
        "doi": doi_str,
        "github_url": github_str,
        "project_url": project_str,
        "external_url": external_str,
        "image": image_str,
        "pdf_file": pdf_file,
        "pdf_size": pdf_size,
        "page_count": page_count,
        "pdf_link": pdf_link,
        "arxiv_link": arxiv_link,
    }
