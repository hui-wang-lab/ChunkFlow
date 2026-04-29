# Phase 3 Implementation Summary

Date: 2026-04-28

## Scope Completed

Phase 3 added the first real template-specific chunking behavior:

- Expanded `ContractTermsChunker` beyond generic chunking.
- Added `LawsChunker`.
- Added `PaperChunker`.
- Added `ManualChunker`.
- Added shared template chunker helpers.
- Updated template registry to route `contract_terms`, `laws`, `paper`, and `manual`.
- Rebuilt document type detection with clean UTF-8/ASCII-safe keyword checks.
- Added synthetic IR tests for all Phase 3 templates.

## Important Files Added

- `chunkflow/chunkers/template_utils.py`
  - Shared helpers for ordering blocks, creating parent chunks, creating child chunks, inferring media/text chunk types, computing page spans, preserving bbox refs, and estimating tokens.

- `chunkflow/chunkers/laws.py`
  - Laws/regulation chunker.
  - Parent groups are chapter/section-like groups.
  - Child chunks are legal articles.
  - Legal item/list continuations stay attached to the current article.
  - Tables/figures are independent child chunks.

- `chunkflow/chunkers/paper.py`
  - Academic paper chunker.
  - Preserves `Abstract` as a complete `paper_abstract` child chunk.
  - Preserves `References` as `paper_references`.
  - Uses section-level parent chunks.
  - Tables/figures stay independent.

- `chunkflow/chunkers/manual.py`
  - Technical manual chunker.
  - Preserves warning/caution/note callouts.
  - Groups ordered/list steps into `manual_procedure`.
  - Marks troubleshooting tables as `manual_troubleshooting_table`.
  - Tables/figures stay independent.

- `test/test_phase3_template_chunkers.py`
  - Fixture tests for contract terms, laws, paper, manual, registry routing, and document type detection.

## Files Modified

- `chunkflow/chunkers/contract_terms.py`
  - Now creates chapter/section-like parent groups.
  - Creates `contract_clause` child chunks from article/clause groups.
  - Keeps table/figure/caption chunks independent.
  - Keeps list-item continuations attached to the current article instead of misclassifying numeric list markers as new articles.
  - Falls back to parser `heading_path` changes when explicit chapter headings are unavailable.

- `chunkflow/chunkers/registry.py`
  - Routes:
    - `contract_terms` -> `ContractTermsChunker`
    - `laws` -> `LawsChunker`
    - `paper` -> `PaperChunker`
    - `manual` -> `ManualChunker`
  - Other templates still fall back to `GenericStructuredChunker`.

- `chunkflow/core/document_type.py`
  - Rewritten to avoid mojibake keyword literals.
  - Uses Unicode escape literals for Chinese keywords.
  - Adds English keyword signals for contract/policy, laws/regulation, paper, and manuals.

## Template Behavior

### ContractTermsChunker

Parent:

- Explicit chapter headings like `Chapter 1` or Chinese `第...章`.
- Parser `heading_path` changes as fallback when chapter headings are missing.
- If the document begins directly with an article, that article becomes the fallback parent.

Child:

- `contract_clause` for article/clause text.
- `table` / `figure` / `caption` remain independent.
- Numeric list items like `1. Death benefit...` are treated as clause continuations, not new articles.

### LawsChunker

Parent:

- Chapter/section headings.

Child:

- `legal_article` chunks.
- Article numbers stay attached to article text.
- Item/list continuations stay attached to the article.

### PaperChunker

Parent:

- Paper sections.

Child:

- `paper_abstract`
- `paper_text`
- `paper_references`
- independent media chunks.

### ManualChunker

Parent:

- Manual headings/sections.

Child:

- `manual_text`
- `manual_callout`
- `manual_procedure`
- `manual_troubleshooting_table`
- independent media chunks.

## Verification

Passed compile check:

```bash
wsl -e bash -lc "cd '/mnt/c/Users/wanghui/Desktop/工作空间2026/project/ChunkFlow' && python3 -m py_compile chunkflow/chunkers/template_utils.py chunkflow/chunkers/contract_terms.py chunkflow/chunkers/laws.py chunkflow/chunkers/paper.py chunkflow/chunkers/manual.py chunkflow/chunkers/registry.py chunkflow/core/document_type.py test/test_phase3_template_chunkers.py"
```

Passed Phase 3 tests:

```bash
wsl -e bash -lc "cd '/mnt/c/Users/wanghui/Desktop/工作空间2026/project/ChunkFlow' && python3 -m unittest discover -s test -p 'test_phase3_template_chunkers.py'"
```

```text
Ran 5 tests
OK
```

Passed full test suite:

```bash
wsl -e bash -lc "cd '/mnt/c/Users/wanghui/Desktop/工作空间2026/project/ChunkFlow' && python3 -m unittest discover -s test"
```

```text
Ran 17 tests
OK
```

Passed local PDF smoke test with forced contract template:

```text
parents: 8
children: 48
warnings: 0
parser: pypdf
chunker: contract_terms
types: ["contract_clause"]
```

Note: verification used WSL `python3`.

## Known Limitations

1. `book`, `table_data`, `picture_pdf`, and `qa` still fall back to `GenericStructuredChunker`.
2. Contract/laws Chinese structure matching is implemented, but real OCR/parser output may still be affected by garbled text from low-quality extraction.
3. Oversized single source blocks are not split inside template chunkers.
4. Paper front matter handling is simple; author/affiliation/email extraction is not implemented.
5. Manual procedure grouping treats contiguous list/step blocks as one procedure, but does not yet parse nested step trees.

## Recommended Next Phase

Phase 4 should cover the remaining templates:

1. `book`
   - chapter parent chunks
   - section child chunks
   - optional TOC/index handling

2. `table_data`
   - Excel/CSV parser support
   - sheet/table parents
   - row group child chunks with column names

3. `picture_pdf`
   - page-level parent chunks
   - OCR block child chunks
   - image/caption text-only chunks

4. `qa`
   - Q/A pair extraction
   - category/section parents
   - metadata fields for question and answer.

