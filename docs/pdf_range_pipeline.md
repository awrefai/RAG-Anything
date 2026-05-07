# PDF Range Pipeline

The PDF range pipeline processes very large PDFs in fixed page windows and then
merges the generated markdown and content-list outputs. It is useful when a
single PDF is too large to parse reliably in one MinerU run.

## Command Line

```bash
python -m raganything.pdf_range_pipeline large.pdf \
  --output ./large_pdf_output \
  --page-window 100 \
  --method auto \
  --retries 1 \
  --device cpu
```

Outputs:

- `large_pdf_output/ranges/`: one parser output folder per page range
- `large_pdf_output/merged/large.md`: merged markdown in page order
- `large_pdf_output/merged/large_content_list.json`: merged content list
- `large_pdf_output/range_manifest.json`: status for each range

Page numbers passed to MinerU are zero-based. Range folder names are one-based
for readability, for example `pages_00001_00100`.

## Python API

```python
from raganything import PDFRangePipeline

pipeline = PDFRangePipeline()
result = pipeline.process_pdf(
    pdf_path="large.pdf",
    output_dir="./large_pdf_output",
    page_window=100,
    method="auto",
    retries=1,
    resume=True,
    device="cpu",
)

print(result.summary())
```

## Resume Behavior

By default, completed range folders are reused when they already contain a
`*_content_list.json` file. Use `--no-resume` to force reprocessing every range.

## Notes

- This does not physically split the PDF. It uses MinerU's existing
  `start_page` and `end_page` parameters for each range.
- Merged `page_idx` values are offset back to the original document page
  numbers.
- Failed ranges are recorded in the manifest and the command exits with a
  non-zero status.
