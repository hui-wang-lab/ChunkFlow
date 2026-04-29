# Chunk Quality PDF Samples

Generated files for validating chunking across four common PDF layouts. All files are under five pages.

| File | Category | Expected pages | Notes |
| --- | --- | ---: | --- |
| 01_plain_text.pdf | plain text | 3 | Narrative paragraphs for semantic chunking checks |
| 02_hierarchical_headings.pdf | hierarchical headings | 3 | H1/H2/H3 structure for heading-aware splitting |
| 03_table_dense.pdf | table-dense | 3 | Multi-page tables with wrapped cells |
| 04_scanned_image_only.pdf | image / scan / OCR | 3 | Image-only pages with scan-like noise; suitable for OCR-path validation |

## Quick verification

- 01_plain_text.pdf: 3 page(s); extracted text lengths per page = [1283, 1007, 1066]
- 02_hierarchical_headings.pdf: 3 page(s); extracted text lengths per page = [1018, 802, 492]
- 03_table_dense.pdf: 3 page(s); extracted text lengths per page = [798, 1070, 513]
- 04_scanned_image_only.pdf: 3 page(s); extracted text lengths per page = [0, 0, 0]