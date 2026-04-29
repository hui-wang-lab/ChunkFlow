"""Template chunker registry."""
from __future__ import annotations

from chunkflow.chunkers.base import TemplateChunker
from chunkflow.chunkers.book import BookChunker
from chunkflow.chunkers.contract_terms import ContractTermsChunker
from chunkflow.chunkers.generic_structured import GenericStructuredChunker
from chunkflow.chunkers.laws import LawsChunker
from chunkflow.chunkers.manual import ManualChunker
from chunkflow.chunkers.paper import PaperChunker
from chunkflow.chunkers.picture_pdf import PicturePdfChunker
from chunkflow.chunkers.qa import QAChunker
from chunkflow.chunkers.table_data import TableDataChunker


def get_chunker(document_type: str) -> TemplateChunker:
    if document_type == "contract_terms":
        return ContractTermsChunker()
    if document_type == "book":
        return BookChunker()
    if document_type == "laws":
        return LawsChunker()
    if document_type == "paper":
        return PaperChunker()
    if document_type == "manual":
        return ManualChunker()
    if document_type == "table_data":
        return TableDataChunker()
    if document_type == "picture_pdf":
        return PicturePdfChunker()
    if document_type == "qa":
        return QAChunker()
    return GenericStructuredChunker()


def available_templates() -> list[str]:
    return [
        "contract_terms",
        "paper",
        "book",
        "manual",
        "laws",
        "table_data",
        "picture_pdf",
        "qa",
        "generic_structured",
    ]
