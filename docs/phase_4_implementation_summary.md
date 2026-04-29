# Phase 4 Implementation Summary

Date: 2026-04-28

## Scope Completed

Phase 4 completed the remaining template chunkers and added lightweight non-PDF parsing:

- Added `BookChunker`.
- Added `TableDataChunker`.
- Added `PicturePdfChunker`.
- Added `QAChunker`.
- Added `TableFileParser` for CSV/TSV and optional XLSX/XLSM.
- Added `TextFileParser` for TXT/Markdown.
- Updated parser routing so non-PDF files are automatically sent to table/text parsers.
- Updated `/api/parse` to accept PDF, CSV, TSV, XLSX, XLSM, TXT, MD, and Markdown.
- Updated the frontend file picker and parser list for table/text files.
- Added Phase 4 tests for templates, parsers, registry routing, detection, and CSV pipeline parsing.

## Important Files Added

- `chunkflow/chunkers/book.py`
  - Uses chapter-like parent chunks.
  - Skips obvious `Contents` / `Table of Contents` / `Index` headings.
  - Emits `book_section` child chunks.
  - Keeps tables/figures independent.

- `chunkflow/chunkers/table_data.py`
  - Groups rows by sheet/table parent.
  - Emits `table_row_group` child chunks.
  - Preserves row range, columns, and sheet name in metadata.

- `chunkflow/chunkers/picture_pdf.py`
  - Groups content by page parent.
  - Emits `ocr_text` child chunks for OCR/text blocks.
  - Emits `image_context` child chunks for figure/table/caption-like media.

- `chunkflow/chunkers/qa.py`
  - Groups content by QA category/heading parent.
  - Emits one `qa_pair` child per question-answer pair.
  - Preserves `question` and `answer` in metadata.

- `chunkflow/parsers/table_file.py`
  - Parses `.csv` and `.tsv` with the standard library.
  - Parses `.xlsx` and `.xlsm` when optional `openpyxl` is installed.
  - Emits one table block per non-empty row.
  - Preserves `sheet_name`, `row_index`, `columns`, and `row` metadata.

- `chunkflow/parsers/text_file.py`
  - Parses `.txt`, `.md`, and `.markdown`.
  - Emits heading, paragraph, and list-item blocks.
  - Supports Markdown headings.

- `test/test_phase4_templates_and_parsers.py`
  - Covers book/table/picture/QA templates.
  - Covers CSV parser and CSV pipeline.
  - Covers TXT/Markdown parser detection.
  - Covers registry routing for Phase 4 templates.

## Files Modified

- `chunkflow/chunkers/registry.py`
  - Routes:
    - `book` -> `BookChunker`
    - `table_data` -> `TableDataChunker`
    - `picture_pdf` -> `PicturePdfChunker`
    - `qa` -> `QAChunker`

- `chunkflow/core/pipeline.py`
  - Adds `TableFileParser` and `TextFileParser`.
  - `auto` parser now routes by suffix:
    - `.csv`, `.tsv`, `.xlsx`, `.xlsm` -> `table_file`
    - `.txt`, `.md`, `.markdown` -> `text_file`
    - PDF -> Docling/MinerU/pypdf priority

- `chunkflow/core/document_type.py`
  - Honors parser-provided `document.document_type`.
  - Adds book and QA detection signals.

- `chunkflow/app.py`
  - Allows `parser=table_file` and `parser=text_file`.
  - Allows non-PDF upload extensions.

- `static/index.html`
  - File picker now accepts PDF, CSV, TSV, XLSX, TXT, and Markdown.
  - Parser dropdown includes table/text parser options.

- `static/app.js`
  - Client-side file extension validation updated for new supported types.
  - Parser labels include `table_file` and `text_file`.

## Template Behavior

### BookChunker

Parent:

- Chapter/part/appendix-like groups.

Child:

- `book_section`
- independent table/figure/caption chunks.

### TableDataChunker

Parent:

- Sheet/table name.

Child:

- `table_row_group`
- Metadata includes `row_start`, `row_end`, `columns`, and `sheet_name`.

### PicturePdfChunker

Parent:

- Page.

Child:

- `ocr_text`
- `image_context`

### QAChunker

Parent:

- FAQ/category heading.

Child:

- `qa_pair`
- Metadata includes `question` and `answer`.

## Verification

Passed compile check:

```bash
wsl -e bash -lc "cd '/mnt/c/Users/wanghui/Desktop/工作空间2026/project/ChunkFlow' && python3 -m py_compile chunkflow/chunkers/book.py chunkflow/chunkers/table_data.py chunkflow/chunkers/picture_pdf.py chunkflow/chunkers/qa.py chunkflow/parsers/table_file.py chunkflow/parsers/text_file.py chunkflow/core/pipeline.py chunkflow/app.py test/test_phase4_templates_and_parsers.py"
```

Passed Phase 4 tests:

```bash
wsl -e bash -lc "cd '/mnt/c/Users/wanghui/Desktop/工作空间2026/project/ChunkFlow' && python3 -m unittest discover -s test -p 'test_phase4_templates_and_parsers.py'"
```

```text
Ran 7 tests
OK
```

Passed full test suite:

```bash
wsl -e bash -lc "cd '/mnt/c/Users/wanghui/Desktop/工作空间2026/project/ChunkFlow' && python3 -m unittest discover -s test"
```

```text
Ran 24 tests
OK
```

Passed CSV and Markdown pipeline smoke tests:

```text
csv_parser: table_file
csv_chunker: table_data
csv_children: 1

md_parser: text_file
md_chunker: qa
md_children: 1
md_type: qa
```

Passed PDF regression smoke test:

```text
parents: 8
children: 48
warnings: 0
parser: pypdf
chunker: contract_terms
```

Note: verification used WSL `python3`.

## Known Limitations

1. XLSX/XLSM parsing requires optional `openpyxl`; it is not added as a required dependency.
2. `.xls` is not supported.
3. Table parser treats the first non-empty row as the header row.
4. Book TOC/index handling is heuristic and only skips obvious headings, not full TOC ranges.
5. QA extraction expects explicit Q/A markers.
6. Picture PDF behavior depends on parser/OCR blocks already existing in IR; this phase does not add OCR itself.

## Recommended Next Phase

Phase 5 should focus on quality, observability, and regression assets:

1. Add golden JSON fixtures per document type.
2. Add CLI or API debug modes for:
   - parsed blocks
   - section tree
   - parent-child graph
   - parser warnings
3. Add quality dashboards/metrics:
   - orphan child count
   - over-token child count
   - table context coverage
   - chunks without source blocks
4. Add front-end views for:
   - parent chunks
   - child chunks
   - source blocks
   - warnings/metrics
5. Add end-to-end parse tests for sample PDF, CSV, Markdown, and fixture-generated synthetic docs.

