"""
Unified chunking pipeline: Docling (preferred) with pypdf paragraph-aware fallback.

Post-processing merges small "orphan" tail chunks back into their section
neighbours so that a single logical section is not split across many chunks.
"""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Optional

from pypdf import PdfReader

from chunkflow.schema import (
    Chunk,
    ChunkingConfig,
    Document,
    chunk_id_from_components,
    chunk_key,
    document_id_from_bytes,
)
from chunkflow.tokenizer import simple_tokenize, estimate_tokens
from chunkflow.docling_parser import is_docling_available, parse_pdf_with_docling
from chunkflow.mineru_parser import is_mineru_available, parse_pdf_with_mineru
from chunkflow.pdf_parser import (
    extract_metadata_from_page_text,
    PageMetadata,
    clean_page_texts,
    clean_chunk_text,
    join_pages_smart,
)

logger = logging.getLogger("chunkflow.chunking")

DEFAULT_PARSER_PRIORITY = ("mineru", "docling", "pypdf")

_PARAGRAPH_SEP_RE = re.compile(r"\n\s*\n")

_CJK_RANGES = "\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff"
_CJK_BARE_END_RE = re.compile(f"[{_CJK_RANGES}]$")
_CN_PUNCT_START_RE = re.compile(r"^[，、；：。！？…—）)》」』\]】]")


_WEAK_CONTINUATION_END_RE = re.compile(r"[:：;；、,，]$")
_STRONG_SENTENCE_END_RE = re.compile(r"[。！？!?]$")
_CN_HEADING_RE = re.compile(r"^第[一二三四五六七八九十百千万零〇\d]+[章节条]")
_EN_HEADING_RE = re.compile(r"^(?:Chapter|Section)\s+\d+", re.IGNORECASE)
_NUMERIC_HEADING_RE = re.compile(r"^\d+\.")
_LIST_MARKER_RE = re.compile(
    r"^(?:[-*]\s*)?(?:"
    r"[（(]?\d+[）).、]"
    r"|[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳]"
    r"|[A-Za-z][.)、]"
    r"|[一二三四五六七八九十百千万]+[、.]"
    r")"
)
_ISOLATED_NUMERIC_LINE_RE = re.compile(r"^\d{4,8}$")


# ---------------------------------------------------------------------------
# Post-processing: repair cross-page broken boundaries
# ---------------------------------------------------------------------------

def _content_type_name(content_type: object) -> str:
    value = getattr(content_type, "value", content_type)
    return str(value).lower() if value is not None else ""


def _boundary_line(text: str, *, from_end: bool) -> str:
    lines = text.splitlines()
    iterable = reversed(lines) if from_end else lines
    for line in iterable:
        stripped = line.strip()
        if not stripped:
            continue
        if _ISOLATED_NUMERIC_LINE_RE.fullmatch(stripped):
            continue
        return stripped
    return ""


def _first_content_line(chunk: Chunk) -> str:
    skip_lines = {
        line.strip()
        for line in [chunk.chapter, chunk.section, *chunk.headings]
        if isinstance(line, str) and line.strip()
    }
    for line in chunk.text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if _ISOLATED_NUMERIC_LINE_RE.fullmatch(stripped):
            continue
        if stripped in skip_lines:
            continue
        return stripped
    return ""


def _is_anchor_section(chunk: Chunk) -> bool:
    section = (chunk.section or "").strip()
    if not section:
        return False
    if _CN_HEADING_RE.match(section) or _EN_HEADING_RE.match(section):
        return True
    return bool(
        _NUMERIC_HEADING_RE.match(section)
        and _content_type_name(chunk.content_type) != "list_item"
    )


