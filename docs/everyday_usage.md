# Everyday Local Usage

This checkout includes a Windows double-click launcher and a Linux/WSL command
line starter. Existing parsed documents are never deleted by these workflows.

## Recommended Routine

1. Double-click `RAG-Anything-Launcher.bat`.
2. Run **Full readiness check** after Windows, WSL, Python, or dependency updates.
3. Start the persistent MinerU API. Starting it again is safe; the command
   reports that it is already running.
4. Use the batch or large-PDF wizard.
5. Keep outputs outside the source package, for example `/mnt/d/koc/RAG_Output`.

The batch wizard scans subfolders recursively, previews the candidate files,
and asks before actual processing. Incremental mode stores
`.raganything_batch_manifest.json` in the output directory and skips unchanged
files on later runs. Changing parser options forces affected files to be
processed again.

Files with the same name in different subfolders receive distinct output
directories. If the output directory is inside the input tree, generated files
under that output directory are excluded from later recursive scans.

## Persistent MinerU API

The launcher manages the service, or use:

```bash
.venv/bin/python start.py mineru-api start
.venv/bin/python start.py mineru-api status
.venv/bin/python start.py mineru-api stop
```

The managed service uses `http://127.0.0.1:18080`. Its PID and log are stored in
`.runtime/`. Batch and large-PDF commands pass `--api-url` to reuse this service
instead of starting a new local MinerU API for every file or page range.

## Direct Batch Command

```bash
.venv/bin/python start.py batch /mnt/d/koc/Documents \
  --output /mnt/d/koc/RAG_Output \
  --recursive \
  --incremental \
  --workers 2 \
  --api-url http://127.0.0.1:18080 \
  --log-file /mnt/d/koc/RAG_Output/batch.log
```

Add `--dry-run` to preview without parsing. MinerU's local API currently allows
three concurrent requests, so two or three workers is the practical ceiling for
this installation.

## Direct Large-PDF Command

```bash
.venv/bin/python start.py large-pdf /mnt/d/koc/large.pdf \
  --output /mnt/d/koc/RAG_Output/large \
  --page-window 300 \
  --adaptive-page-window \
  --min-page-window 25 \
  --api-url http://127.0.0.1:18080 \
  --log-file /mnt/d/koc/RAG_Output/large/large_pdf.log
```

Completed ranges are resumed using `range_success.json`; failed oversized
ranges are split until they fit the configured minimum window. Markdown and
content-list JSON are merged in original page order.

## Pipeline and VLM Modes

- `--backend pipeline` is the default and does not use a VLM backend.
- `--backend vlm-auto-engine` uses MinerU's local VLM engine.
- `--backend vlm-http-client --vlm-url URL` uses an external VLM service.
- `--api-url` identifies the persistent MinerU API and is separate from
  `--vlm-url`.

## Repair and Verification

If `.venv` is missing, the launcher recreates dependencies automatically. The
manual equivalent is:

```bash
uv sync --frozen --all-extras --link-mode copy
.venv/bin/python start.py doctor
```

Normal daily commands use `.venv/bin/python` directly and do not resolve or
upgrade dependencies. This keeps startup deterministic. Logs are appended to
the paths selected in the launcher. A failed batch exits nonzero and lists each
failed input in its summary.

For a controlled dependency refresh, stop the MinerU service first and rebuild
the lock before synchronizing:

```bash
.venv/bin/python start.py mineru-api stop
uv self update
uv lock --upgrade
uv sync --frozen --all-extras --link-mode copy
.venv/bin/python -m pytest -q
.venv/bin/python start.py doctor
```

MinerU currently supports Python 3.10 through 3.13. The PaddleOCR extra includes
the CPU PaddlePaddle runtime; RAG-Anything uses PaddleOCR's ONNX Runtime engine
by default to avoid CPU OneDNN/PIR compatibility failures.

As of 2026-07-12, MinerU 3.4.4 requires Transformers 4.x (`>=4.57.3,<5`). A
dependency audit reports three Transformers advisories whose fixes are only in
5.x, so the resolver cannot apply them without leaving MinerU's supported
range. Keep model sources trusted and update the lock again when MinerU supports
Transformers 5. Do not force individual transitive packages past `uv.lock`.

Do not use `RagAnyThing` or `raganything` as an output folder inside this
checkout. On Windows-mounted drives those names collide with the Python source
package and are rejected deliberately.
