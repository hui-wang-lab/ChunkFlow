# Phase 2 Implementation Summary

Date: 2026-04-28

## Scope Completed

Phase 2 upgraded parser adapters toward true layout-aware IR:

- Added bbox and page-size normalization helpers.
- Added parsed-document validator checks for page references, page block membership, bbox bounds, and zero-area bbox.
- Updated MinerU integration so adapters can consume raw `content_list` artifacts directly.
- Updated `MinerUPdfParser` to preserve layout-aware block data from MinerU `content_list`.
- Updated `DoclingPdfParser` to try native Docling document item extraction before falling back to the older HybridChunker path.
- Added fixture-based tests for bbox normalization, MinerU layout conversion, and Docling native conversion.

## Important Files Added

- `chunkflow/ir/normalize.py`
  - Adds `coerce_bbox`, `extract_bbox`, `bbox_in_page`, and `page_size_from_value`.
  - Supports common bbox shapes:
    - `[x0, y0, x1, y1]`
    - `{"left": ..., "top": ..., "right": ..., "bottom": ...}`
    - polygon points like `[[x, y], ...]`
    - parser objects with bbox-like attributes.

- `test/test_phase2_layout_adapters.py`
  - Uses local fixtures only.
  - Does not call remote MinerU or require Docling installation.
  - Covers bbox normalization, MinerU `content_list` conversion, and Docling fake document conversion.

## Files Modified

- `chunkflow/mineru_parser.py`
  - Added `parse_pdf_with_mineru_artifacts(...)`.
  - Existing `parse_pdf_with_mineru(...)` now reuses this artifact function, then converts to legacy chunk dictionaries for compatibility.

- `chunkflow/parsers/mineru_pdf.py`
  - `MinerUPdfParser` now calls `parse_pdf_with_mineru_artifacts`.
  - New `document_from_mineru_content_list(...)` converts MinerU items into IR `Block`s.
  - Preserves:
    - `bbox`
    - `page_number`
    - page width/height when provided
    - table caption
    - table markdown
    - table HTML
    - figure/image caption
    - image path metadata
    - confidence when present
  - If `content_list` is empty but full markdown exists, the adapter uses the already downloaded markdown as fallback instead of calling MinerU again.

- `chunkflow/parsers/docling_pdf.py`
  - `DoclingPdfParser` now tries native document item extraction first.
  - Added `document_from_docling_document(...)`.
  - Uses duck-typing to tolerate different Docling model versions.
  - Preserves:
    - page number from provenance
    - bbox from provenance or item
    - page size from `doc.pages`
    - table markdown/html when export methods exist
    - captions when available
    - heading path from section headers or metadata
  - Falls back to existing `parse_pdf_with_docling(...)` legacy chunk behavior when native extraction is unavailable or empty.

- `chunkflow/ir/validators.py`
  - Adds warnings for:
    - block referencing a missing page
    - block missing from page `block_ids`
    - bbox outside known page bounds
    - zero-area bbox

## Current Adapter Behavior

### MinerU

Preferred path:

```text
MinerU API -> full.md + content_list.json -> IR Blocks
```

Fallback path:

```text
full.md -> legacy markdown chunk dicts -> IR Blocks
```

The adapter does not call the remote MinerU API twice.

### Docling

Preferred path:

```text
DocumentConverter -> result.document -> native doc items -> IR Blocks
```

Fallback path:

```text
parse_pdf_with_docling HybridChunker -> legacy chunk dicts -> IR Blocks
```

The native path is intentionally permissive because Docling object shapes can differ across versions.

## Verification

Passed compile check:

```bash
wsl -e bash -lc "cd '/mnt/c/Users/wanghui/Desktop/工作空间2026/project/ChunkFlow' && python3 -m py_compile chunkflow/ir/normalize.py chunkflow/ir/validators.py chunkflow/mineru_parser.py chunkflow/parsers/mineru_pdf.py chunkflow/parsers/docling_pdf.py test/test_phase2_layout_adapters.py"
```

Passed Phase 2 tests:

```bash
wsl -e bash -lc "cd '/mnt/c/Users/wanghui/Desktop/工作空间2026/project/ChunkFlow' && python3 -m unittest discover -s test -p 'test_phase2_layout_adapters.py'"
```

```text
Ran 3 tests
OK
```

Passed full test suite:

```bash
wsl -e bash -lc "cd '/mnt/c/Users/wanghui/Desktop/工作空间2026/project/ChunkFlow' && python3 -m unittest discover -s test"
```

```text
Ran 12 tests
OK
```

Passed pypdf pipeline smoke test on one local PDF fixture:

```text
parents: 41
children: 47
warnings: 0
parser: pypdf
chunker: contract_terms
```

Note: verification still used WSL `python3`; the Windows shell does not expose a usable `python` command in this environment.

## Known Limitations

1. Docling native extraction is duck-typed and conservative.
   It should work across common model shapes, but real Docling installations may expose richer structures that deserve targeted extraction later.

2. MinerU page size is only preserved when `content_list` items include page width/height or page info fields.

3. Coordinates are normalized into `BBox`, but no coordinate-system metadata has been formalized yet.

4. The chunkers still do not split an oversized single source block. If a parser emits a huge paragraph block, later chunking may exceed the desired token budget.

5. Captions are attached to table/figure blocks when provided inline by the parser. A later pass could also merge standalone caption blocks by proximity.

## Recommended Next Phase

Phase 3 should focus on core template intelligence:

1. Expand `ContractTermsChunker` beyond generic behavior:
   - detect chapter/article/clause/list hierarchy
   - keep article numbers with text
   - merge cross-page clause continuations
   - keep tables independent but attached to contract heading context

2. Add `LawsChunker`:
   - chapter/section/article/paragraph/item tree
   - child chunks by article or short consecutive articles

3. Add `PaperChunker`:
   - preserve title/authors/abstract
   - section-level parent chunks
   - references handling
   - figure/table caption context

4. Add `ManualChunker`:
   - keep warning/note/procedure blocks intact
   - preserve troubleshooting tables
   - avoid splitting ordered steps

5. Add fixture tests for each template using synthetic IR, not parser-dependent PDFs.