def _starts_like_continuation(chunk: Chunk) -> bool:
    section = (chunk.section or "").strip()
    first_line = _boundary_line(chunk.text, from_end=False)
    first_content_line = _first_content_line(chunk)
    content_type = _content_type_name(chunk.content_type)

    if content_type == "list_item":
        return True
    if _LIST_MARKER_RE.match(section) or _LIST_MARKER_RE.match(first_line):
        return True
    if first_content_line and _LIST_MARKER_RE.match(first_content_line):
        return True
    if first_content_line and not (
        _CN_HEADING_RE.match(first_content_line)
        or _EN_HEADING_RE.match(first_content_line)
        or _NUMERIC_HEADING_RE.match(first_content_line)
    ):
        return True
    return bool(section and not _is_anchor_section(chunk))


def _ends_with_continuation_signal(chunk: Chunk) -> bool:
    tail = _boundary_line(chunk.text, from_end=True)
    if not tail:
        return False
    if _WEAK_CONTINUATION_END_RE.search(tail):
        return True
    return bool(_LIST_MARKER_RE.match(tail) and not _STRONG_SENTENCE_END_RE.search(tail))


def _should_merge_structural_continuation(first: Chunk, second: Chunk) -> bool:
    if second.page_number < first.page_number or second.page_number - first.page_number > 1:
        return False
    if first.chapter and second.chapter and first.chapter != second.chapter:
        return False
    if not _ends_with_continuation_signal(first):
        return False
    if _same_section(first, second):
        return _starts_like_continuation(second)
    return _is_anchor_section(first) and _starts_like_continuation(second)


def _merge_structural_continuations(
    chunks: list[Chunk],
    max_tokens: int,
    overflow_ratio: float = 0.2,
) -> list[Chunk]:
    """Merge consecutive chunks that are clearly one logical paragraph/list.

    For high-confidence continuations, preserving paragraph integrity matters
    more than staying within the nominal token budget, so this pass allows
    oversize merges.
    """
    if len(chunks) <= 1:
        return chunks

    merged: list[Chunk] = []

    for chunk in chunks:
        if merged:
            prev = merged[-1]
            if _should_merge_structural_continuation(prev, chunk):
                merged[-1] = _combine_chunks(prev, chunk)
                logger.debug(
                    "Merged structural continuation: chunk %d into %d",
                    chunk.chunk_index, prev.chunk_index,
                )
                continue

        merged.append(chunk)

    return _reindex_chunks(merged)


def _repair_broken_boundaries(
    chunks: list[Chunk],
    max_tokens: int,
    overflow_ratio: float = 0.5,
) -> list[Chunk]:
    """Merge consecutive chunks where text is split mid-word or mid-sentence.

    Detection signals (any one triggers a merge):
      1. Previous chunk ends with a bare CJK character (no punctuation) — this
         almost never happens at a natural boundary in Chinese text.
      2. Current chunk starts with Chinese continuation punctuation (，、；etc.)
         — the punctuation belongs to the previous sentence.

    A generous *overflow_ratio* (default 50 %) is used because repairing
    broken text is more important than enforcing size limits.
    """
    if len(chunks) <= 1:
        return chunks

    hard_cap = int(max_tokens * (1 + overflow_ratio))
    merged: list[Chunk] = []

    for chunk in chunks:
        if merged:
            prev = merged[-1]
            prev_stripped = prev.text.rstrip()
            curr_stripped = chunk.text.lstrip()

            broken = (
                _CJK_BARE_END_RE.search(prev_stripped)
                or _CN_PUNCT_START_RE.match(curr_stripped)
            )
            if broken:
                combined_est = estimate_tokens(prev.text) + estimate_tokens(chunk.text)
                if combined_est <= hard_cap:
                    merged[-1] = _combine_chunks(prev, chunk)
                    logger.debug(
                        "Repaired broken boundary: merged chunk %d into %d",
                        chunk.chunk_index, prev.chunk_index,
                    )
                    continue

        merged.append(chunk)

    return _reindex_chunks(merged)


# ---------------------------------------------------------------------------
# Post-processing: merge small orphan chunks
# ---------------------------------------------------------------------------

