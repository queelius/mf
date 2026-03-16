# Paper Build Decoupling — Design Spec

## Problem

`mf papers process` currently invokes `tex2any` and `pdflatex` to build HTML and PDF from LaTeX source. This makes mf a build system — a responsibility that belongs to each paper's own repo via Makefiles. The build tools (`tex2any`) are external dependencies that may not be installed, and different papers may need different build pipelines.

## Decision

Remove all build logic from mf. Papers own their builds (via `make html pdf`). mf becomes a content registry that ingests pre-built artifacts.

## Artifact Path Convention

Given `source_path` pointing to a source file, artifact locations are derived from the filename stem, relative to the source file's parent directory.

### Defaults by source format

| Format | Source file | HTML dir default | PDF default |
|--------|-----------|------------------|-------------|
| `tex` | `paper.tex` | `paper_html/` | `paper.pdf` |
| `pdf` | `paper.pdf` | _(none)_ | `paper.pdf` (same as source) |
| `pregenerated` | `index.html` | `source_path.parent` | _(glob for *.pdf)_ |

### Override fields in `paper_db.json`

Per-entry overrides (relative to source file's parent directory):

- `html_dir` — path to directory containing `index.html`
- `pdf_file_source` — path to PDF file

### Resolution function

```python
def resolve_artifact_paths(entry: PaperEntry) -> tuple[Path | None, Path | None]:
    """Return (html_dir, pdf_path) resolved from source_path + format + overrides."""
```

Returns absolute paths. Returns `None` for artifacts that don't exist or aren't applicable.

## New command: `ingest`

Replaces `process`. Copies pre-built artifacts to Hugo static directory.

```
mf papers ingest <slug> [--force]
```

### Preconditions

- Paper must exist in `paper_db.json` (use `mf papers add` first)
- `source_path` must be set in the DB entry
- At least one artifact (HTML dir or PDF) must exist at the resolved path

### Flow

1. Look up entry by slug — error if not found or no `source_path`
2. Call `resolve_artifact_paths(entry)` to find HTML dir and PDF
3. Verify at least one artifact exists — error if neither found
4. Compute source hash, compare to stored `source_hash` — skip if unchanged (unless `--force`)
5. Backup existing `/static/latex/{slug}/` (timestamped, same as today)
6. Copy artifacts to `/static/latex/{slug}/`
7. Update `source_hash` and `last_generated` in DB, save
8. Run `generate_paper_content()` to refresh Hugo content page

### No interactive prompts

`ingest` is fully non-interactive. It either succeeds or fails with a clear error message. This makes it scriptable.

## Renamed command: `status`

Replaces `sync`. Reports staleness without building or ingesting.

```
mf papers status [--slug <slug>]
```

Uses existing `check_all_papers()` + `print_sync_status()` infrastructure unchanged. The auto-rebuild portion of `sync_papers()` is deleted.

## Deletions

### From `processor.py`

| Function | Reason |
|----------|--------|
| `generate_html()` | tex2any invocation — build responsibility |
| `generate_pdf()` | 5-pass pdflatex pipeline — build responsibility |
| `run_command()` | Only used by `generate_html`/`generate_pdf` |
| `find_tex_files()` | Scanning for .tex files — no longer needed |
| `process_paper()` | Full orchestration — replaced by `ingest_paper()` |

### From `sync.py`

| Function/Class | Reason |
|----------------|--------|
| `sync_papers()` | Auto-rebuild orchestrator |
| `_process_papers_parallel()` | Parallel rebuild |
| `_process_papers_sequential()` | Sequential rebuild |
| `_process_single_paper_with_timeout()` | Subprocess-based rebuild |
| `process_stale_paper()` | Single paper rebuild |
| `SyncResults` | Only used by rebuild |
| `ProcessingResult` | Only used by rebuild |

### From `metadata.py`

| Code | Reason |
|------|--------|
| `tex2any-footer-config` meta tag parsing (lines 89-100) | tex2any-specific; standard meta tags stay |
| `tex2any_config` field on `HTMLMetadataExtractor` | Associated state |

## What stays

### `processor.py` (becomes ingest module)

- `copy_to_static()` — copies artifacts to `/static/latex/{slug}/`
- `backup_existing_paper()` — timestamped backup before overwrite
- `restore_backup()` — restore on failure
- **New:** `resolve_artifact_paths()` — convention-based artifact discovery
- **New:** `ingest_paper()` — the new orchestration function

### `sync.py` (becomes status-only)

- `SyncStatus` dataclass
- `check_paper_staleness()` — hash-based staleness detection
- `check_all_papers()` — batch staleness check
- `print_sync_status()` — Rich table output

### `metadata.py` (standard extraction only)

- `HTMLMetadataExtractor` — `<title>`, `<meta name="author">`, `<meta name="keywords">`, `<meta name="description">`, `<meta name="date">`, Open Graph tags
- `extract_from_html()` — parse HTML for metadata
- `extract_from_pdf()` — page count, file size, PDF metadata
- `extract_meta_tag()`, `extract_title_from_html()` — utility functions

### `generator.py` (unchanged)

Already works with whatever's in `/static/latex/{slug}/`. No changes needed.

### `commands.py` (rewired)

- `process` command → replaced by `ingest` command
- `sync` command → replaced by `status` command
- All other commands unchanged (`generate`, `list`, `show`, `set`, `unset`, `tag`, `feature`, etc.)

## Workflow

```
# One-time: register the paper
mf papers add cipher-maps --source ~/github/.../cipher_maps.tex

# Build in the paper's repo
cd ~/github/trapdoor-computing/papers/cipher-maps-unified/paper
make html pdf

# Ingest pre-built artifacts into Hugo site
mf papers ingest cipher-maps

# Check what's stale across all papers
mf papers status
```

## `source_path` semantics

`source_path` is the hashable file that represents the paper's source state:

- **LaTeX papers**: the `.tex` file (hash detects source changes)
- **PDF-only papers**: the PDF itself (hash detects new versions)
- **Pregenerated papers**: `index.html` (hash detects rebuild)

The `source_format` field (`tex`, `pdf`, `pregenerated`) determines which default artifact resolution rules apply.

## Test impact

- `test_processor.py` — delete build tests (`test_generate_html_*`, `test_generate_pdf_*`), add `test_resolve_artifact_paths`, `test_ingest_paper` tests
- `test_sync.py` — delete rebuild tests, keep staleness detection tests
- `test_metadata.py` — remove tex2any-footer-config test, keep standard extraction tests
- `test_commands.py` — update `process` → `ingest`, `sync` → `status` CLI tests
