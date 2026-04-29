import tempfile
import unittest
from pathlib import Path

from chunkflow.chunkers.base import ChunkerConfig
from chunkflow.chunkers.book import BookChunker
from chunkflow.chunkers.picture_pdf import PicturePdfChunker
from chunkflow.chunkers.qa import QAChunker
from chunkflow.chunkers.registry import get_chunker
from chunkflow.chunkers.table_data import TableDataChunker
from chunkflow.core.document_type import detect_document_type, detect_document_type_details
from chunkflow.core.pipeline import PipelineConfig, parse_to_chunk_package
from chunkflow.ir.models import Block, ParsedDocument
from chunkflow.ir.models import BBox
from chunkflow.parsers.table_file import TableFileParser
from chunkflow.parsers.text_file import TextFileParser


class Phase4TemplateAndParserTests(unittest.TestCase):
    def test_book_chunker_uses_chapters_and_skips_toc(self) -> None:
        document = _document(
            [
                _block(0, "heading", "Contents"),
                _block(1, "paragraph", "Chapter 1 .... 1"),
                _block(2, "heading", "Chapter 1 Start"),
                _block(3, "paragraph", "The first chapter begins."),
                _block(4, "heading", "Section 1.1"),
                _block(5, "paragraph", "A section paragraph."),
                _block(6, "heading", "Chapter 2 Next"),
                _block(7, "paragraph", "The second chapter begins."),
            ]
        )

        result = BookChunker().chunk(document, ChunkerConfig(child_max_tokens=80))

        titles = [parent.title for parent in result.parent_chunks]
        self.assertIn("Chapter 1 Start", titles)
        self.assertIn("Chapter 2 Next", titles)
        self.assertNotIn("Contents", titles)
        self.assertTrue(any(child.chunk_type == "book_section" for child in result.child_chunks))

    def test_table_file_parser_and_chunker_group_rows_by_sheet(self) -> None:
        with _temp_text("Name,Amount\nAlpha,10\nBeta,20\n", suffix=".csv") as path:
            document = TableFileParser().parse(path, _parser_config())

        self.assertEqual(document.document_type, "table_data")
        self.assertEqual(len(document.blocks), 2)
        self.assertEqual(document.blocks[0].metadata["columns"], ["Name", "Amount"])
        self.assertIn("Name: Alpha", document.blocks[0].text)

        result = TableDataChunker().chunk(document, ChunkerConfig(child_max_tokens=80))
        self.assertEqual(result.chunker_used, "table_data")
        self.assertEqual(len(result.parent_chunks), 1)
        self.assertEqual(result.child_chunks[0].chunk_type, "table_row_group")
        self.assertEqual(result.child_chunks[0].metadata["row_start"], 2)
        self.assertEqual(result.child_chunks[0].metadata["row_end"], 3)

    def test_picture_pdf_chunker_groups_by_page_and_keeps_image_context(self) -> None:
        document = _document(
            [
                _block(0, "paragraph", "OCR text on page one.", page=1),
                _block(1, "figure", "Figure 1 Workflow", page=1),
                _block(2, "paragraph", "OCR text on page two.", page=2),
            ]
        )

        result = PicturePdfChunker().chunk(document, ChunkerConfig(child_max_tokens=80))

        self.assertEqual([parent.title for parent in result.parent_chunks], ["Page 1", "Page 2"])
        self.assertTrue(any(child.chunk_type == "ocr_text" for child in result.child_chunks))
        self.assertTrue(any(child.chunk_type == "image_context" for child in result.child_chunks))

    def test_qa_chunker_extracts_pairs_and_metadata(self) -> None:
        document = _document(
            [
                _block(0, "heading", "FAQ"),
                _block(1, "paragraph", "Q: What is covered?"),
                _block(2, "paragraph", "A: Medical expenses are covered."),
                _block(3, "paragraph", "Q: What is excluded?"),
                _block(4, "paragraph", "A: Intentional acts are excluded."),
            ]
        )

        result = QAChunker().chunk(document, ChunkerConfig())

        qa_pairs = [child for child in result.child_chunks if child.chunk_type == "qa_pair"]
        self.assertEqual(len(qa_pairs), 2)
        self.assertEqual(qa_pairs[0].metadata["question"], "What is covered?")
        self.assertIn("Medical expenses", qa_pairs[0].metadata["answer"])

    def test_text_parser_and_detector_route_book_and_qa(self) -> None:
        with _temp_text("# FAQ\n\nQ: What is ChunkFlow?\n\nA: A chunking service.\n", suffix=".md") as path:
            document = TextFileParser().parse(path, _parser_config())
        self.assertEqual(detect_document_type(document), "qa")
        detection = detect_document_type_details(document)
        self.assertEqual(detection.document_type, "qa")
        self.assertGreaterEqual(detection.confidence, 0.6)
        self.assertTrue(detection.signals)

        with _temp_text("Chapter 1\n\nA beginning.\n\nChapter 2\n\nThe next part.\n", suffix=".txt") as path:
            book_document = TextFileParser().parse(path, _parser_config())
        self.assertEqual(detect_document_type(book_document), "book")

    def test_pipeline_parses_csv_to_table_data_package(self) -> None:
        with _temp_text("Name,Amount\nAlpha,10\nBeta,20\n", suffix=".csv") as path:
            package = parse_to_chunk_package(path, PipelineConfig(parser="auto", template="auto", include_blocks=False))

        self.assertEqual(package.parser_used, "table_file")
        self.assertEqual(package.chunker_used, "table_data")
        self.assertEqual(package.document_type, "table_data")
        self.assertIn("document_type_detection", package.metadata)
        self.assertEqual(
            package.metadata["document_type_detection"]["signals"],
            ["parser_document_type:table_data"],
        )
        self.assertGreaterEqual(len(package.child_chunks), 1)

    def test_registry_routes_phase4_templates(self) -> None:
        self.assertIsInstance(get_chunker("book"), BookChunker)
        self.assertIsInstance(get_chunker("table_data"), TableDataChunker)
        self.assertIsInstance(get_chunker("picture_pdf"), PicturePdfChunker)
        self.assertIsInstance(get_chunker("qa"), QAChunker)

    def test_contract_chunker_repairs_docling_split_article_markers(self) -> None:
        document = _document(
            [
                _block(0, "paragraph", "第一条 定本办法。", bbox=BBox(79, 516, 158, 613)),
                _block(1, "heading", "第一章 总则", bbox=BBox(253, 628, 348, 641)),
                _block(
                    2,
                    "paragraph",
                    "为加强安全风险辨识、评估、管控，结合实际，制",
                    bbox=BBox(79, 544, 521, 616),
                    heading_path=["第一章 总则"],
                ),
                _block(
                    3,
                    "list_item",
                    "生产安全风险是指某种特定危险事件发生的可能性与后果严重程度的组合，是指针",
                    bbox=BBox(79, 460, 521, 504),
                    heading_path=["第一章 总则"],
                ),
                _block(
                    4,
                    "list_item",
                    "第二条 对风险进行动态辨识评估并实施差异化管理的过程。",
                    bbox=BBox(79, 432, 442, 501),
                    heading_path=["第一章 总则"],
                ),
                _block(
                    5,
                    "list_item",
                    "第三条 本办法适用于集团公司及所属各单位。",
                    bbox=BBox(79, 376, 521, 420),
                    heading_path=["第一章 总则"],
                ),
            ]
        )

        result = get_chunker("contract_terms").chunk(document, ChunkerConfig(child_max_tokens=120))

        texts = [child.text for child in result.child_chunks]
        self.assertIn("第一条 为加强安全风险辨识、评估、管控，结合实际，制定本办法。", texts[0])
        self.assertIn("第二条 生产安全风险是指某种特定危险事件发生的可能性与后果严重程度的组合，是指针对风险进行动态辨识评估并实施差异化管理的过程。", texts[1])
        self.assertIn("第三条 本办法适用于集团公司及所属各单位。", texts[2])