def _merge_small_chunks(
    chunks: list[Chunk],
    min_chunk_tokens: int,
    max_tokens: int,
    overflow_ratio: float = 0.2,
) -> list[Chunk]:
    """Merge chunks that are too small into their same-section neighbour.

    Rules:
      1. A chunk with estimated tokens < *min_chunk_tokens* is considered an orphan.
      2. An orphan is merged with its **previous** neighbour when they share the
         same section heading (or both have no heading).
      3. Merging is allowed even if the result exceeds *max_tokens*, up to
         *max_tokens * (1 + overflow_ratio)*.
      4. If backward merge is not possible, try forward merge with the next chunk.
    """
    if min_chunk_tokens <= 0 or len(chunks) <= 1:
        return chunks

    hard_cap = int(max_tokens * (1 + overflow_ratio))

    merged: list[Chunk] = []
    skip_next: set[int] = set()

    for idx, chunk in enumerate(chunks):
        if idx in skip_next:
            continue

        est = estimate_tokens(chunk.text)
        if est >= min_chunk_tokens:
            merged.append(chunk)
            continue

        combined_backward = False
        if merged:
            prev = merged[-1]
            if _same_section(prev, chunk):
                combined_est = estimate_tokens(prev.text) + est
                if combined_est <= hard_cap:
                    merged[-1] = _combine_chunks(prev, chunk)
                    combined_backward = True

        if not combined_backward:
            next_idx = idx + 1
            if next_idx < len(chunks) and next_idx not in skip_next:
                nxt = chunks[next_idx]
                if _same_section(chunk, nxt):
                    combined_est = est + estimate_tokens(nxt.text)
                    if combined_est <= hard_cap:
                        merged.append(_combine_chunks(chunk, nxt))
                        skip_next.add(next_idx)
                        continue

            merged.append(chunk)

    return _reindex_chunks(merged)


def _same_section(a: Chunk, b: Chunk) -> bool:
    return a.section == b.section and a.chapter == b.chapter


def _strip_duplicate_heading(first_text: str, second_text: str) -> str:
    """Remove leading heading lines from *second_text* that duplicate
    the heading context already present at the start of *first_text*.

    Docling's ``contextualize()`` prepends the same heading hierarchy to
    every chunk in a section; when merging two such chunks the second
    copy must be stripped to avoid duplication.
    """
    first_lines = first_text.strip().splitlines()
    second_lines = second_text.strip().splitlines()

    if not first_lines or not second_lines:
        return second_text

    first_prefix: set[str] = set()
    for fl in first_lines:
        stripped = fl.strip()
        if not stripped:
            continue
        first_prefix.add(stripped)
        if len(first_prefix) >= 5:
            break

    skip = 0
    for sl in second_lines:
        stripped = sl.strip()
        if not stripped:
            skip += 1
            continue
        if stripped in first_prefix:
            skip += 1
        else:
            break

    if skip > 0:
        remaining = "\n".join(second_lines[skip:]).strip()
        if remaining:
            return remaining

    return second_text


def _combine_chunks(first: Chunk, second: Chunk) -> Chunk:
    second_text = _strip_duplicate_heading(first.text, second.text)
    separator = "\n" if first.text.endswith("\n") else "\n"
    combined_text = first.text + separator + second_text

    headings = list(first.headings)
    for h in second.headings:
        if h not in headings:
            headings.append(h)

    return Chunk(
        chunk_id=first.chunk_id,
        chunk_key=first.chunk_key,
        document_id=first.document_id,
        source_type=first.source_type,
        page_number=first.page_number,
        chunk_index=first.chunk_index,
        text=combined_text,
        chapter=first.chapter or second.chapter,
        section=first.section or second.section,
        domain_hint=first.domain_hint or second.domain_hint,
        headings=headings,
        content_type=first.content_type or second.content_type,
    )


