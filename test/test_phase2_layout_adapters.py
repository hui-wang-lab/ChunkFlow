import tempfile
import unittest
from pathlib import Path

from chunkflow.ir.normalize import coerce_bbox
from chunkflow.ir.validators import validate_parsed_document
from chunkflow.parsers.docling_pdf import document_from_docling_document
from chunkflow.parsers.mineru_pdf import document_from_mineru_content_list


class Phase2LayoutAdapterTests(unittest.TestCase):
    def test_bbox_normalization_accepts_list_dict_and_polygon(self) -> None:
        bbox = coerce_bbox([30, 20, 10, 5])
        self.assertIsNotNone(bbox)
        self.assertEqual((bbox.x0, bbox.y0, bbox.x1, bbox.y1), (10.0, 5.0, 30.0, 20.0))

        bbox = coerce_bbox({"left": 1, "top": 2, "right": 3, "bottom": 4})
        self.assertIsNotNone(bbox)
        self.assertEqual((bbox.x0, bbox.y0, bbox.x1, bbox.y1), (1.0, 2.0, 3.0, 4.0))

        bbox = coerce_bbox([[1, 2], [7, 3], [4, 9]])
        self.assertIsNotNone(bbox)
        self.assertEqual((bbox.x0, bbox.y0, bbox.x1, bbox.y1), (1.0, 2.0, 7.0, 9.0))

    def test_mineru_content_list_preserves_layout_table_and_figure_metadata(self) -> None:
        with _temp_file() as path:
            document = document_from_mineru_content_list(
                path=path,
                content_list=[
                    {
                        "type": "title",
                        "text": "Section A",
                        "text_level": 1,
                        "page_idx": 0,
                        "bbox": [10, 10, 100, 30],
                        "page_width": 600,
                        "page_height": 800,
                    },
                    {
                        "type": "table",
                        "table_caption": "Premium table",
                        "table_body": "<table><tr><th>K</th><th>V</th></tr><tr><td>x</td><td>1</td></tr></table>",
                        "page_idx": 0,
                        "bbox": {"left": 20, "top": 40, "right": 300, "bottom": 160},
                    },
                    {
                        "type": "image",
                        "img_caption": ["Figure 1", "Workflow"],
                        "img_path": "images/fig1.png",
                        "page_idx": 1,
                        "bbox": [[5, 5], [200, 5], [200, 140], [5, 140]],
                    },
                ],
            )

        self.assertEqual(document.parser_used, "mineru")
        self.assertEqual(len(document.blocks), 3)
        self.assertEqual(document.blocks[1].block_type, "table")
        self.assertIn("| x | 1 |", document.blocks[1].markdown)
        self.assertEqual(document.blocks[1].caption, "Premium table")
        self.assertIsNotNone(document.blocks[1].bbox)
        self.assertEqual(document.blocks[2].block_type, "figure")
        self.assertEqual(document.blocks[2].caption, "Figure 1 Workflow")
        self.assertEqual(document.blocks[2].metadata["image_path"], "images/fig1.png")
        self.assertEqual(len(validate_parsed_document(document)), 0)

    def test_docling_document_fixture_preserves_pages_bbox_and_table_html(self) -> None:
        doc = _FakeDoclingDocument(
            items=[
                _FakeDoclingItem(
                    "section_header",
                    "Chapter 1",
                    page=1,
                    bbox=[10, 10, 120, 30],
                    level=1,
                ),
                _FakeDoclingItem(
                    "text",
                    "A paragraph in the chapter.",
                    page=1,
                    bbox=[10, 40, 300, 70],
                ),
                _FakeDoclingTable(
                    markdown="| A | B |\n| --- | --- |\n| 1 | 2 |",
                    html="<table><tr><td>1</td><td>2</td></tr></table>",
                    page=1,
                    bbox=[10, 80, 300, 180],
                ),
            ],
            pages={1: _FakePage(width=600, height=800)},
        )
        with _temp_file() as path:
            document = document_from_docling_document(path=path, doc=doc)

        self.assertEqual(document.parser_used, "docling")
        self.assertEqual(document.pages[0].width, 600)
        self.assertEqual(document.blocks[0].block_type, "heading")
        self.assertEqual(document.blocks[1].heading_path, ["Chapter 1"])
        self.assertEqual(document.blocks[2].block_type, "table")
        self.assertIn("| 1 | 2 |", document.blocks[2].markdown)
        self.assertIn("<table>", document.blocks[2].html)
        self.assertEqual(len(validate_parsed_document(document)), 0)


class _Label:
    def __init__(self, value: str) -> None:
        self.value = value


class _FakeBBox:
    def __init__(self, bbox) -> None:
        self.bbox = bbox


class _FakeProv:
    def __init__(self, page: int, bbox) -> None:
        self.page_no = page
        self.bbox = bbox


class _FakeDoclingItem:
    def __init__(self, label: str, text: str, *, page: int, bbox, level: int | None = None) -> None:
        self.label = _Label(label)
        self.text = text
        self.level = level
        self.prov = [_FakeProv(page, bbox)]


class _FakeDoclingTable:
    def __init__(self, *, markdown: str, html: str, page: int, bbox) -> None:
        self.label = _Label("table")
        self.prov = [_FakeProv(page, bbox)]
        self._markdown = markdown
        self._html = html

    def export_to_markdown(self) -> str:
        return self._markdown

    def export_to_html(self) -> str:
        return self._html


class _FakePage:
    def __init__(self, *, width: int, height: int) -> None:
        self.width = width
        self.height = height


class _FakeDoclingDocument:
    def __init__(self, *, items, pages) -> None:
        self._items = items
        self.pages = pages

    def iterate_items(self):
        for item in self._items:
            yield item, 0


class _temp_file:
    def __enter__(self) -> Path:
        self._tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        self._tmp.write(b"layout-fixture")
        self._tmp.close()
        return Path(self._tmp.name)

    def __exit__(self, exc_type, exc, tb) -> None:
        Path(self._tmp.name).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
