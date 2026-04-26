# MinerU Integration

ChunkFlow can use MinerU precise parsing before Docling to improve table extraction.

## Enable MinerU

```bash
pip install -r requirements.txt

# Required to enable MinerU precise API.
export MINERU_API_TOKEN="your-token"

# Optional parser and MinerU settings.
export CHUNKFLOW_PARSER_PRIORITY="mineru,docling,pypdf"
export MINERU_MODEL_VERSION="vlm"
export MINERU_ENABLE_TABLE="true"
export MINERU_ENABLE_FORMULA="true"
export MINERU_IS_OCR="false"
export MINERU_LANGUAGE="ch"
export MINERU_POLL_TIMEOUT_SECONDS="300"
export MINERU_POLL_INTERVAL_SECONDS="3"
```

When `MINERU_API_TOKEN` is not configured or MinerU fails, parsing automatically falls back to Docling and then pypdf.

## Parser Order

Default order:

```text
MinerU precise API -> Docling -> pypdf
```

MinerU output is normalized into the same chunk shape used by the Docling path. Table chunks are marked with `content_type="table"` and table HTML is converted to Markdown tables where possible.
