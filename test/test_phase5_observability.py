import json
import unittest
from pathlib import Path

from chunkflow.core.pipeline import PipelineConfig, parse_to_chunk_package
from chunkflow.core.snapshot import package_snapshot
from chunkflow.ir.models import BBox, BBoxRef, ChildChunk, ChunkPackage, ParentChunk
from chunkflow.postprocess.boundary_repair import repair_boundaries
from chunkflow.postprocess.overlong_split import split_overlong_chunks


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "test" / "fixtures"
GOLDEN = FIXTURES / "golden"


class Phase5ObservabilityTests(unittest.TestCase):
    def test_boundary_repair_merges_cross_page_hyphen_and_layout_continuation(self) -> None:
        parent = ParentChunk(
            parent_id="p1",
            document_id="doc",
            section_id="s1",
            heading_path=["Document"],
            title="Document",
            text="",
            page_span=(1, 2),
            source_block_ids=["b1", "b2"],
            child_chunk_ids=["c1", "c2"],
        )
        first = ChildChunk(
            chunk_id="c1",
            parent_id="p1",
            document_id="doc",
            chunk_type="text",
            template="generic_structured",
            text="The renewal bene-",
            page_span=(1, 1),
            source_block_ids=["b1"],
            bbox_refs=[BBoxRef("b1", 1, BBox(20, 720, 520, 780))],
            token_count=4,
        )
        second = ChildChunk(
            chunk_id="c2",
            parent_id="p1",
            document_id="doc",
            chunk_type="text",
            template="generic_structured",
            text="fit continues on the next page",
            page_span=(2, 2),
            source_block_ids=["b2"],
            bbox_refs=[BBoxRef("b2", 2, BBox(20, 40, 520, 120))],
            token_count=8,
        )
        package = ChunkPackage(
            document_id="doc",
            document_type="generic_structured",
            parser_used="synthetic",
            chunker_used="generic_structured",
            parent_chunks=[parent],
            child_chunks=[first, second],
        )

        warnings = repair_boundaries(package)

        self.assertTrue(any("hyphen" in warning for warning in warnings))
        self.assertEqual(len(package.child_chunks), 1)
        self.assertIn("benefit continues", package.child_chunks[0].text)
        self.assertEqual(parent.child_chunk_ids, ["c1"])

    def test_boundary_repair_merges_cross_parent_chinese_continuation(self) -> None:
        p1 = ParentChunk(
            parent_id="p1",
            document_id="doc",
            section_id="s1",
            heading_path=["第六条 明确说明与如实告知"],
            title="第六条 明确说明与如实告知",
            text="",
            page_span=(8, 8),
            source_block_ids=["b1"],
            child_chunk_ids=["c1"],
        )
        p2 = ParentChunk(
            parent_id="p2",
            document_id="doc",
            section_id="s2",
            heading_path=["新华人寿保险股份有限公司 个人保险基本条款第三版"],
            title="新华人寿保险股份有限公司 个人保险基本条款第三版",
            text="",
            page_span=(9, 9),
            source_block_ids=["b2"],
            child_chunk_ids=["c2"],
        )
        first = ChildChunk(
            chunk_id="c1",
            parent_id="p1",
            document_id="doc",
            chunk_type="contract_clause",
            template="contract_terms",
            text="我们不承担保险责",
            page_span=(8, 8),
            source_block_ids=["b1"],
            token_count=8,
        )
        second = ChildChunk(
            chunk_id="c2",
            parent_id="p2",
            document_id="doc",
            chunk_type="contract_clause",
            template="contract_terms",
            text="新华人寿保险股份有限公司 个人保险基本条款第三版\n\n任，并不退还保险费。",
            page_span=(9, 9),
            source_block_ids=["b2"],
            token_count=20,
        )
        package = ChunkPackage(
            document_id="doc",
            document_type="contract_terms",
            parser_used="synthetic",
            chunker_used="contract_terms",
            parent_chunks=[p1, p2],
            child_chunks=[first, second],
        )

        warnings = repair_boundaries(package)

        self.assertTrue(any("cross_parent_sentence" in warning for warning in warnings))
        self.assertEqual(len(package.child_chunks), 1)
        self.assertEqual(len(package.parent_chunks), 1)
        self.assertIn("保险责任，并不退还保险费", package.child_chunks[0].text)
        self.assertNotIn("新华人寿保险股份有限公司", package.child_chunks[0].text)

    def test_overlong_split_preserves_parent_child_edges(self) -> None:
        parent = ParentChunk(
            parent_id="p1",
            document_id="doc",
            section_id="s1",
            heading_path=["Document"],
            title="Document",
            text="",
            page_span=(1, 1),
            source_block_ids=["b1"],
            child_chunk_ids=["c1"],
        )
        child = ChildChunk(
            chunk_id="c1",
            parent_id="p1",
            document_id="doc",
            chunk_type="text",
            template="generic_structured",
            text=("Sentence one. " * 40) + ("Sentence two. " * 40),
            page_span=(1, 1),
            source_block_ids=["b1"],
            heading_path=["Document"],
            token_count=400,
        )
        package = ChunkPackage(
            document_id="doc",
            document_type="generic_structured",
            parser_used="synthetic",
            chunker_used="generic_structured",
            parent_chunks=[parent],
            child_chunks=[child],
            metadata={"chunker_config": {"child_max_tokens": 40}},
        )

        warnings = split_overlong_chunks(package)

        self.assertTrue(warnings)
        self.assertGreater(len(package.child_chunks), 1)
        self.assertEqual(parent.child_chunk_ids, [child.chunk_id for child in package.child_chunks])
        self.assertTrue(all(child.token_count <= 40 for child in package.child_chunks))
        self.assertTrue(all(child.metadata["overlong_split"] for child in package.child_chunks))

    def test_overlong_split_repeats_heading_prefix_on_every_part(self) -> None:
        heading = ["盛世荣耀臻享版终身寿险（分红型）利益条款", "第五条 保险责任"]
        heading_text = " > ".join(heading)
        parent = ParentChunk(
            parent_id="p1",
            document_id="doc",
            section_id="s1",
            heading_path=heading,
            title="第五条 保险责任",
            text="",
            page_span=(1, 2),
            source_block_ids=["b1"],
            child_chunk_ids=["c1"],
        )
        child = ChildChunk(
            chunk_id="c1",
            parent_id="p1",
            document_id="doc",
            chunk_type="contract_clause",
            template="contract_terms",
            text=(
                f"{heading_text}\n\n"
                + "若身故或身体全残时被保险人处于交费期间届满后的首个保单周年日之后。"
                + "本合同实际交纳的保险费乘以给付系数。" * 20
            ),
            page_span=(1, 2),
            source_block_ids=["b1"],
            heading_path=heading,
            token_count=500,
        )
        package = ChunkPackage(
            document_id="doc",
            document_type="contract_terms",
            parser_used="synthetic",
            chunker_used="contract_terms",
            parent_chunks=[parent],
            child_chunks=[child],
            metadata={"chunker_config": {"child_max_tokens": 80}},
        )

        split_overlong_chunks(package)

        self.assertGreater(len(package.child_chunks), 1)
        self.assertTrue(all(part.text.startswith(heading_text) for part in package.child_chunks))
        self.assertTrue(all(part.heading_path == heading for part in package.child_chunks))

    def test_debug_payload_is_optional_and_contains_graph(self) -> None:
        package = parse_to_chunk_package(
            FIXTURES / "phase5_qa.md",
            PipelineConfig(parser="auto", template="auto", include_blocks=True, include_debug=True),
        )
        payload = package.to_dict(include_blocks=False, include_debug=True)

        self.assertIn("debug", payload)
        self.assertIn("section_tree", payload["debug"])
        self.assertIn("parent_child_graph", payload["debug"])
        self.assertEqual(payload["debug"]["chunk_summary"]["child_count"], len(package.child_chunks))
        self.assertGreaterEqual(len(payload["debug"]["parent_child_graph"]), 1)

        without_debug = package.to_dict(include_blocks=False, include_debug=False)
        self.assertNotIn("debug", without_debug)
        self.assertNotIn("blocks", without_debug)

    def test_quality_metrics_include_phase5_observability_counts(self) -> None:
        package = parse_to_chunk_package(
            FIXTURES / "phase5_table.csv",
            PipelineConfig(parser="auto", template="auto", include_blocks=True),
        )
        metrics = package.parse_report.metrics

        self.assertEqual(metrics["orphan_child_count"], 0)
        self.assertEqual(metrics["chunks_without_source_block_count"], 0)
        self.assertEqual(metrics["parent_child_edge_count"], len(package.child_chunks))
        self.assertEqual(metrics["child_type_counts"], {"table_row_group": 1})
        self.assertEqual(metrics["block_type_counts"], {"table": 3})
        self.assertEqual(metrics["media_context_strategy_counts"], {})
        self.assertIn("over_max_token_child_count", metrics)
        self.assertIn("split_overlong_child_count", metrics)
        self.assertIn("layout_noise_removed_count", metrics)
        self.assertIn("inferred_heading_count", metrics)
        self.assertIn("heading_level_counts", metrics)
        self.assertIn("boundary_repair_count", metrics)

    def test_golden_snapshots_match_current_output(self) -> None:
        cases = {
            "csv_table_data": FIXTURES / "phase5_table.csv",
            "markdown_qa": FIXTURES / "phase5_qa.md",
        }

        for name, path in cases.items():
            with self.subTest(name=name):
                package = parse_to_chunk_package(
                    path,
                    PipelineConfig(parser="auto", template="auto", include_blocks=True),
                )
                current = package_snapshot(package)
                expected = json.loads((GOLDEN / f"{name}.json").read_text(encoding="utf-8"))
                self.assertEqual(current, expected)


if __name__ == "__main__":
    unittest.main()
