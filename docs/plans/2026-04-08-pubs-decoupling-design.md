# Design: Decoupled Publications Database

**Date**: 2026-04-08
**Status**: Proposed
**Author**: Alex Towell

## Motivation

`mf pubs` currently derives its data from `paper_db.json`, filtering for entries with a venue, `status: published`, or a DOI. This coupling creates several problems:

1. **Lifecycle tracking**: `paper_db.json` tracks ingestion state (source hashes, artifact paths). Publication lifecycle (draft, submitted, under review, accepted) is a different concern.
2. **Schema tension**: Adding publication-specific fields (venue details, submission timeline, reviewer feedback) clutters the ingestion database.
3. **Scope mismatch**: `paper_db` has 57 entries including legacy work. The publication list should be curated, not filtered.
4. **Artifact tracking**: Publications accumulate artifacts over time (slides, posters, videos, BibTeX). These don't belong in the ingestion pipeline.

## Design

Introduce `pubs_db.json` as a separate JSON database for publications. `mf pubs` reads from this database instead of `paper_db.json`. The two databases can reference each other via slugs but are independently managed.

### Relationship to paper_db

- `paper_db.json`: ingestion pipeline. Source repo to Hugo site. Tracks source hashes, build artifacts, ingestion state.
- `pubs_db.json`: publication lifecycle. Tracks status, venue, submissions, artifacts, timeline.
- A pubs entry MAY reference a `paper_slug` in paper_db for asset resolution (PDF, HTML). This is optional: a pub can exist without a paper_db entry (external publication), and a paper_db entry can exist without a pub entry (legacy/archived).

### File Location

`/home/spinoza/github/repos/metafunctor/.mf/pubs_db.json`

(Same directory as `paper_db.json`.)

### Schema

```json
{
  "_schema_version": 1,
  "dreamlog-compression": {
    "title": "Compression Enables Generalization: Wake-Sleep Cycles for Logic Programming with LLM Integration",
    "authors": [
      {"name": "Alexander Towell", "email": "lex@metafunctor.com", "orcid": "0000-0001-6443-9897"}
    ],
    "date": "2026-04-08",
    "abstract": "Knowledge bases in logic programming grow through fact accumulation but do not learn...",

    "status": "draft",
    "type": "conference paper",
    "tags": ["compression", "logic programming", "LLM", "Solomonoff induction"],

    "venue": null,
    "venue_details": {
      "name": null,
      "track": null,
      "year": null,
      "location": null
    },
    "doi": null,
    "arxiv_id": null,
    "isbn": null,

    "source_repo": "beta/dreamlog",
    "paper_slug": "dreamlog-compression",

    "artifacts": {
      "pdf": "/latex/dreamlog-compression/paper.pdf",
      "html": "/latex/dreamlog-compression/",
      "slides": null,
      "poster": null,
      "video": null,
      "bibtex": "/latex/dreamlog-compression/cite.bib",
      "supplement": null,
      "code": "https://github.com/queelius/dreamlog",
      "data": null,
      "photos": null
    },

    "links": [
      {"name": "GitHub", "url": "https://github.com/queelius/dreamlog"}
    ],

    "timeline": [
      {"date": "2026-04-08", "event": "draft-complete", "note": "Initial draft with EX25b results"}
    ]
  }
}
```

### Field Reference

#### Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `title` | string | Publication title |
| `authors` | array | Author objects with name, email, optional orcid |
| `date` | string | ISO date (creation or publication date) |
| `status` | string | Lifecycle status (see below) |
| `type` | string | Publication type (see below) |

#### Status Lifecycle

```
draft --> preprint --> submitted --> under-review --> accepted --> published
                  \-> withdrawn     \-> rejected --> revised --> resubmitted
```

| Status | Meaning |
|--------|---------|
| `draft` | Active writing, not shared publicly |
| `preprint` | Shared publicly (arXiv, etc.) but not peer-reviewed |
| `submitted` | Submitted to a venue, awaiting review |
| `under-review` | Actively being reviewed |
| `accepted` | Accepted by venue, not yet published |
| `published` | Published with DOI or in proceedings |
| `rejected` | Rejected by a venue |
| `revised` | Being revised after rejection or reviewer feedback |
| `withdrawn` | Withdrawn by author |

#### Publication Types

