"""FastAPI application: file upload, parsing, and chunk viewing."""
from __future__ import annotations

import logging
import os
import tempfile
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, UploadFile, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from chunkflow.chunkers.registry import available_templates
from chunkflow.core.pipeline import PipelineConfig, available_parsers, configured_parser_priority, parse_to_chunk_package

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("chunkflow.app")

app = FastAPI(title="ChunkFlow", description="Document parsing and chunking service")

STATIC_DIR = Path(__file__).parent.parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

UPLOAD_DIR = Path(tempfile.gettempdir()) / "chunkflow_uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@app.get("/", response_class=HTMLResponse)
async def index():
    index_file = STATIC_DIR / "index.html"
    return HTMLResponse(content=index_file.read_text(encoding="utf-8"))


@app.get("/api/status")
async def status():
    parser_status = available_parsers()
    priority = configured_parser_priority("auto")
    parser = "pypdf"
    for candidate in priority:
        if parser_status.get(candidate):
            parser = candidate
            break
    return {
        "service": "ChunkFlow",
        "parsers": parser_status,
        "mineru_available": parser_status.get("mineru", False),
        "docling_available": parser_status.get("docling", False),
        "parser": parser,
        "parser_priority": priority,
        "templates": available_templates(),
    }


@app.get("/api/templates")
async def templates():
    return {
        "templates": available_templates(),
        "default": "auto",
    }


