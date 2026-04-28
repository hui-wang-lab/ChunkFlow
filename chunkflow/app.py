"""FastAPI application: file upload, parsing, and chunk viewing."""
from __future__ import annotations

import logging
import os
import tempfile
import uuid
from pathlib import Path

from fastapi import FastAPI, File, UploadFile, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from chunkflow.chunking import configured_parser_priority, parse_document
from chunkflow.docling_parser import is_docling_available
from chunkflow.mineru_parser import is_mineru_available

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("chunkflow.app")

PARSER_MODES: dict[str, list[str] | None] = {
    "auto": None,
    "docling": ["docling", "pypdf"],
    "mineru": ["mineru", "pypdf"],
    "pypdf": ["pypdf"],
}

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
    priority = configured_parser_priority()
    parser = "pypdf"
    for candidate in priority:
        if candidate == "docling" and is_docling_available():
            parser = "docling"
            break
        if candidate == "mineru" and is_mineru_available():
            parser = "mineru"
            break
        if candidate == "pypdf":
            parser = "pypdf"
            break
    return {
        "service": "ChunkFlow",
        "mineru_available": is_mineru_available(),
        "docling_available": is_docling_available(),
        "parser": parser,
        "parser_priority": priority,
    }


@app.post("/api/parse")
async def parse_file(
    file: UploadFile = File(...),
    parser: str = Query("auto", pattern="^(auto|docling|mineru|pypdf)$"),
    max_tokens: int = Query(400, ge=50, le=2000),
    chunk_size_tokens: int = Query(400, ge=50, le=2000),
    overlap_tokens: int = Query(100, ge=0, le=500),
    min_chunk_tokens: int = Query(50, ge=0, le=500),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    suffix = Path(file.filename).suffix.lower()
    if suffix != ".pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    unique_name = f"{uuid.uuid4().hex}{suffix}"
    save_path = UPLOAD_DIR / unique_name

    try:
        content = await file.read()
        save_path.write_bytes(content)

        logger.info("Parsing %s (%d bytes) ...", file.filename, len(content))
        document = parse_document(
            str(save_path),
            max_tokens=max_tokens,
            chunk_size_tokens=chunk_size_tokens,
            overlap_tokens=overlap_tokens,
            min_chunk_tokens=min_chunk_tokens,
            parser_priority=PARSER_MODES[parser],
        )

        result = document.to_dict()
        result["filename"] = file.filename
        result["file_size_bytes"] = len(content)
        result["parser_requested"] = parser

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


if __name__ == "__main__":
    main()
