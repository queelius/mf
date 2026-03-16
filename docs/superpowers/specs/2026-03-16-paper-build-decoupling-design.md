# Paper Build Decoupling — Design Spec

## Problem

`mf papers process` currently invokes `tex2any` and `pdflatex` to build HTML and PDF from LaTeX source. This makes mf a build system — a responsibility that belongs to each paper's own repo via Makefiles. The build tools (`tex2any`) are external dependencies that may not be installed, and different papers may need different build pipelines.

## Decision

Remove all build logic from mf. Papers own their builds (via `make html pdf`). mf becomes a content registry that ingests pre-built artifacts.

## Artifact Path Convention

Given `source_path` pointing to a source file, artifact locations are derived relative to the source file's parent directory.

### Defaults by source format

| Format | Source file | HTML dir default | PDF default |
|--------|-----------|------------------|-------------|
| `tex` | `paper.tex` | `html_paper/` | `{stem}.pdf` |
| `pdf` | `paper.pdf` | _(none)_ | source file itself |
| `pregenerated` | `index.html` | `source_path.parent` | _(glob for *.pdf)_ |

The `tex` HTML default is `html_paper/` — this matches the 22+ Makefiles already created in paper repos (all use `HTMLDIR = html_paper`).

### Override fields in `paper_db.json`

Per-entry overrides (relative to source file's parent directory):

- `html_dir` — path to directory containing `index.html`
- `pdf_file_source` — path to PDF file

These are source-side artifact location overrides. They are distinct from the existing Hugo-side `pdf_path` and `html_path` fields (which are relative to `/static/latex/`).

### Schema changes

Add to `PAPER_SCHEMA` in `field_ops.py`:
- `html_dir`: `FieldDef(FieldType.STRING, "Source HTML directory override")`
- `pdf_file_source`: `FieldDef(FieldType.STRING, "Source PDF file override")`

Update `source_format` choices: `["tex", "pdf", "pregenerated"]` (replace `docx` with `pdf`; no existing DB entries use `docx`).

Add properties to `PaperEntry` in `database.py`:
- `html_dir -> str | None`
- `pdf_file_source -> str | None`

### Resolution function

```python
@dataclass
class ArtifactPaths:
    """Resolved artifact locations for a paper."""
    html_dir: Path | None = None
    pdf_path: Path | None = None

def resolve_artifact_paths(entry: PaperEntry) -> ArtifactPaths:
    """Resolve artifact locations from source_path + format + overrides.

    Returns absolute paths. Returns None for artifacts that don't exist
    or aren't applicable for this format.
    """
```

## New command: `ingest`

Replaces `process`. Copies pre-built artifacts to Hugo static directory.

```
mf papers ingest <slug> [--force]
```

CLI argument is a slug (string), not a filesystem path. The `source_path` is read from the database.

### Preconditions

- Paper must exist in `paper_db.json` (use `mf papers add` first)
- `source_path` must be set and the file must exist at that path
- At least one artifact (HTML dir or PDF) must exist at the resolved path

### Flow

1. Look up entry by slug — error if not found or no `source_path`
2. Verify `source_path` exists on disk — error if missing
3. Call `resolve_artifact_paths(entry)` to find HTML dir and PDF
4. Verify at least one artifact exists — error if neither found
5. Compute source hash, compare to stored `source_hash` — skip if unchanged (unless `--force`)
6. Backup existing `/static/latex/{slug}/` (timestamped, same as today)
7. Copy artifacts to `/static/latex/{slug}/`:
   - If `html_dir` resolved: copy entire directory contents
   - If `pdf_path` resolved: copy PDF file into the target dir
   - (These may come from different locations; `copy_to_static` is called per artifact source, not once)
8. Update `source_hash` and `last_generated` in DB, save
9. Run `generate_paper_content()` to refresh Hugo content page

### No interactive prompts

`ingest` is fully non-interactive. It either succeeds or fails with a clear error message. This makes it scriptable. No `--all` or batch mode — use shell scripting (`mf papers status` → parse → loop) for batch ingestion.

## Renamed command: `status`

Replaces `sync`. Reports staleness without building or ingesting.

```
mf papers status [--slug <slug>]
```

Uses existing `check_all_papers()` + `print_sync_status()` infrastructure. The auto-rebuild portion of `sync_papers()` is deleted.

## Modifications

### `sync.py`: `check_paper_staleness()`

Remove the `source_format != "tex"` early-return guard. All formats with a `source_path` should be hash-checked for staleness. The function should only skip entries that have no `source_path` or where the source is a directory.

### `processor.py`: artifact copying

The current `copy_to_static(source_dir, slug)` copies from a single source directory. The new `ingest_paper()` function will call it for the HTML directory (if present) and separately copy the PDF file. No signature change needed — `copy_to_static` handles directories, and a simple `shutil.copy2` handles the standalone PDF.

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
| `_process_single_paper_with_timeout()` | Subprocess-based rebuild (contains inline `process_paper` import) |
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
- `check_paper_staleness()` — hash-based staleness detection (**modified**: remove tex-only guard)
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

- `process` command → replaced by `ingest` command (argument changes from `SOURCE` path to `SLUG` string)
- `sync` command → replaced by `status` command (remove `--workers`, `--timeout`, `--yes` flags)
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

- `test_processor.py` — delete build tests (`test_generate_html_*`, `test_generate_pdf_*`, `test_find_tex_files`), update imports (remove `find_tex_files`, `run_command`, `generate_html`, `generate_pdf`, `process_paper`), add `test_resolve_artifact_paths` and `test_ingest_paper` tests
- `test_sync.py` — delete rebuild tests (`test_sync_*` that call `process_paper`), keep staleness detection tests, add test for non-tex format staleness check
- `test_generator.py` — no changes (metadata extraction tests here stay as-is; remove any tex2any-footer-config specific assertions if present)
- `test_commands.py` — replace `process` CLI tests with `ingest` CLI tests, replace `sync` CLI tests with `status` CLI tests
