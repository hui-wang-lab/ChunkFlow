import unittest

from chunkflow.mineru_parser import _content_list_to_chunks, _html_table_to_markdown


class MinerUParserTests(unittest.TestCase):
    def test_html_table_is_converted_to_markdown(self) -> None:
        html = """
        <table>
          <tr><th>Name</th><th>Amount</th></tr>
          <tr><td>Alpha</td><td>10</td></tr>
        </table>
        """

        markdown = _html_table_to_markdown(html)

        self.assertIn("| Name | Amount |", markdown)
        self.assertIn("| Alpha | 10 |", markdown)

    def test_content_list_preserves_table_chunk_type_and_headings(self) -> None:
        items = [
            {"type": "title", "text": "Section A", "text_level": 1, "page_idx": 0},
            {
                "type": "table",
                "table_caption": "Metrics",
                "table_body": "<table><tr><th>K</th><th>V</th></tr><tr><td>x</td><td>1</td></tr></table>",
                "page_idx": 1,
            },
        ]

        chunks = _content_list_to_chunks(items, max_tokens=400)

        self.assertEqual(chunks[1]["content_type"], "table")
        self.assertEqual(chunks[1]["page_number"], 2)
        self.assertEqual(chunks[1]["headings"], ["Section A"])
        self.assertIn("Metrics", chunks[1]["raw_text"])
        self.assertIn("| x | 1 |", chunks[1]["raw_text"])


if __name__ == "__main__":
    unittest.main()