def _document(blocks: list[Block]) -> ParsedDocument:
    return ParsedDocument(
        document_id="doc",
        source_path="sample.pdf",
        filename="sample.pdf",
        file_type="pdf",
        document_type=None,
        parser_used="synthetic",
        blocks=blocks,
    )


def _block(
    index: int,
    block_type: str,
    text: str,
    *,
    page: int = 1,
    bbox: BBox | None = None,
    heading_path: list[str] | None = None,
) -> Block:
    heading_path = [text] if heading_path is None and block_type == "heading" else (heading_path or [])
    return Block(
        block_id=f"b{index}",
        document_id="doc",
        page_number=page,
        block_type=block_type,
        text=text,
        markdown=text if block_type == "table" else None,
        bbox=bbox,
        reading_order=index,
        heading_path=heading_path,
    )


def _parser_config():
    from chunkflow.parsers.base import ParserConfig

    return ParserConfig()


class _temp_text:
    def __init__(self, text: str, *, suffix: str) -> None:
        self.text = text
        self.suffix = suffix

    def __enter__(self) -> Path:
        self._tmp = tempfile.NamedTemporaryFile("w", suffix=self.suffix, encoding="utf-8", delete=False)
        self._tmp.write(self.text)
        self._tmp.close()
        return Path(self._tmp.name)

    def __exit__(self, exc_type, exc, tb) -> None:
        Path(self._tmp.name).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