def _reindex_chunks(chunks: list[Chunk]) -> list[Chunk]:
    """Re-generate chunk_index / chunk_id after merging."""
    result = []
    for new_idx, c in enumerate(chunks):
        cid = chunk_id_from_components(
            c.document_id, c.source_type, c.page_number, new_idx,
        )
        result.append(
            Chunk(
                chunk_id=cid,
                chunk_key=c.chunk_key,
                document_id=c.document_id,
                source_type=c.source_type,
                page_number=c.page_number,
                chunk_index=new_idx,
                text=c.text,
                chapter=c.chapter,
                section=c.section,
                domain_hint=c.domain_hint,
                headings=c.headings,
                content_type=c.content_type,
            )
        )
    return result


# ---------------------------------------------------------------------------
# Paragraph-aware chunking (fallback path)
# ---------------------------------------------------------------------------

def _token_offset_to_page(
    start_token_idx: int,
    page_token_offsets: list[tuple[int, int, int]],
) -> int:
    for page_num, start, end in page_token_offsets:
        if start <= start_token_idx < end:
            return page_num
    if page_token_offsets:
        return page_token_offsets[-1][0]
    return 1


def _char_offset_to_page(
    char_offset: int,
    page_char_offsets: list[tuple[int, int, int]],
) -> int:
    for page_num, start, end in page_char_offsets:
        if start <= char_offset < end:
            return page_num
    if page_char_offsets:
        return page_char_offsets[-1][0]
    return 1


def _paragraph_aware_chunks(
    text: str,
    config: ChunkingConfig,
    document_id: str,
    source_type: str,
    page_char_offsets: list[tuple[int, int, int]],
    page_metadata: dict[int, Optional[PageMetadata]],
) -> list[Chunk]:
    """Split text into chunks respecting paragraph boundaries.

    Paragraphs (separated by blank lines) are greedily packed into chunks.
    A paragraph that alone exceeds *chunk_size_tokens* is kept whole (never
    split mid-paragraph) to preserve semantic integrity.
    """
    paragraphs = _PARAGRAPH_SEP_RE.split(text)
    if not paragraphs:
        return []

    chunks: list[Chunk] = []
    chunk_index = 0
    current_parts: list[str] = []
    current_tokens = 0
    current_char_offset = 0
    first_char_offset = 0

    for para in paragraphs:
        para = para.strip()
        if not para:
            current_char_offset += 2
            continue

        para_tokens = estimate_tokens(para)

        if current_parts and (current_tokens + para_tokens > config.chunk_size_tokens):
            chunk_text = clean_chunk_text("\n\n".join(current_parts))
            page_number = _char_offset_to_page(first_char_offset, page_char_offsets)
            key = chunk_key(document_id, page_number)
            cid = chunk_id_from_components(document_id, source_type, page_number, chunk_index)
            meta = page_metadata.get(page_number)

            if chunk_text:
                chunks.append(
                    Chunk(
                        chunk_id=cid,
                        chunk_key=key,
                        document_id=document_id,
                        source_type=source_type,
                        page_number=page_number,
                        chunk_index=chunk_index,
                        text=chunk_text,
                        chapter=meta.chapter if meta else None,
                        section=meta.section if meta else None,
                        domain_hint=meta.domain_hint if meta else None,
                    )
                )
                chunk_index += 1
            current_parts = []
            current_tokens = 0
            first_char_offset = current_char_offset

        if not current_parts:
            first_char_offset = current_char_offset

        current_parts.append(para)
        current_tokens += para_tokens
        current_char_offset += len(para) + 2

    if current_parts:
        chunk_text = clean_chunk_text("\n\n".join(current_parts))
        page_number = _char_offset_to_page(first_char_offset, page_char_offsets)
        key = chunk_key(document_id, page_number)
        cid = chunk_id_from_components(document_id, source_type, page_number, chunk_index)
        meta = page_metadata.get(page_number)

        if chunk_text:
            chunks.append(
                Chunk(
                    chunk_id=cid,
                    chunk_key=key,
                    document_id=document_id,
                    source_type=source_type,
                    page_number=page_number,
                    chunk_index=chunk_index,
                    text=chunk_text,
                    chapter=meta.chapter if meta else None,
                    section=meta.section if meta else None,
                    domain_hint=meta.domain_hint if meta else None,
                )
            )

    return chunks


