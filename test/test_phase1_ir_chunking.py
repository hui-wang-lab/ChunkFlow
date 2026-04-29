import unittest

from chunkflow.chunkers.base import ChunkerConfig
from chunkflow.chunkers.contract_terms import ContractTermsChunker
from chunkflow.ir.layout_noise import clean_layout_noise
from chunkflow.ir.models import BBox, Block, Page, ParsedDocument
from chunkflow.ir.section_tree import build_section_tree
from chunkflow.postprocess.media_context import attach_media_context


class Phase1IRChunkingTests(unittest.TestCase):
    def test_layout_noise_removes_repeated_headers_and_page_numbers(self) -> None:
        document = ParsedDocument(
            document_id="doc",
            source_path="sample.pdf",
            filename="sample.pdf",
            file_type="pdf",
            document_type=None,
            parser_used="synthetic",
            pages=[
                Page(page_number=1, width=600, height=800, block_ids=["h1", "p1", "n1"]),
                Page(page_number=2, width=600, height=800, block_ids=["h2", "p2", "n2"]),
            ],
            blocks=[
                Block("h1", "doc", 1, "paragraph", "Confidential", bbox=BBox(20, 10, 200, 30), reading_order=0),
                Block("p1", "doc", 1, "paragraph", "First page body.", bbox=BBox(20, 120, 500, 200), reading_order=1),
                Block("n1", "doc", 1, "paragraph", "1", bbox=BBox(290, 760, 310, 780), reading_order=2),
                Block("h2", "doc", 2, "paragraph", "Confidential", bbox=BBox(20, 10, 200, 30), reading_order=3),
                Block("p2", "doc", 2, "paragraph", "Second page body.", bbox=BBox(20, 120, 500, 200), reading_order=4),
                Block("n2", "doc", 2, "paragraph", "2", bbox=BBox(290, 760, 310, 780), reading_order=5),
            ],
        )

        warnings = clean_layout_noise(document)

        self.assertTrue(warnings)
        self.assertEqual([block.block_id for block in document.blocks], ["p1", "p2"])
        self.assertEqual(document.pages[0].block_ids, ["p1"])
        self.assertEqual(document.metadata["layout_noise_removed_count"], 4)

    def test_layout_noise_removes_insurance_running_headers_without_bbox(self) -> None:
        document = ParsedDocument(
            document_id="doc",
            source_path="sample.pdf",
            filename="sample.pdf",
            file_type="pdf",
            document_type=None,
            parser_used="synthetic",
            pages=[
                Page(page_number=8, block_ids=["h1", "p1"]),
                Page(page_number=9, block_ids=["h2", "p2"]),
            ],
            blocks=[
                Block("h1", "doc", 8, "paragraph", "盛世荣耀臻享版终身寿险（分红型）利益条款", reading_order=0),
                Block("p1", "doc", 8, "paragraph", "第六条 明确说明与如实告知", reading_order=1),
                Block("h2", "doc", 9, "paragraph", "新华人寿保险股份有限公司 个人保险基本条款第三版", reading_order=2),
                Block("p2", "doc", 9, "paragraph", "任，并不退还保险费。", reading_order=3),
            ],
        )

        warnings = clean_layout_noise(document)

        self.assertTrue(warnings)
        self.assertEqual([block.block_id for block in document.blocks], ["p1", "p2"])
        self.assertEqual(document.metadata["layout_noise_removed_count"], 2)

    def test_section_tree_promotes_structured_paragraph_headings(self) -> None:
        document = ParsedDocument(
            document_id="doc",
            source_path="sample.pdf",
            filename="sample.pdf",
            file_type="pdf",
            document_type=None,
            parser_used="synthetic",
            blocks=[
                Block(
                    block_id="b0",
                    document_id="doc",
                    page_number=1,
                    block_type="paragraph",
                    text="1.1 Eligibility",
                    reading_order=0,
                ),
                Block(
                    block_id="b1",
                    document_id="doc",
                    page_number=1,
                    block_type="paragraph",
                    text="Applicants must meet the eligibility rules.",
                    reading_order=1,
                ),
            ],
        )

        build_section_tree(document)

        self.assertEqual(document.blocks[0].block_type, "heading")
        self.assertEqual(document.blocks[0].heading_path, ["1.1 Eligibility"])
        self.assertEqual(document.blocks[1].heading_path, ["1.1 Eligibility"])

    def test_section_tree_builds_numbered_heading_hierarchy(self) -> None:
        document = ParsedDocument(
            document_id="doc",
            source_path="sample.pdf",
            filename="sample.pdf",
            file_type="pdf",
            document_type=None,
            parser_used="synthetic",
            blocks=[
                Block("b0", "doc", 1, "paragraph", "1 Eligibility", reading_order=0),
                Block("b1", "doc", 1, "paragraph", "1.1 Age Rules", reading_order=1),
                Block("b2", "doc", 1, "paragraph", "Applicants must be adults.", reading_order=2),
            ],
        )

        build_section_tree(document)

        self.assertEqual(document.blocks[0].metadata["heading_level"], 1)
        self.assertEqual(document.blocks[1].metadata["heading_level"], 2)
        self.assertEqual(document.blocks[1].heading_path, ["1 Eligibility", "1.1 Age Rules"])
        self.assertEqual(document.blocks[2].heading_path, ["1 Eligibility", "1.1 Age Rules"])

    def test_section_tree_uses_parser_font_size_as_heading_level_signal(self) -> None:
        document = ParsedDocument(
            document_id="doc",
            source_path="sample.pdf",
            filename="sample.pdf",
            file_type="pdf",
            document_type=None,
            parser_used="synthetic",
            blocks=[
                Block("b0", "doc", 1, "heading", "Main Section", reading_order=0, metadata={"font_size": 18}),
                Block("b1", "doc", 1, "heading", "Sub Section", reading_order=1, metadata={"font_size": 14}),
                Block("b2", "doc", 1, "paragraph", "Body.", reading_order=2),
            ],
        )

        build_section_tree(document)

        self.assertEqual(document.blocks[0].metadata["heading_level"], 1)
        self.assertEqual(document.blocks[1].metadata["heading_level"], 2)
        self.assertEqual(document.blocks[2].heading_path, ["Main Section", "Sub Section"])

    def test_contract_chunker_creates_parent_child_and_table_context(self) -> None:
        document = ParsedDocument(
            document_id="doc",
            source_path="sample.pdf",
            filename="sample.pdf",
            file_type="pdf",
            document_type=None,
            parser_used="synthetic",
            blocks=[
                Block(
                    block_id="b0",
                    document_id="doc",
                    page_number=1,
                    block_type="heading",
                    text="Article 1 Coverage",
                    reading_order=0,
                    heading_path=["Article 1 Coverage"],
                ),
                Block(
                    block_id="b1",
                    document_id="doc",
                    page_number=1,
                    block_type="paragraph",
                    text="The policy covers the following benefits.",
                    reading_order=1,
                    heading_path=["Article 1 Coverage"],
                ),
                Block(
                    block_id="b2",
                    document_id="doc",
                    page_number=1,
                    block_type="table",
                    text="| Benefit | Amount |\n| --- | --- |\n| A | 100 |",
                    markdown="| Benefit | Amount |\n| --- | --- |\n| A | 100 |",
                    caption="Benefit summary",
                    reading_order=2,
                    heading_path=["Article 1 Coverage"],
                ),
                Block(
                    block_id="b3",
                    document_id="doc",
                    page_number=1,
                    block_type="paragraph",
                    text="The benefit is subject to exclusions.",
                    reading_order=3,
                    heading_path=["Article 1 Coverage"],
                ),
            ],
        )
        build_section_tree(document)

        result = ContractTermsChunker().chunk(document, ChunkerConfig(child_max_tokens=80))
        attach_media_context(result.child_chunks, document, ChunkerConfig())

        self.assertEqual(len(result.parent_chunks), 1)
        self.assertGreaterEqual(len(result.child_chunks), 3)
        self.assertTrue(all(child.parent_id == result.parent_chunks[0].parent_id for child in result.child_chunks))

        table_child = next(child for child in result.child_chunks if child.chunk_type == "table")
        self.assertIn("Benefit", table_child.text)
        self.assertIn("Benefit summary", table_child.context_before or "")
        self.assertIn("covers the following benefits", table_child.context_before or "")
        self.assertIn("subject to exclusions", table_child.context_after or "")
        self.assertEqual(table_child.metadata["context_strategy"], "caption_and_same_section_neighbors")
        self.assertEqual(table_child.metadata["context_caption_block_ids"], ["b2"])


if __name__ == "__main__":
    unittest.main()