@app.post("/api/parse")
async def parse_file(
    file: UploadFile = File(...),
    parser: str = Query("auto", pattern="^(auto|docling|mineru|pypdf|table_file|text_file)$"),
    template: str = Query(
        "auto",
        pattern="^(auto|contract_terms|paper|book|manual|laws|table_data|picture_pdf|qa|generic_structured)$",
    ),
    max_tokens: int = Query(400, ge=50, le=2000),
    chunk_size_tokens: int = Query(400, ge=50, le=2000),
    overlap_tokens: int = Query(100, ge=0, le=500),
    min_chunk_tokens: int = Query(50, ge=0, le=500),
    child_max_tokens: int = Query(450, ge=50, le=3000),
    child_min_tokens: int = Query(80, ge=0, le=500),
    parent_granularity: str = Query("chapter", pattern="^(chapter|section)$"),
    table_context_blocks: int = Query(2, ge=0, le=10),
    image_context_blocks: int = Query(2, ge=0, le=10),
    include_blocks: bool = Query(True),
    debug: bool = Query(False),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    suffix = Path(file.filename).suffix.lower()
    allowed_suffixes = {".pdf", ".csv", ".tsv", ".xlsx", ".xlsm", ".txt", ".md", ".markdown"}
    if suffix not in allowed_suffixes:
        raise HTTPException(
            status_code=400,
            detail="Supported files: PDF, CSV, TSV, XLSX, TXT, Markdown",
        )

    unique_name = f"{uuid.uuid4().hex}{suffix}"
    save_path = UPLOAD_DIR / unique_name

    try:
        content = await file.read()
        save_path.write_bytes(content)

        logger.info("Parsing %s (%d bytes) ...", file.filename, len(content))
        package = parse_to_chunk_package(
            str(save_path),
            PipelineConfig(
                parser=parser,
                template=template,
                max_tokens=max_tokens,
                chunk_size_tokens=chunk_size_tokens,
                overlap_tokens=overlap_tokens,
                min_chunk_tokens=min_chunk_tokens,
                child_max_tokens=child_max_tokens,
                child_min_tokens=child_min_tokens,
                parent_granularity=parent_granularity,
                table_context_blocks=table_context_blocks,
                image_context_blocks=image_context_blocks,
                include_blocks=include_blocks,
                include_debug=debug,
            ),
        )

        result = package.to_dict(include_blocks=include_blocks, include_debug=debug)
        result["filename"] = file.filename
        result["file_size_bytes"] = len(content)
        result["parser_requested"] = parser
        result["template_requested"] = template
        result["quality_monitor"] = _build_quality_monitor(
            package=package,
            filename=file.filename,
            file_size_bytes=len(content),
            parser_requested=parser,
            template_requested=template,
        )

        return JSONResponse(content=result)

    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("Parse failed for %s", file.filename)
        raise HTTPException(status_code=500, detail=f"Parse failed: {e}")
    finally:
        if save_path.exists():
            os.unlink(save_path)


def main():
    import uvicorn
    uvicorn.run("chunkflow.app:app", host="0.0.0.0", port=8900, reload=True)


def _build_quality_monitor(
    *,
    package,
    filename: str,
    file_size_bytes: int,
    parser_requested: str,
    template_requested: str,
) -> dict[str, Any]:
    """Build a compact execution trace and quality diagnosis payload for the UI."""
    metrics = package.parse_report.metrics or {}
    detection = package.metadata.get("document_type_detection") or {}
    warnings = list(package.warnings or [])
    parser_chain = package.metadata.get("parser_fallback_chain") or package.parser_used

    health_checks = [
        _health_check(
            "parser",
            "Parser completed",
            bool(package.parser_used),
            f"Used {package.parser_used}",
            "No parser result was recorded.",
        ),
        _health_check(
            "blocks",
            "Blocks extracted",
            package.parse_report.block_count > 0,
            f"{package.parse_report.block_count} blocks",
            "No blocks were extracted; check parser availability or file readability.",
        ),
        _health_check(
            "sections",
            "Sections detected",
            bool(package.metadata.get("section_count", 0)),
            f"{package.metadata.get('section_count', 0)} sections",
            "No section tree was detected; heading rules may need tuning.",
        ),
        _health_check(
            "sources",
            "Chunks have source blocks",
            int(metrics.get("chunks_without_source_block_count") or 0) == 0,
            "All chunks have source blocks",
            f"{metrics.get('chunks_without_source_block_count', 0)} chunks have no source block.",
        ),
        _health_check(
            "tokens",
            "Token budget respected",
            int(metrics.get("over_max_token_child_count") or 0) == 0,
            "No child chunk exceeds the configured limit",
            f"{metrics.get('over_max_token_child_count', 0)} child chunks exceed the configured limit.",
        ),
        _health_check(
            "relations",
            "Parent-child links valid",
            int(metrics.get("orphan_child_count") or 0) == 0,
            "No orphan child chunks",
            f"{metrics.get('orphan_child_count', 0)} child chunks do not map to a parent.",
        ),
    ]

    warning_groups = _warning_groups(warnings)
    return {
        "summary": {
            "filename": filename,
            "file_size_bytes": file_size_bytes,
            "document_type": package.document_type,
            "parser_requested": parser_requested,
            "parser_used": package.parser_used,
            "chunker_used": package.chunker_used,
            "template_requested": template_requested,
            "page_count": package.parse_report.page_count,
            "block_count": package.parse_report.block_count,
            "parent_count": len(package.parent_chunks),
            "child_count": len(package.child_chunks),
            "warning_count": len(warnings),
        },
        "execution_chain": [
            {
                "stage": "upload",
                "status": "ok",
                "detail": f"{filename} ({file_size_bytes} bytes)",
            },
            {
                "stage": "parse",
                "status": "ok" if package.parse_report.block_count else "warning",
                "detail": f"requested={parser_requested}, used={package.parser_used}",
                "fallback_chain": parser_chain,
            },
            {
                "stage": "normalize",
                "status": "ok",
                "detail": (
                    f"layout_noise_removed={package.metadata.get('layout_noise_removed_count', 0)}, "
                    f"sections={package.metadata.get('section_count', 0)}"
                ),
            },
            {
                "stage": "detect_type",
                "status": "ok" if detection.get("confidence", 0) >= 0.5 else "warning",
                "detail": (
                    f"type={package.document_type}, confidence={detection.get('confidence', '-')}, "
                    f"signals={', '.join(detection.get('signals') or []) or '-'}"
                ),
            },
            {
                "stage": "chunk",
                "status": "ok" if package.child_chunks else "warning",
                "detail": f"chunker={package.chunker_used}, parents={len(package.parent_chunks)}, children={len(package.child_chunks)}",
            },
            {
                "stage": "postprocess",
                "status": "warning" if warning_groups else "ok",
                "detail": f"warnings={len(warnings)}, repairs={metrics.get('boundary_repair_count', 0)}",
            },
        ],
        "health_checks": health_checks,
        "metrics": {
            key: metrics.get(key)
            for key in (
                "avg_tokens_per_child",
                "max_tokens_per_child",
                "min_tokens_per_child",
                "over_max_token_child_count",
                "split_overlong_child_count",
                "chunks_without_source_block_count",
                "orphan_child_count",
                "chunks_with_bbox_refs_count",
                "table_context_coverage",
                "figure_context_coverage",
                "layout_noise_removed_count",
                "inferred_heading_count",
                "boundary_repair_count",
            )
        },
        "distributions": {
            "block_type_counts": metrics.get("block_type_counts") or {},
            "child_type_counts": metrics.get("child_type_counts") or {},
            "heading_level_counts": metrics.get("heading_level_counts") or {},
            "media_context_strategy_counts": metrics.get("media_context_strategy_counts") or {},
        },
        "warning_groups": warning_groups,
        "risk_samples": _risk_samples(package),
        "suggested_checks": _suggested_checks(metrics, warning_groups, package),
    }


def _health_check(name: str, label: str, ok: bool, ok_detail: str, fail_detail: str) -> dict[str, str]:
    return {
        "name": name,
        "label": label,
        "status": "ok" if ok else "warning",
        "detail": ok_detail if ok else fail_detail,
    }


def _warning_groups(warnings: list[str]) -> list[dict[str, Any]]:
    counts: Counter[str] = Counter()
    examples: dict[str, list[str]] = {}
    for warning in warnings:
        group = "general"
        if warning.startswith("[") and "]" in warning:
            group = warning[1: warning.index("]")]
        elif "Parser " in warning:
            group = "parser"
        counts[group] += 1
        examples.setdefault(group, [])
        if len(examples[group]) < 3:
            examples[group].append(warning)
    return [
        {"group": group, "count": count, "examples": examples.get(group, [])}
        for group, count in counts.most_common()
    ]


def _risk_samples(package) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    children = list(package.child_chunks or [])
    if not children:
        return samples

    for child in children:
        reasons: list[str] = []
        if not child.source_block_ids:
            reasons.append("missing_source")
        if child.metadata.get("overlong_split"):
            reasons.append("overlong_split")
        if child.token_count == 0:
            reasons.append("empty_tokens")
        if child.text[:1] in ",.;:!?，。；：！？、":
            reasons.append("starts_with_punctuation")
        if reasons:
            samples.append(_chunk_sample(child, reasons))
        if len(samples) >= 5:
            return samples

    for child in sorted(children, key=lambda item: item.token_count, reverse=True)[:3]:
        if all(sample["chunk_id"] != child.chunk_id for sample in samples):
            samples.append(_chunk_sample(child, ["largest_chunk"]))
    return samples[:5]


def _chunk_sample(child, reasons: list[str]) -> dict[str, Any]:
    return {
        "chunk_id": child.chunk_id,
        "chunk_type": child.chunk_type,
        "page_span": list(child.page_span),
        "token_count": child.token_count,
        "reasons": reasons,
        "heading_path": list(child.heading_path),
        "text_preview": child.text[:240],
    }


def _suggested_checks(metrics: dict[str, Any], warning_groups: list[dict[str, Any]], package) -> list[str]:
    suggestions: list[str] = []
    if not package.parse_report.block_count:
        suggestions.append("Parser produced no blocks; try a different parser or inspect parser availability.")
    if int(metrics.get("inferred_heading_count") or 0) == 0 and package.document_type not in {"table_data", "qa"}:
        suggestions.append("Few or no inferred headings; add heading patterns for this document style if chunks look too broad.")
    if int(metrics.get("over_max_token_child_count") or 0) > 0:
        suggestions.append("Some chunks exceed the token budget; tune child_max_tokens or improve section boundaries.")
    if int(metrics.get("chunks_without_source_block_count") or 0) > 0:
        suggestions.append("Chunks without source blocks indicate a chunker bug or missing source propagation.")
    if any(group["group"] == "boundary_repair" for group in warning_groups):
        suggestions.append("Boundary repair fired; inspect cross-page chunks and consider layout/header cleanup rules.")
    if not suggestions:
        suggestions.append("No high-priority quality issue detected; inspect sample chunks for semantic completeness.")
    return suggestions


if __name__ == "__main__":
    main()
