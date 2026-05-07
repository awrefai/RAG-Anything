import json
from pathlib import Path

from raganything.pdf_range_pipeline import PDFRangePipeline


class FakeParser:
    def parse_pdf(self, pdf_path, output_dir, method="auto", **kwargs):
        output_path = Path(output_dir)
        range_name = output_path.name
        nested = output_path / Path(pdf_path).stem / method
        nested.mkdir(parents=True, exist_ok=True)
        start_page = kwargs["start_page"]
        end_page = kwargs["end_page"]
        (nested / f"{Path(pdf_path).stem}.md").write_text(
            f"# {range_name}\n\npages {start_page + 1}-{end_page + 1}\n",
            encoding="utf-8",
        )
        content_list = [
            {
                "type": "text",
                "text": f"range {range_name}",
                "page_idx": 0,
            }
        ]
        with (nested / f"{Path(pdf_path).stem}_content_list.json").open(
            "w", encoding="utf-8"
        ) as file:
            json.dump(content_list, file)
        return content_list


def test_build_ranges_uses_inclusive_end_pages():
    assert PDFRangePipeline.build_ranges(total_pages=250, page_window=100) == [
        (0, 99),
        (100, 199),
        (200, 249),
    ]


def test_process_pdf_merges_markdown_and_offsets_content_list(tmp_path):
    pdf_path = tmp_path / "large.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")
    output_dir = tmp_path / "out"

    pipeline = PDFRangePipeline(parser_factory=FakeParser)
    result = pipeline.process_pdf(
        pdf_path=pdf_path,
        output_dir=output_dir,
        page_window=100,
        total_pages=250,
    )

    merged_md = Path(result.merged_markdown_file).read_text(encoding="utf-8")
    assert "<!-- pages 1-100 -->" in merged_md
    assert "<!-- pages 101-200 -->" in merged_md
    assert "<!-- pages 201-250 -->" in merged_md

    with Path(result.merged_content_list_file).open("r", encoding="utf-8") as file:
        merged_content = json.load(file)
    assert [item["page_idx"] for item in merged_content] == [0, 100, 200]

    with (output_dir / "range_manifest.json").open("r", encoding="utf-8") as file:
        manifest = json.load(file)
    assert len(manifest["ranges"]) == 3
    assert all(item["status"] == "success" for item in manifest["ranges"])


def test_process_pdf_resumes_existing_range(tmp_path):
    pdf_path = tmp_path / "large.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")
    output_dir = tmp_path / "out"
    existing = output_dir / "ranges" / "pages_00001_00100" / "large" / "auto"
    existing.mkdir(parents=True)
    (existing / "large.md").write_text("# existing\n", encoding="utf-8")
    with (existing / "large_content_list.json").open("w", encoding="utf-8") as file:
        json.dump([{"type": "text", "text": "existing", "page_idx": 0}], file)

    pipeline = PDFRangePipeline(parser_factory=FakeParser)
    result = pipeline.process_pdf(
        pdf_path=pdf_path,
        output_dir=output_dir,
        page_window=100,
        total_pages=100,
    )

    assert result.ranges[0].status == "skipped"
    merged_md = Path(result.merged_markdown_file).read_text(encoding="utf-8")
    assert "# existing" in merged_md
