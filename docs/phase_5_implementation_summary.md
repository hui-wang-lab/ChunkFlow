# Phase 5 Implementation Summary

Date: 2026-04-28

## Scope Completed

Phase 5 added observability, stable regression snapshots, and UI quality summaries:

- Added optional debug payloads to `ChunkPackage`.
- Added `debug=true` support to `/api/parse`.
- Expanded quality metrics.
- Added stable package snapshots for golden tests.
- Added fixture inputs and generated golden JSON summaries.
- Added a golden fixture generation script.
- Added frontend quality/warnings/metrics summary panel.
- Added Phase 5 tests for debug output, metrics, and golden snapshot regression.

## Important Files Added

- `chunkflow/core/debug.py`
  - Builds optional debug payloads with:
    - `section_tree`
    - `block_summary`
    - `chunk_summary`
    - `parent_child_graph`
    - `orphan_child_ids`
    - `warnings`

- `chunkflow/core/snapshot.py`
  - Builds stable, ID-light summaries for golden regression tests.
  - Avoids random paths and full IDs so fixture output stays readable.

- `scripts/generate_golden_fixtures.py`
  - Regenerates golden JSON snapshots from fixture inputs.
  - Run from repository root:

```bash
python -m scripts.generate_golden_fixtures
```

- `test/fixtures/phase5_table.csv`
  - CSV fixture for `table_file -> table_data`.

- `test/fixtures/phase5_qa.md`
  - Markdown fixture for `text_file -> qa`.

- `test/fixtures/golden/csv_table_data.json`
  - Golden snapshot for CSV table data.

- `test/fixtures/golden/markdown_qa.json`
  - Golden snapshot for Markdown QA.

- `test/test_phase5_observability.py`
  - Tests debug payloads, metrics, and golden snapshot equality.

## Files Modified

- `chunkflow/ir/models.py`
  - `ChunkPackage` now has a `debug` field.
  - `ChunkPackage.to_dict(...)` accepts `include_debug`.

- `chunkflow/core/pipeline.py`
  - `PipelineConfig` now has `include_debug`.
  - Adds chunker config metadata for metrics.
  - Builds debug payloads when requested.

- `chunkflow/postprocess/quality.py`
  - Adds:
    - `chunks_with_bbox_refs_count`
    - `over_max_token_child_count`
    - `parent_child_edge_count`
    - `block_type_counts`
    - `child_type_counts`
    - `figure_context_coverage`
    - `max_tokens_per_child`
    - `min_tokens_per_child`

- `chunkflow/app.py`
  - Adds `debug` query parameter.
  - Passes `include_debug` to the pipeline and response serializer.

- `static/index.html`
  - Adds `qualityPanel`.

- `static/style.css`
  - Adds quality panel styling.

- `static/app.js`
  - Renders quality metrics and warnings above the chunk list.

## API Debug Behavior

Default response remains compact:

```text
POST /api/parse
```

Debug response:

```text
POST /api/parse?debug=true
```

Adds:

```json
{
  "debug": {
    "section_tree": [],
    "block_summary": {},
    "chunk_summary": {},
    "parent_child_graph": [],
    "orphan_child_ids": [],
    "warnings": []
  }
}
```

`include_blocks=false` and `debug=true` can be combined when only graph/debug metadata is needed.

## Golden Snapshot Behavior

Golden snapshots intentionally compare stable summaries, not full package JSON. They include:

- parser/chunker/document type
- parent/child/block/warning counts
- parse report counts
- key quality metrics
- parent titles and child counts
- child chunk type, heading path, token count, metadata keys, and text preview

This catches meaningful chunking regressions without failing on deterministic but noisy IDs.

## Verification

Passed compile check:

```bash
wsl -e bash -lc "cd '/mnt/c/Users/wanghui/Desktop/工作空间2026/project/ChunkFlow' && python3 -m py_compile chunkflow/core/debug.py chunkflow/core/snapshot.py chunkflow/postprocess/quality.py chunkflow/ir/models.py chunkflow/core/pipeline.py chunkflow/app.py test/test_phase5_observability.py scripts/generate_golden_fixtures.py"
```

Passed Phase 5 tests:

```bash
wsl -e bash -lc "cd '/mnt/c/Users/wanghui/Desktop/工作空间2026/project/ChunkFlow' && python3 -m unittest discover -s test -p 'test_phase5_observability.py'"
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
Ran 27 tests
OK
```

Passed debug pipeline smoke test:

```text
parser: text_file
chunker: qa
children: 2
debug_keys: block_summary, chunk_summary, orphan_child_ids, parent_child_graph, section_tree, warnings
```

Note: verification used WSL `python3`.

## Known Limitations

1. Golden fixtures currently cover CSV table data and Markdown QA only.
2. PDF golden fixtures are not yet added because local parser output can vary by parser availability and OCR/parser dependencies.
3. Frontend quality panel is summary-only; it does not yet provide a separate parent/source-block drill-down view.
4. Debug payload is returned inline; for very large documents a future streaming or artifact mode may be better.

## Recommended Next Work

1. Add parser-stable PDF golden fixtures using synthetic parser outputs or small bundled PDFs with pinned parser paths.
2. Add a CLI command around `parse_to_chunk_package` for local debugging and golden generation.
3. Add frontend tabs for:
   - child chunks
   - parent chunks
   - source blocks
   - debug graph
4. Add threshold-based quality gates for CI, for example:
   - no orphan children
   - no chunks without source blocks
   - table context coverage above a configured minimum
5. Add benchmark fixtures to track parser/chunker runtime for larger documents.

