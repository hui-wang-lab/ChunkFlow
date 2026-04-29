# Phase 1 Implementation Summary

Date: 2026-04-28

## Scope Completed

Phase 1 implemented the first architecture split from the design document:

- Added a normalized document IR.
- Added parser adapters for Docling, MinerU, and pypdf fallback.
- Added a pipeline entry point that runs `parse -> section tree -> template chunker -> postprocess -> ChunkPackage`.
- Added a template chunker registry.
- Added a Phase 1 `contract_terms` chunker and a fallback `generic_structured` chunker.
- Added chapter/section-style parent chunks and child chunks.
- Added text context windows for table/figure/caption child chunks.
- Changed `/api/parse` to return the new `ChunkPackage` shape instead of the old flat `chunks` list.
- Updated the web UI to render `child_chunks`.
- Added a focused Phase 1 unit test for parent-child generation and table context.

## Important Files Added

- `chunkflow/ir/models.py`
  - Defines `ParsedDocument`, `Page`, `Block`, `SectionNode`, `ParseReport`, `ParentChunk`, `ChildChunk`, and `ChunkPackage`.

- `chunkflow/ir/section_tree.py`
  - Builds a conservative heading-path section tree and assigns `section_id` to blocks.

- `chunkflow/ir/validators.py`
  - Adds basic parsed-document and chunk-package invariant checks.

- `chunkflow/core/ids.py`
  - Centralizes stable IDs for blocks, sections, parent chunks, and child chunks.

- `chunkflow/core/document_type.py`
  - Adds simple automatic document type detection.

- `chunkflow/core/pipeline.py`
  - New main orchestration entry point: `parse_to_chunk_package(file_path, PipelineConfig(...))`.

- `chunkflow/parsers/base.py`
  - Parser adapter interface and `ParserConfig`.

- `chunkflow/parsers/docling_pdf.py`
  - Adapter around existing Docling parser.

- `chunkflow/parsers/mineru_pdf.py`
  - Adapter around existing MinerU parser.

- `chunkflow/parsers/pypdf_fallback.py`
  - Basic pypdf paragraph-block fallback parser.

- `chunkflow/parsers/utils.py`
  - Shared helpers for converting legacy parser output into IR blocks.

- `chunkflow/chunkers/base.py`
  - Chunker interface and `ChunkerConfig`.

- `chunkflow/chunkers/generic_structured.py`
  - Generic structure-aware parent-child chunker.

- `chunkflow/chunkers/contract_terms.py`
  - Phase 1 contract/insurance chunker. It currently reuses generic behavior but exposes a stable template name for future contract-specific rules.

- `chunkflow/chunkers/registry.py`
  - Template lookup and template list.

- `chunkflow/postprocess/media_context.py`
  - Adds same-section before/after text context for table/figure/caption chunks.

- `chunkflow/postprocess/quality.py`
  - Adds basic metrics to `parse_report.metrics`.

- `test/test_phase1_ir_chunking.py`
  - Synthetic unit test for Phase 1 parent-child output and table context.

## Files Modified

- `chunkflow/app.py`
  - Uses the new pipeline.
  - Adds `template`, `child_max_tokens`, `child_min_tokens`, `parent_granularity`, `table_context_blocks`, `image_context_blocks`, and `include_blocks` query parameters.
  - Adds `GET /api/templates`.
  - Extends `GET /api/status` with parser availability and template list.

- `static/app.js`
  - Renders `child_chunks` and supports the new `page_span`, `heading_path`, `chunk_type`, and `token_count` fields.

## New API Shape

`POST /api/parse` now returns:

```json
{
  "document_id": "...",
  "document_type": "contract_terms",
  "parser_used": "docling",
  "chunker_used": "contract_terms",
  "parent_chunk_count": 1,
  "child_chunk_count": 10,
  "parent_chunks": [],
  "child_chunks": [],
  "blocks": [],
  "parse_report": {
    "page_count": 1,
    "block_count": 10,
    "table_count": 1,
    "figure_count": 0,
    "warnings": [],
    "metrics": {}
  },
  "warnings": [],
  "metadata": {
    "filename": "sample.pdf",
    "file_type": "pdf",
    "parser_fallback_chain": ["docling"],
    "section_count": 1
  }
}
```

Each `ChildChunk` includes:

- `chunk_id`
- `parent_id`
- `chunk_type`
- `template`
- `text`
- `page_span`
- `source_block_ids`
- `bbox_refs`
- `heading_path`
- `context_before`
- `context_after`
- `token_count`
- `metadata`

## Design Notes

1. The Docling and MinerU adapters are transitional.
   They currently normalize the existing legacy parser chunk dictionaries into IR `Block`s. Phase 2 should extract native parser blocks, bbox, captions, and layout objects directly instead of treating old chunks as blocks.

2. The `contract_terms` chunker intentionally has its own class now.
   It currently inherits generic behavior, but future work can add insurance-contract rules without changing API names or pipeline wiring.

3. Parent granularity is effectively top-level heading/chapter in Phase 1.
   The `parent_granularity` parameter is accepted by the API but only `chapter` is implemented.

4. Table/figure context is text-only.
   It uses same-section neighboring text blocks and skips headers, footers, page numbers, tables, and figures.

5. Citation is still only pre-wired.
   `source_block_ids`, `bbox_refs`, and `page_span` are present, but no answer-source matching or PDF screenshot/highlight pipeline exists.

## Verification

Passed:

```bash
wsl -e bash -lc "cd '/mnt/c/Users/wanghui/Desktop/工作空间2026/project/ChunkFlow' && python3 -m py_compile chunkflow/ir/models.py chunkflow/core/pipeline.py chunkflow/parsers/base.py chunkflow/parsers/utils.py chunkflow/parsers/docling_pdf.py chunkflow/parsers/mineru_pdf.py chunkflow/parsers/pypdf_fallback.py chunkflow/chunkers/base.py chunkflow/chunkers/generic_structured.py chunkflow/chunkers/contract_terms.py chunkflow/chunkers/registry.py chunkflow/postprocess/media_context.py chunkflow/postprocess/quality.py chunkflow/app.py"
```

Passed:

```bash
wsl -e bash -lc "cd '/mnt/c/Users/wanghui/Desktop/工作空间2026/project/ChunkFlow' && python3 -m unittest discover -s test -p 'test_phase1_ir_chunking.py'"
```

Passed after installing `pypdf` in the WSL user Python environment:

```bash
wsl -e bash -lc "cd '/mnt/c/Users/wanghui/Desktop/工作空间2026/project/ChunkFlow' && python3 -m unittest discover -s test"
```

```text
Ran 9 tests in 0.002s
OK
```

Note: the Windows shell still does not have a usable `python` command. Verification used WSL `python3`.

Passed pypdf pipeline smoke test on one local PDF fixture:

```text
parents: 41
children: 47
parser: pypdf
chunker: contract_terms
```

## Recommended Next Phase

Phase 2 should focus on true layout-aware parser adapters:

1. Update `DoclingPdfParser` to emit native page/block/table/figure objects with bbox when available.
2. Update `MinerUPdfParser` to preserve `content_list` bbox, captions, table HTML/markdown, and figure metadata directly in `Block`.
3. Normalize coordinate systems into `BBox`.
4. Add IR validator checks for page/block/bbox consistency.
5. Add tests using small parser-output fixtures rather than remote MinerU calls.