def _sliding_window_chunks(
    text: str,
    config: ChunkingConfig,
    document_id: str,
    source_type: str,
    page_token_offsets: list[tuple[int, int, int]],
    page_metadata: dict[int, Optional[PageMetadata]],
) -> list[Chunk]:
    tokens = simple_tokenize(text)
    if not tokens:
        return []

    chunks: list[Chunk] = []
    stride = config.chunk_size_tokens - config.overlap_tokens
    chunk_index = 0

    for start_idx in range(0, len(tokens), stride):
        end_idx = min(start_idx + config.chunk_size_tokens, len(tokens))
        window_tokens = tokens[start_idx:end_idx]
        chunk_text = " ".join(window_tokens)

        if not chunk_text.strip():
            continue

        page_number = _token_offset_to_page(start_idx, page_token_offsets)
        key = chunk_key(document_id, page_number)
        cid = chunk_id_from_components(document_id, source_type, page_number, chunk_index)

        meta = page_metadata.get(page_number)
        chapter = meta.chapter if meta else None
        section = meta.section if meta else None
        domain_hint = meta.domain_hint if meta else None

        chunks.append(
            Chunk(
                chunk_id=cid,
                chunk_key=key,
                document_id=document_id,
                source_type=source_type,
                page_number=page_number,
                chunk_index=chunk_index,
                text=chunk_text,
                chapter=chapter,
                section=section,
                domain_hint=domain_hint,
            )
        )
        chunk_index += 1

        if end_idx >= len(tokens):
            break

    return chunks


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def configured_parser_priority() -> list[str]:
    raw = os.getenv("CHUNKFLOW_PARSER_PRIORITY", ",".join(DEFAULT_PARSER_PRIORITY))
    priority = [part.strip().lower() for part in raw.split(",") if part.strip()]
    return [p for p in priority if p in DEFAULT_PARSER_PRIORITY] or list(DEFAULT_PARSER_PRIORITY)


def _chunks_from_structured_parser(
    parsed_chunks: list[dict],
    *,
    document_id: str,
    source_type: str,
    effective_max: int,
    min_chunk_tokens: int,
) -> list[Chunk]:
    chunks = []
    for i, dc in enumerate(parsed_chunks):
        pn = dc.get("page_number")
        page_number = pn if pn is not None else 1
        key = chunk_key(document_id, page_number)
        cid = chunk_id_from_components(document_id, source_type, page_number, i)
        chunks.append(
            Chunk(
                chunk_id=cid,
                chunk_key=key,
                document_id=document_id,
                source_type=source_type,
                page_number=page_number,
                chunk_index=i,
                text=clean_chunk_text(dc["raw_text"]),
                chapter=dc.get("chapter"),
                section=dc.get("section"),
                domain_hint=dc.get("domain_hint"),
                headings=dc.get("headings", []),
                content_type=dc.get("content_type"),
            )
        )
    chunks = _repair_broken_boundaries(chunks, effective_max)
    chunks = _merge_structural_continuations(chunks, effective_max)
    return _merge_small_chunks(chunks, min_chunk_tokens, effective_max)

