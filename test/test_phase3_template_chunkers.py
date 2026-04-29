import unittest

from chunkflow.chunkers.base import ChunkerConfig
from chunkflow.chunkers.contract_terms import ContractTermsChunker
from chunkflow.chunkers.laws import LawsChunker
from chunkflow.chunkers.manual import ManualChunker
from chunkflow.chunkers.paper import PaperChunker
from chunkflow.chunkers.registry import get_chunker
from chunkflow.core.document_type import detect_document_type
from chunkflow.ir.models import Block, ParsedDocument


class Phase3TemplateChunkerTests(unittest.TestCase):
    def test_contract_terms_chunks_by_article_and_keeps_table_independent(self) -> None:
        document = _document(
            [
                _block(0, "heading", "Chapter 1 General"),
                _block(1, "heading", "Article 1 Coverage"),
                _block(2, "paragraph", "The insured is covered during the policy period."),
                _block(3, "list_item", "1. Death benefit is payable."),
                _block(4, "table", "| Benefit | Amount |\n| --- | --- |\n| Death | 100 |"),
                _block(5, "heading", "Article 2 Exclusion"),
                _block(6, "paragraph", "This policy excludes intentional acts."),
            ]
        )

        result = ContractTermsChunker().chunk(document, ChunkerConfig(child_max_tokens=80))

        self.assertEqual(result.chunker_used, "contract_terms")
        self.assertEqual(len(result.parent_chunks), 1)
        self.assertTrue(any(child.chunk_type == "table" for child in result.child_chunks))
        article_children = [child for child in result.child_chunks if child.chunk_type == "contract_clause"]
        self.assertTrue(any(child.metadata["article"] == "Article 1 Coverage" for child in article_children))
        self.assertTrue(any(child.metadata["article"] == "Article 2 Exclusion" for child in article_children))
        first_article = next(child for child in article_children if child.metadata["article"] == "Article 1 Coverage")
        self.assertIn("Death benefit", first_article.text)

    def test_contract_terms_skips_heading_only_article_chunks(self) -> None:
        document = _document(
            [
                _block(0, "heading", "Article 1 Contract Composition"),
                _block(1, "heading", "Article 2 Application Scope"),
                _block(2, "heading", "Article 3 Premium"),
                _block(3, "paragraph", "The applicant shall pay the premium on time."),
            ]
        )

        result = ContractTermsChunker().chunk(document, ChunkerConfig(child_max_tokens=80))

        texts = [child.text for child in result.child_chunks]
        self.assertFalse(any(text.strip().endswith("Article 2 Application Scope") for text in texts))
        self.assertTrue(any("The applicant shall pay the premium" in text for text in texts))

    def test_contract_terms_carries_article_metadata_across_long_article_parts(self) -> None:
        document = _document(
            [
                _block(0, "heading", "Article 5 Insurance Responsibility"),
                _block(1, "paragraph", "Death benefit " * 30),
                _block(2, "paragraph", "Disability benefit " * 30),
                _block(3, "paragraph", "Paid-up addition benefit " * 30),
            ]
        )

        result = ContractTermsChunker().chunk(document, ChunkerConfig(child_max_tokens=45))
        parts = [child for child in result.child_chunks if child.metadata.get("article") == "Article 5 Insurance Responsibility"]

        self.assertGreater(len(parts), 1)
        self.assertTrue(all("Article 5 Insurance Responsibility" in child.heading_path for child in parts))
        self.assertEqual([child.metadata.get("article_part_index") for child in parts], list(range(1, len(parts) + 1)))
        self.assertTrue(all(child.metadata.get("article_part_count") == len(parts) for child in parts))

    def test_contract_terms_ignores_paragraph_heading_path_changes_inside_article(self) -> None:
        document = _document(
            [
                _block(0, "heading", "Article 5 Insurance Responsibility"),
                Block(
                    block_id="b1",
                    document_id="doc",
                    page_number=2,
                    block_type="paragraph",
                    text="Continuation text from article five.",
                    reading_order=1,
                    heading_path=["Article 6 Exclusions"],
                ),
                _block(2, "heading", "Article 6 Exclusions", page=2),
                _block(3, "paragraph", "Excluded acts are not covered.", page=2),
            ]
        )

        result = ContractTermsChunker().chunk(document, ChunkerConfig(child_max_tokens=80))

        article_five = [child for child in result.child_chunks if child.metadata.get("article") == "Article 5 Insurance Responsibility"]
        self.assertEqual(len(article_five), 1)
        self.assertIn("Continuation text from article five", article_five[0].text)

    def test_laws_chunker_keeps_article_numbers_with_text(self) -> None:
        document = _document(
            [
                _block(0, "heading", "Chapter 1 General Provisions"),
                _block(1, "paragraph", "Article 1 This regulation applies to all agencies."),
                _block(2, "list_item", "(1) Agencies must file reports."),
                _block(3, "paragraph", "Article 2 Records must be retained."),
            ]
        )

        result = LawsChunker().chunk(document, ChunkerConfig(child_max_tokens=80))

        legal_articles = [child for child in result.child_chunks if child.chunk_type == "legal_article"]
        self.assertEqual(len(legal_articles), 3)
        self.assertIn("Article 1", legal_articles[1].text)
        self.assertIn("Agencies must file reports", legal_articles[1].text)
        self.assertIn("Article 2", legal_articles[2].text)

    def test_paper_chunker_preserves_abstract_and_references(self) -> None:
        document = _document(
            [
                _block(0, "heading", "Abstract"),
                _block(1, "paragraph", "We propose a method and evaluate it."),
                _block(2, "heading", "1 Introduction"),
                _block(3, "paragraph", "Retrieval systems need robust chunking."),
                _block(4, "table", "| Model | Score |\n| --- | --- |\n| A | 0.9 |"),
                _block(5, "heading", "References"),
                _block(6, "paragraph", "[1] Example reference."),
            ]
        )

        result = PaperChunker().chunk(document, ChunkerConfig(child_max_tokens=80))

        self.assertTrue(any(child.chunk_type == "paper_abstract" for child in result.child_chunks))
        self.assertTrue(any(child.chunk_type == "table" for child in result.child_chunks))
        self.assertTrue(any(child.chunk_type == "paper_references" for child in result.child_chunks))

    def test_manual_chunker_preserves_callout_procedure_and_troubleshooting_table(self) -> None:
        document = _document(
            [
                _block(0, "heading", "Installation"),
                _block(1, "paragraph", "WARNING Disconnect power before service."),
                _block(2, "list_item", "Step 1 Remove the cover."),
                _block(3, "list_item", "Step 2 Install the module."),
                _block(4, "table", "| Symptom | Remedy |\n| --- | --- |\n| Fault | Reset |"),
            ]
        )

        result = ManualChunker().chunk(document, ChunkerConfig(child_max_tokens=80))

        self.assertTrue(any(child.chunk_type == "manual_callout" for child in result.child_chunks))
        procedure = next(child for child in result.child_chunks if child.chunk_type == "manual_procedure")
        self.assertIn("Step 1", procedure.text)
        self.assertIn("Step 2", procedure.text)
        self.assertTrue(any(child.chunk_type == "manual_troubleshooting_table" for child in result.child_chunks))

    def test_registry_and_detector_route_phase3_templates(self) -> None:
        self.assertIsInstance(get_chunker("laws"), LawsChunker)
        self.assertIsInstance(get_chunker("paper"), PaperChunker)
        self.assertIsInstance(get_chunker("manual"), ManualChunker)

        self.assertEqual(detect_document_type(_document([_block(0, "paragraph", "Abstract\nKeywords: chunking")])), "paper")
        self.assertEqual(detect_document_type(_document([_block(0, "paragraph", "Article 1 This regulation applies.")])), "laws")
        self.assertEqual(detect_document_type(_document([_block(0, "paragraph", "WARNING Follow this procedure.")])), "manual")
        self.assertEqual(detect_document_type(_document([_block(0, "paragraph", "The insured pays a premium.")])), "contract_terms")


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


def _block(index: int, block_type: str, text: str, *, page: int = 1) -> Block:
    heading_path = [text] if block_type == "heading" else []
    return Block(
        block_id=f"b{index}",
        document_id="doc",
        page_number=page,
        block_type=block_type,
        text=text,
        markdown=text if block_type == "table" else None,
        reading_order=index,
        heading_path=heading_path,
    )


if __name__ == "__main__":
    unittest.main()