| Type | Description |
|------|-------------|
| `conference paper` | Peer-reviewed conference proceedings |
| `journal article` | Peer-reviewed journal publication |
| `workshop paper` | Workshop proceedings |
| `thesis` | MS or PhD thesis |
| `technical report` | Institutional report |
| `white paper` | Industry or independent report |
| `preprint` | arXiv or similar |
| `book chapter` | Chapter in edited volume |

#### Optional Fields

| Field | Type | Description |
|-------|------|-------------|
| `abstract` | string | Paper abstract |
| `tags` | array | Topic tags |
| `venue` | string | Venue name (journal, conference) |
| `venue_details` | object | Structured venue info (name, track, year, location) |
| `doi` | string | Digital Object Identifier |
| `arxiv_id` | string | arXiv identifier (e.g., "2406.12345") |
| `isbn` | string | ISBN for books/proceedings |
| `source_repo` | string | Relative path from ~/github/ to source repo |
| `paper_slug` | string | Slug in paper_db (for asset resolution) |
| `artifacts` | object | Publication artifacts (see below) |
| `links` | array | External links |
| `timeline` | array | Event log |

#### Artifacts

Each value is a path (relative to Hugo site root, starting with `/`) or a URL (starting with `http`). Null or absent means the artifact doesn't exist yet.

| Key | Description |
|-----|-------------|
| `pdf` | Paper PDF |
| `html` | Web-rendered HTML version |
| `slides` | Presentation slides (PDF or URL) |
| `poster` | Conference poster |
| `video` | Recorded talk (URL) |
| `bibtex` | BibTeX citation file |
| `supplement` | Supplementary material |
| `code` | Code repository (URL) |
| `data` | Dataset (URL, e.g., Zenodo) |
| `photos` | Conference/event photos (directory path or URL) |

#### Timeline Events

```json
{"date": "2026-04-08", "event": "draft-complete", "note": "Initial draft"}
{"date": "2026-05-01", "event": "submitted", "note": "Submitted to AAAI 2027"}
{"date": "2026-07-15", "event": "reviews-received", "note": "3 reviews, major revision"}
{"date": "2026-08-01", "event": "revised", "note": "Addressed all reviewer concerns"}
{"date": "2026-09-01", "event": "accepted", "note": "Accepted to AAAI 2027"}
{"date": "2027-02-15", "event": "published", "note": "DOI: 10.xxxx/yyyy"}
```

## Implementation Plan

### Phase 1: Database and Core

1. Create `PubsDatabase` class in `mf/publications/database.py`
   - Load/save `pubs_db.json`
   - `PubEntry` dataclass with typed fields
   - Validation: required fields, status values, artifact paths

2. Create seed `pubs_db.json` with existing published works
   - Migrate entries from paper_db that have `status: published` or a venue
   - Add artifact paths from paper_db
   - This is a one-time migration; after this the databases are independent

### Phase 2: CLI Commands

Update `mf pubs` to read from `pubs_db.json`:

| Command | Description |
|---------|-------------|
| `mf pubs list` | List publications (filter by status, type, tag, venue) |
| `mf pubs show SLUG` | Show full details |
| `mf pubs add SLUG` | Add a new publication entry (interactive or from flags) |
| `mf pubs update SLUG` | Update fields (status, venue, artifacts, etc.) |
| `mf pubs log SLUG EVENT` | Append a timeline event |
| `mf pubs generate` | Generate Hugo content from pubs_db |
| `mf pubs stats` | Database statistics |
| `mf pubs migrate` | One-time migration from paper_db |

### Phase 3: Hugo Integration

- Update `/content/publications/` generation to use pubs_db
- Artifact links in publication pages (PDF, slides, video, poster icons)
- Status badges in listings (draft, preprint, under review, published)
- Timeline display on individual publication pages

### Phase 4: Transition

- `mf papers` continues to work unchanged (ingestion pipeline)
- `mf pubs generate` reads from pubs_db instead of paper_db
- Legacy papers in paper_db that aren't in pubs_db remain as `/content/papers/` only
- New publications go directly into pubs_db via `mf pubs add`

## Non-Goals

- Automatic sync between paper_db and pubs_db (explicit migration only)
- Replacing paper_db (it serves the ingestion pipeline, a different concern)
- Tracking reviewer identities or confidential review content in the database
