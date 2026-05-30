# PDF Range Pipeline

The PDF range pipeline can process very large PDFs in one MinerU run or in
adaptive page windows, then merge the generated markdown and content-list
outputs. It is useful when a single PDF is too large to parse reliably in one
MinerU run, while still avoiding unnecessary MinerU restarts.

## Command Line

```bash
python -m raganything.pdf_range_pipeline large.pdf \
  --output ./large_pdf_output \
  --page-window 0 \
  --adaptive-page-window \
  --min-page-window 25 \
  --method auto \
  --retries 1 \
  --device cpu
```

Or use the project starter:

```bash
python start.py large-pdf large.pdf \
  --output ./large_pdf_output \
  --page-window 0 \
  --adaptive-page-window \
  --min-page-window 25 \
  --retries 1 \
  --device cpu
```

For VLM HTTP mode:

```bash
python start.py large-pdf large.pdf \
  --output ./large_pdf_output \
  --page-window 0 \
  --adaptive-page-window \
  --min-page-window 25 \
  --backend vlm-http-client \
  --vlm-url http://127.0.0.1:30000
```

Use `--page-window 0` to try the whole PDF in one MinerU invocation. If that
run is too large for the device, the default adaptive mode splits the failed
range in half and retries until it reaches `--min-page-window`. If you already
know the device limit, set `--page-window` to that limit, for example `300`, so
MinerU processes 300 pages per invocation.

Outputs:

- `large_pdf_output/ranges/`: one parser output folder per successful page run
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
    page_window=0,
    method="auto",
    retries=1,
    resume=True,
    adaptive_page_window=True,
    min_page_window=25,
    device="cpu",
)

print(result.summary())
```

## Resume Behavior

By default, completed range folders are reused when they already contain a
`*_content_list.json` file. Use `--no-resume` to force reprocessing every range.

## Notes

- This does not physically split the PDF. It uses MinerU's existing
  `start_page` and `end_page` parameters for each successful run.
- MinerU's CLI owns the local service lifecycle. The pipeline avoids restarts
  by using one large run when possible, and only creates smaller runs when the
  requested window is too large for the device.
- Merged `page_idx` values are offset back to the original document page
  numbers.
- Failed ranges are recorded in the manifest and the command exits with a
  non-zero status.
