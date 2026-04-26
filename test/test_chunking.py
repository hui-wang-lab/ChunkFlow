import unittest

from chunkflow.chunking import _merge_structural_continuations
from chunkflow.pdf_parser import clean_chunk_text
from chunkflow.schema import Chunk


def make_chunk(
    *,
    idx: int,
    text: str,
    page: int,
    section: str | None,
    content_type: str | None,
) -> Chunk:
    return Chunk(
        chunk_id=f"chunk-{idx}",
        chunk_key=f"doc:{page}",
        document_id="doc",
        source_type="pdf",
        page_number=page,
        chunk_index=idx,
        text=text,
        section=section,
        content_type=content_type,
    )


class ChunkingRegressionTests(unittest.TestCase):
    def test_clean_chunk_text_removes_page_footer_numeric_residue(self) -> None:
        raw = "①本合同实际交纳的保险费×给付系数；\n20251 第 1 页"
        self.assertEqual(clean_chunk_text(raw), "①本合同实际交纳的保险费×给付系数；")

    def test_merge_cross_page_list_continuation_but_not_next_section(self) -> None:
        first = make_chunk(
            idx=0,
            page=1,
            section="第五条  保险责任",
            content_type="text",
            text=(
                "第五条  保险责任\n"
                "若身故或身体全残时被保险人处于交费期间届满后的首个保单周年日（含）之后，"
                "则其身故或身体全残保险金金额为以下三者之最大者：\n"
                "①本合同实际交纳的保险费×给付系数；"
            ),
        )
        second = make_chunk(
            idx=1,
            page=2,
            section="②基本保险金额对应的现金价值；",
            content_type="list_item",
            text=(
                "②基本保险金额对应的现金价值；\n"
                "③基本保险金额×（1+1.75%）（n-1）。\n"
                "上述给付系数根据以下不同情形确定。"
            ),
        )
        third = make_chunk(
            idx=2,
            page=2,
            section="2.特定公共交通工具意外伤害身故或身体全残保险金",
            content_type="text",
            text=(
                "2.特定公共交通工具意外伤害身故或身体全残保险金\n"
                "上述基本保险金额不包括因红利分配产生的相关利益。"
            ),
        )

        merged = _merge_structural_continuations([first, second, third], max_tokens=400)

        self.assertEqual(len(merged), 2)
        self.assertIn("①本合同实际交纳的保险费×给付系数；", merged[0].text)
        self.assertIn("②基本保险金额对应的现金价值；", merged[0].text)
        self.assertEqual(merged[1].section, "2.特定公共交通工具意外伤害身故或身体全残保险金")

    def test_merge_structural_continuation_even_when_it_exceeds_token_budget(self) -> None:
        first = make_chunk(
            idx=0,
            page=1,
            section="第二十三条  释义",
            content_type="text",
            text="第二十三条  释义\n" + ("甲" * 220) + "\n无合法有效驾驶证驾驶：指下列情形之一：",
        )
        second = make_chunk(
            idx=1,
            page=2,
            section="第二十三条  释义",
            content_type="list_item",
            text="- 1.没有取得有关主管部门颁发或者认可的驾驶资格证书；\n" + ("乙" * 220),
        )

        merged = _merge_structural_continuations([first, second], max_tokens=400)

        self.assertEqual(len(merged), 1)
        self.assertIn("无合法有效驾驶证驾驶：指下列情形之一：", merged[0].text)
        self.assertIn("没有取得有关主管部门颁发或者认可的驾驶资格证书", merged[0].text)

    def test_merge_same_section_when_next_chunk_starts_with_duplicated_heading(self) -> None:
        first = make_chunk(
            idx=0,
            page=1,
            section="第五条  保险责任",
            content_type="text",
            text="第五条  保险责任\n被保险人身故保险金根据以下不同情形确定：",
        )
        second = make_chunk(
            idx=1,
            page=2,
            section="第五条  保险责任",
            content_type="text",
            text="第五条  保险责任\n若身故或身体全残时被保险人处于交费期间届满后的首个保单周年日（不含）之前，则其保险金金额为本合同实际交纳的保险费。",
        )

        merged = _merge_structural_continuations([first, second], max_tokens=400)

        self.assertEqual(len(merged), 1)
        self.assertIn("根据以下不同情形确定：", merged[0].text)
        self.assertIn("若身故或身体全残时被保险人处于交费期间届满后的首个保单周年日", merged[0].text)


if __name__ == "__main__":
    unittest.main()