def parse_document(
    file_path: str,
    max_tokens: int = 400,
    chunk_size_tokens: int = 400,
    overlap_tokens: int = 100,
    min_chunk_tokens: int = 50,
) -> Document:
    """Parse a PDF file and return a Document with ordered Chunks.

    Uses Docling when available; falls back to pypdf + paragraph-aware chunking.

    *min_chunk_tokens* controls the post-processing merge pass: any chunk with
    fewer estimated tokens is merged with its same-section neighbour to avoid
    tiny orphan tails.  Set to 0 to disable merging.
    """
    path = os.path.abspath(file_path)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"File not found: {file_path}")

    with open(path, "rb") as f:
        raw = f.read()

    document_id = document_id_from_bytes(raw)
    source_type = Path(path).suffix.lower().lstrip(".") or "bin"
    if source_type not in ("pdf", "md", "txt"):
        source_type = "pdf" if path.lower().endswith(".pdf") else "bin"

    effective_max = max(max_tokens, chunk_size_tokens)

    parser_priority = configured_parser_priority()
    attempted: list[str] = []

    # --- MinerU path ---
    if "mineru" in parser_priority and is_mineru_available():
        attempted.append("mineru")
        logger.info("Using MinerU for high-fidelity parsing")
        try:
            mineru_chunks = parse_pdf_with_mineru(path, max_tokens=max_tokens)
        except Exception as e:
            logger.warning("MinerU parsing failed, falling back: %s", e)
            mineru_chunks = []

        if mineru_chunks:
            chunks = _chunks_from_structured_parser(
                mineru_chunks,
                document_id=document_id,
                source_type=source_type,
                effective_max=effective_max,
                min_chunk_tokens=min_chunk_tokens,
            )
            return Document(
                document_id=document_id,
                source_path=path,
                chunks=chunks,
                parser_used="mineru",
                parser_fallback_chain=attempted,
            )
        logger.info("MinerU produced no chunks, falling back")

    # --- Docling path ---
    if "docling" in parser_priority and is_docling_available():
        attempted.append("docling")
        logger.info("Using Docling for structure-aware parsing")
        try:
            docling_chunks = parse_pdf_with_docling(path, max_tokens=max_tokens)
        except Exception as e:
            logger.warning("Docling parsing failed, falling back to pypdf: %s", e)
            docling_chunks = []

        if docling_chunks:
            chunks = _chunks_from_structured_parser(
                docling_chunks,
                document_id=document_id,
                source_type=source_type,
                effective_max=effective_max,
                min_chunk_tokens=min_chunk_tokens,
            )
            return Document(
                document_id=document_id,
                source_path=path,
                chunks=chunks,
                parser_used="docling",
                parser_fallback_chain=attempted,
            )
        logger.info("Docling produced no chunks, falling back to pypdf")

    # --- Fallback: pypdf + paragraph-aware chunking ---
    attempted.append("pypdf")
    logger.info("Using pypdf + paragraph-aware chunking")
    try:
        reader = PdfReader(path)
    except Exception as e:
        raise RuntimeError(f"Failed to read PDF: {file_path}") from e

    raw_page_texts: list[tuple[int, str]] = []
    for i, page in enumerate(reader.pages):
        try:
            text = page.extract_text()
        except Exception:
            text = None
        if text is None:
            text = ""
        raw_page_texts.append((i + 1, text.strip()))

    page_texts = clean_page_texts(raw_page_texts)
    full_text, page_char_offsets = join_pages_smart(page_texts)

    if not full_text.strip():
        return Document(
            document_id=document_id,
            source_path=path,
            chunks=[],
            parser_used="pypdf",
            parser_fallback_chain=attempted,
        )

    page_metadata: dict[int, Optional[PageMetadata]] = {}
    for page_number, text in page_texts:
        try:
            meta = extract_metadata_from_page_text(page_number, text)
            page_metadata[page_number] = meta
        except Exception:
            page_metadata[page_number] = None

    config = ChunkingConfig(
        chunk_size_tokens=chunk_size_tokens,
        overlap_tokens=overlap_tokens,
    )

    chunks = _paragraph_aware_chunks(
        full_text, config, document_id, source_type,
        page_char_offsets, page_metadata,
    )

    chunks = _repair_broken_boundaries(chunks, effective_max)
    chunks = _merge_structural_continuations(chunks, effective_max)
    chunks = _merge_small_chunks(
        chunks, min_chunk_tokens, effective_max,
    )

    return Document(
        document_id=document_id,
        source_path=path,
        chunks=chunks,
        parser_used="pypdf",
        parser_fallback_chain=attempted,
    )
