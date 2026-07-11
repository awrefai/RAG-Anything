"""
Range-based PDF parsing pipeline.

This module adds a resumable workflow for very large PDFs by processing fixed
page ranges with the existing MinerU parser and then merging the range outputs
back into ordered markdown and content-list artifacts.
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from .output_safety import validate_output_dir
from .parser import MineruParser


@dataclass
class PDFRangeResult:
    """Result for a single page range."""

    start_page: int
    end_page: int
    output_dir: str
    markdown_file: Optional[str]
    content_blocks: int
    status: str
    error: Optional[str] = None
    attempts: int = 1
    elapsed_seconds: float = 0.0


@dataclass
class PDFRangePipelineResult:
    """Summary of a full range-based PDF parsing run."""

    pdf_path: str
    output_dir: str
    merged_markdown_file: str
    merged_content_list_file: str
    total_pages: int
    page_window: int
    ranges: List[PDFRangeResult] = field(default_factory=list)

    @property
    def successful_ranges(self) -> List[PDFRangeResult]:
        return [item for item in self.ranges if item.status in {"success", "skipped"}]

    @property
    def failed_ranges(self) -> List[PDFRangeResult]:
        return [item for item in self.ranges if item.status == "failed"]

    def summary(self) -> str:
        return (
            "PDF Range Pipeline Summary:\n"
            f"  PDF: {self.pdf_path}\n"
            f"  Total pages: {self.total_pages}\n"
            f"  Page window: {self.page_window or 'all'}\n"
            f"  Ranges: {len(self.ranges)}\n"
            f"  Successful: {len(self.successful_ranges)}\n"
            f"  Failed: {len(self.failed_ranges)}\n"
            f"  Markdown: {self.merged_markdown_file}\n"
            f"  Content list: {self.merged_content_list_file}"
        )


class PDFRangePipeline:
    """
    Process a large PDF in page ranges and merge generated artifacts.

    Page numbers are zero-based internally to match MinerU's ``start_page`` and
    ``end_page`` arguments. Merged markdown is ordered by range start page.
    """

    def __init__(
        self,
        parser_factory: Callable[[], MineruParser] = MineruParser,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.parser_factory = parser_factory
        self.logger = logger or logging.getLogger(__name__)

    @staticmethod
    def get_pdf_page_count(pdf_path: str | Path) -> int:
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise RuntimeError(
                "pypdf is required to count PDF pages. Install it with `pip install pypdf`."
            ) from exc

        reader = PdfReader(str(pdf_path))
        return len(reader.pages)

    @staticmethod
    def build_ranges(total_pages: int, page_window: int) -> List[tuple[int, int]]:
        if total_pages <= 0:
            raise ValueError("total_pages must be greater than zero")
        if page_window < 0:
            raise ValueError("page_window must be zero or greater")
        if page_window == 0:
            page_window = total_pages

        ranges: List[tuple[int, int]] = []
        for start_page in range(0, total_pages, page_window):
            end_page = min(start_page + page_window - 1, total_pages - 1)
            ranges.append((start_page, end_page))
        return ranges

    @staticmethod
    def _range_name(start_page: int, end_page: int) -> str:
        return f"pages_{start_page + 1:05d}_{end_page + 1:05d}"

    @staticmethod
    def _success_marker_file(range_dir: Path) -> Path:
        return range_dir / "range_success.json"

    @staticmethod
    def _find_markdown_file(output_dir: Path, pdf_stem: str) -> Optional[Path]:
        preferred = sorted(output_dir.rglob(f"{pdf_stem}.md"))
        if preferred:
            return preferred[0]

        candidates = sorted(output_dir.rglob("*.md"))
        return candidates[0] if candidates else None

    @staticmethod
    def _read_markdown(markdown_file: Optional[Path]) -> str:
        if markdown_file is None or not markdown_file.exists():
            return ""
        return markdown_file.read_text(encoding="utf-8")

    @staticmethod
    def _offset_page_indices(
        content_list: Sequence[Dict[str, Any]], page_offset: int
    ) -> List[Dict[str, Any]]:
        adjusted: List[Dict[str, Any]] = []
        for item in content_list:
            block = dict(item)
            page_idx = block.get("page_idx")
            if isinstance(page_idx, int):
                block["page_idx"] = page_idx + page_offset
            adjusted.append(block)
        return adjusted

    @staticmethod
    def _load_existing_content_list(range_dir: Path) -> Optional[List[Dict[str, Any]]]:
        candidates = sorted(range_dir.rglob("*_content_list.json"))
        if not candidates:
            return None
        with candidates[0].open("r", encoding="utf-8") as file:
            data = json.load(file)
        if not isinstance(data, list):
            raise ValueError(f"Expected a list in {candidates[0]}")
        return data

    @classmethod
    def _find_content_list_file(cls, range_dir: Path) -> Optional[Path]:
        candidates = sorted(range_dir.rglob("*_content_list.json"))
        return candidates[0] if candidates else None

    @staticmethod
    def _jsonable_options(options: Dict[str, Any]) -> Dict[str, Any]:
        clean: Dict[str, Any] = {}
        for key, value in options.items():
            try:
                json.dumps(value)
            except TypeError:
                clean[key] = repr(value)
            else:
                clean[key] = value
        return clean

    @classmethod
    def _range_metadata(
        cls,
        pdf_path: Path,
        start_page: int,
        end_page: int,
        method: str,
        parser_kwargs: Dict[str, Any],
    ) -> Dict[str, Any]:
        stat = pdf_path.stat()
        return {
            "pdf_path": str(pdf_path.resolve()),
            "pdf_size": stat.st_size,
            "pdf_mtime_ns": stat.st_mtime_ns,
            "start_page": start_page,
            "end_page": end_page,
            "method": method,
            "parser_kwargs": cls._jsonable_options(parser_kwargs),
        }

    @classmethod
    def _write_success_marker(
        cls,
        range_dir: Path,
        pdf_path: Path,
        start_page: int,
        end_page: int,
        method: str,
        parser_kwargs: Dict[str, Any],
        markdown_file: Optional[Path],
        content_list_file: Optional[Path],
    ) -> None:
        marker = cls._range_metadata(
            pdf_path, start_page, end_page, method, parser_kwargs
        )
        marker.update(
            {
                "status": "success",
                "markdown_file": str(markdown_file) if markdown_file else None,
                "content_list_file": (
                    str(content_list_file) if content_list_file else None
                ),
            }
        )
        cls._success_marker_file(range_dir).write_text(
            json.dumps(marker, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @classmethod
    def _load_completed_range(
        cls,
        range_dir: Path,
        pdf_path: Path,
        start_page: int,
        end_page: int,
        method: str,
        parser_kwargs: Dict[str, Any],
    ) -> Optional[List[Dict[str, Any]]]:
        marker_file = cls._success_marker_file(range_dir)
        if not marker_file.exists():
            return None

        marker = json.loads(marker_file.read_text(encoding="utf-8"))
        expected = cls._range_metadata(
            pdf_path, start_page, end_page, method, parser_kwargs
        )
        for key, value in expected.items():
            if marker.get(key) != value:
                return None

        content_file = marker.get("content_list_file")
        content_path = (
            Path(content_file)
            if content_file
            else cls._find_content_list_file(range_dir)
        )
        if content_path is None or not content_path.exists():
            return None

        with content_path.open("r", encoding="utf-8") as file:
            data = json.load(file)
        if not isinstance(data, list):
            raise ValueError(f"Expected a list in {content_path}")
        return data

    def process_pdf(
        self,
        pdf_path: str | Path,
        output_dir: str | Path,
        page_window: int = 0,
        total_pages: Optional[int] = None,
        method: str = "auto",
        retries: int = 0,
        resume: bool = True,
        adaptive_page_window: bool = True,
        min_page_window: int = 25,
        merge_markdown: bool = True,
        merge_content_list: bool = True,
        **parser_kwargs: Any,
    ) -> PDFRangePipelineResult:
        validate_output_dir(output_dir)

        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF file does not exist: {pdf_path}")
        if pdf_path.suffix.lower() != ".pdf":
            raise ValueError(f"Expected a PDF file, got: {pdf_path}")

        total = total_pages or self.get_pdf_page_count(pdf_path)
        ranges = self.build_ranges(total, page_window)
        if min_page_window <= 0:
            raise ValueError("min_page_window must be greater than zero")

        output_path = Path(output_dir)
        ranges_dir = output_path / "ranges"
        merged_dir = output_path / "merged"
        ranges_dir.mkdir(parents=True, exist_ok=True)
        merged_dir.mkdir(parents=True, exist_ok=True)

        parser = self.parser_factory()
        pdf_stem = pdf_path.stem
        range_results: List[PDFRangeResult] = []
        merged_markdown_parts: List[str] = []
        merged_content_list_items: List[Dict[str, Any]] = []

        range_queue = list(ranges)

        while range_queue:
            start_page, end_page = range_queue.pop(0)
            range_name = self._range_name(start_page, end_page)
            range_dir = ranges_dir / range_name
            range_dir.mkdir(parents=True, exist_ok=True)
            started_at = time.time()
            markdown_file: Optional[Path] = None
            content_list: List[Dict[str, Any]] = []
            status = "failed"
            error: Optional[str] = None
            attempts_used = 0

            existing_content_list = (
                self._load_completed_range(
                    range_dir,
                    pdf_path,
                    start_page,
                    end_page,
                    method,
                    parser_kwargs,
                )
                if resume
                else None
            )
            markdown_file = self._find_markdown_file(range_dir, pdf_stem)

            if resume and existing_content_list is not None:
                content_list = existing_content_list
                status = "skipped"
                attempts_used = 0
                self.logger.info("Skipping completed range %s", range_name)
            else:
                for attempt in range(1, retries + 2):
                    attempts_used = attempt
                    try:
                        self.logger.info(
                            "Processing %s pages %s-%s",
                            pdf_path.name,
                            start_page + 1,
                            end_page + 1,
                        )
                        content_list = parser.parse_pdf(
                            pdf_path=pdf_path,
                            output_dir=str(range_dir),
                            method=method,
                            start_page=start_page,
                            end_page=end_page,
                            **parser_kwargs,
                        )
                        markdown_file = self._find_markdown_file(range_dir, pdf_stem)
                        self._write_success_marker(
                            range_dir,
                            pdf_path,
                            start_page,
                            end_page,
                            method,
                            parser_kwargs,
                            markdown_file,
                            self._find_content_list_file(range_dir),
                        )
                        status = "success"
                        error = None
                        break
                    except (
                        Exception
                    ) as exc:  # pragma: no cover - exercised via CLI/runtime
                        error = str(exc)
                        self.logger.warning(
                            "Range %s failed on attempt %s: %s",
                            range_name,
                            attempt,
                            error,
                        )

            current_window = end_page - start_page + 1
            left_window = current_window // 2
            right_window = current_window - left_window
            can_split = (
                adaptive_page_window
                and left_window >= min_page_window
                and right_window >= min_page_window
            )
            if status == "failed" and can_split:
                split_at = start_page + left_window - 1
                left_range = (start_page, split_at)
                right_range = (split_at + 1, end_page)
                self.logger.warning(
                    "Range %s is too large for this run; splitting into %s and %s",
                    range_name,
                    self._range_name(*left_range),
                    self._range_name(*right_range),
                )
                range_results.append(
                    PDFRangeResult(
                        start_page=start_page,
                        end_page=end_page,
                        output_dir=str(range_dir),
                        markdown_file=str(markdown_file) if markdown_file else None,
                        content_blocks=len(content_list),
                        status="split",
                        error=error,
                        attempts=attempts_used,
                        elapsed_seconds=time.time() - started_at,
                    )
                )
                range_queue[0:0] = [left_range, right_range]
                continue

            elapsed = time.time() - started_at
            adjusted_content = self._offset_page_indices(content_list, start_page)
            if status in {"success", "skipped"}:
                if merge_markdown:
                    markdown_text = self._read_markdown(markdown_file).strip()
                    if markdown_text:
                        merged_markdown_parts.append(
                            f"<!-- pages {start_page + 1}-{end_page + 1} -->\n\n"
                            f"{markdown_text}\n"
                        )
                if merge_content_list:
                    merged_content_list_items.extend(adjusted_content)

            range_results.append(
                PDFRangeResult(
                    start_page=start_page,
                    end_page=end_page,
                    output_dir=str(range_dir),
                    markdown_file=str(markdown_file) if markdown_file else None,
                    content_blocks=len(content_list),
                    status=status,
                    error=error,
                    attempts=attempts_used,
                    elapsed_seconds=elapsed,
                )
            )

        merged_markdown_file = merged_dir / f"{pdf_stem}.md"
        merged_content_list_file = merged_dir / f"{pdf_stem}_content_list.json"
        manifest_file = output_path / "range_manifest.json"

        if merge_markdown:
            merged_markdown_file.write_text(
                "\n\n".join(merged_markdown_parts).strip() + "\n",
                encoding="utf-8",
            )
        if merge_content_list:
            with merged_content_list_file.open("w", encoding="utf-8") as file:
                json.dump(merged_content_list_items, file, ensure_ascii=False, indent=2)

        result = PDFRangePipelineResult(
            pdf_path=str(pdf_path),
            output_dir=str(output_path),
            merged_markdown_file=str(merged_markdown_file),
            merged_content_list_file=str(merged_content_list_file),
            total_pages=total,
            page_window=page_window,
            ranges=range_results,
        )

        with manifest_file.open("w", encoding="utf-8") as file:
            json.dump(asdict(result), file, ensure_ascii=False, indent=2)

        return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Process a large PDF by page ranges")
    parser.add_argument("pdf", help="PDF file to process")
    parser.add_argument("--output", "-o", required=True, help="Output directory")
    parser.add_argument(
        "--page-window",
        type=int,
        default=0,
        help="Pages per MinerU run. Use 0 to try the whole PDF in one run.",
    )
    parser.add_argument("--total-pages", type=int, help="Override detected page count")
    parser.add_argument(
        "--method", choices=["auto", "txt", "ocr"], default="auto", help="Parse method"
    )
    parser.add_argument("--retries", type=int, default=0, help="Retries per range")
    parser.add_argument("--no-resume", action="store_true", help="Reprocess all ranges")
    parser.add_argument(
        "--adaptive-page-window",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Split a failed range into smaller ranges until it fits the device.",
    )
    parser.add_argument(
        "--min-page-window",
        type=int,
        default=25,
        help="Smallest page range size allowed when adaptive splitting is enabled.",
    )
    parser.add_argument("--lang", help="OCR language hint")
    parser.add_argument("--device", help="MinerU device when supported")
    parser.add_argument("--backend", help="MinerU backend")
    parser.add_argument("--vlm-url", help="VLM service URL for vlm-http-client")
    parser.add_argument(
        "--api-url",
        help="Reuse an already-running MinerU API server, for example: http://127.0.0.1:18080",
    )
    parser.add_argument("--source", help="MinerU model source")
    parser.add_argument(
        "--no-formula", action="store_true", help="Disable formula parsing"
    )
    parser.add_argument("--no-table", action="store_true", help="Disable table parsing")
    parser.add_argument(
        "--log-file",
        help="Append range-pipeline logs to this file",
    )
    args = parser.parse_args()

    log_handlers = [logging.StreamHandler()]
    if args.log_file:
        log_path = Path(args.log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_handlers.append(logging.FileHandler(log_path, encoding="utf-8"))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=log_handlers,
    )

    pipeline = PDFRangePipeline()
    result = pipeline.process_pdf(
        pdf_path=args.pdf,
        output_dir=args.output,
        page_window=args.page_window,
        total_pages=args.total_pages,
        method=args.method,
        retries=args.retries,
        resume=not args.no_resume,
        adaptive_page_window=args.adaptive_page_window,
        min_page_window=args.min_page_window,
        lang=args.lang,
        device=args.device,
        backend=args.backend,
        vlm_url=args.vlm_url,
        api_url=args.api_url,
        source=args.source,
        formula=not args.no_formula,
        table=not args.no_table,
    )

    print(result.summary())
    return 1 if result.failed_ranges else 0


if __name__ == "__main__":
    raise SystemExit(main())
