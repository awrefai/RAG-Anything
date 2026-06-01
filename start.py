#!/usr/bin/env python3
"""
Starter launcher for common RAG-Anything workflows.

Run without arguments for an interactive menu, or pass a workflow command:

    python start.py large-pdf document.pdf --output ./out --page-window 100
    python start.py batch ./docs --output ./batch_out --recursive --dry-run
    python start.py parse document.pdf --output ./parsed
"""

from __future__ import annotations

import argparse
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable, List, Optional

PARSERS = ["mineru", "docling", "paddleocr"]
METHODS = ["auto", "txt", "ocr"]
BACKENDS = [
    "pipeline",
    "hybrid-auto-engine",
    "hybrid-http-client",
    "vlm-auto-engine",
    "vlm-http-client",
]
SOURCES = ["huggingface", "modelscope", "local"]


def run_command(args: List[str]) -> int:
    print("\nRunning:")
    print(shlex.join(args))
    print()
    return subprocess.call(args)


def module_main_command(module: str, *args: str) -> List[str]:
    """Run a module CLI through main() without runpy pre-import warnings."""
    return [
        sys.executable,
        "-c",
        f"from {module} import main; raise SystemExit(main())",
        *args,
    ]


def add_parser_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--parser",
        choices=PARSERS,
        default="mineru",
        help="Parser to use.",
    )
    parser.add_argument(
        "--method",
        choices=METHODS,
        default="auto",
        help="Parsing method.",
    )
    parser.add_argument("--lang", help="OCR language hint, for example en, ch, ja.")
    parser.add_argument(
        "--backend",
        choices=BACKENDS,
        default="pipeline",
        help="MinerU backend. Use vlm-auto-engine or vlm-http-client for VLM mode.",
    )
    parser.add_argument("--vlm-url", help="VLM HTTP service URL for vlm-http-client.")
    parser.add_argument(
        "--device",
        help="Inference device when supported by the installed parser.",
    )
    parser.add_argument(
        "--source",
        choices=SOURCES,
        default="huggingface",
        help="Model source when supported by the installed parser.",
    )
    parser.add_argument("--no-formula", action="store_true", help="Disable formulas.")
    parser.add_argument("--no-table", action="store_true", help="Disable tables.")


def append_common_parser_args(command: List[str], args: argparse.Namespace) -> None:
    command.extend(["--parser", args.parser, "--method", args.method])
    if args.lang:
        command.extend(["--lang", args.lang])
    if args.backend:
        command.extend(["--backend", args.backend])
    if args.vlm_url:
        command.extend(["--vlm_url", args.vlm_url])
    if args.device:
        command.extend(["--device", args.device])
    if args.source:
        command.extend(["--source", args.source])
    if args.no_formula:
        command.append("--no-formula")
    if args.no_table:
        command.append("--no-table")


def handle_parse(args: argparse.Namespace) -> int:
    command = module_main_command("raganything.parser", args.file)
    if args.output:
        command.extend(["--output", args.output])
    append_common_parser_args(command, args)
    if args.stats:
        command.append("--stats")
    return run_command(command)


def handle_batch(args: argparse.Namespace) -> int:
    command = module_main_command(
        "raganything.batch_parser",
        *args.paths,
        "--output",
        args.output,
        "--parser",
        args.parser,
        "--method",
        args.method,
        "--workers",
        str(args.workers),
        "--timeout",
        str(args.timeout),
    )
    if args.recursive:
        command.append("--recursive")
    else:
        command.append("--no-recursive")
    if args.no_progress:
        command.append("--no-progress")
    if args.dry_run:
        command.append("--dry-run")
    if args.lang:
        command.extend(["--lang", args.lang])
    if args.backend:
        command.extend(["--backend", args.backend])
    if args.vlm_url:
        command.extend(["--vlm_url", args.vlm_url])
    if args.device:
        command.extend(["--device", args.device])
    if args.source:
        command.extend(["--source", args.source])
    if args.no_formula:
        command.append("--no-formula")
    if args.no_table:
        command.append("--no-table")
    return run_command(command)


def handle_large_pdf(args: argparse.Namespace) -> int:
    command = module_main_command(
        "raganything.pdf_range_pipeline",
        args.pdf,
        "--output",
        args.output,
        "--page-window",
        str(args.page_window),
        "--method",
        args.method,
        "--retries",
        str(args.retries),
    )
    if args.total_pages:
        command.extend(["--total-pages", str(args.total_pages)])
    if args.no_resume:
        command.append("--no-resume")
    if not args.adaptive_page_window:
        command.append("--no-adaptive-page-window")
    if args.min_page_window:
        command.extend(["--min-page-window", str(args.min_page_window)])
    if args.lang:
        command.extend(["--lang", args.lang])
    if args.backend:
        command.extend(["--backend", args.backend])
    if args.vlm_url:
        command.extend(["--vlm-url", args.vlm_url])
    if args.device:
        command.extend(["--device", args.device])
    if args.source:
        command.extend(["--source", args.source])
    if args.no_formula:
        command.append("--no-formula")
    if args.no_table:
        command.append("--no-table")
    return run_command(command)


def handle_rag(args: argparse.Namespace) -> int:
    command = [
        sys.executable,
        "examples/raganything_example.py",
        args.file,
        "--working_dir",
        args.working_dir,
        "--output",
        args.output,
        "--parser",
        args.parser,
    ]
    if args.api_key:
        command.extend(["--api-key", args.api_key])
    if args.base_url:
        command.extend(["--base-url", args.base_url])
    return run_command(command)


def handle_check(args: argparse.Namespace) -> int:
    command = module_main_command(
        "raganything.parser",
        "dummy",
        "--check",
        "--parser",
        args.parser,
    )
    return run_command(command)


def handle_markdown_pdf(args: argparse.Namespace) -> int:
    method = args.method or "reportlab"
    if method == "reportlab":
        from raganything.parser import Parser

        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        generated_path = Parser.convert_text_to_pdf(args.input, str(output_path.parent))
        if generated_path.resolve() != output_path.resolve():
            shutil.move(str(generated_path), str(output_path))
        print(f"Successfully converted {args.input} to {output_path}")
        return 0

    command = module_main_command(
        "raganything.enhanced_markdown",
        args.input,
        "--output",
        args.output,
    )
    command.extend(["--method", method])
    return run_command(command)


def prompt(
    label: str,
    default: Optional[str] = None,
    choices: Optional[Iterable[str]] = None,
) -> str:
    suffix = f" [{default}]" if default else ""
    choice_text = f" ({', '.join(choices)})" if choices else ""
    value = input(f"{label}{choice_text}{suffix}: ").strip()
    return value or (default or "")


def prompt_yes_no(label: str, default: bool = False) -> bool:
    default_text = "Y/n" if default else "y/N"
    value = input(f"{label} [{default_text}]: ").strip().lower()
    if not value:
        return default
    return value in {"y", "yes", "true", "1"}


def interactive() -> int:
    print("RAG-Anything Starter")
    print("1. Parse one document")
    print("2. Process a large PDF by page ranges")
    print("3. Batch process files/folders")
    print("4. Full RAG example")
    print("5. Check parser installation")
    print("6. Convert markdown to PDF")

    selection = prompt("Select workflow", "2", ["1", "2", "3", "4", "5", "6"])
    python = sys.executable

    if selection == "1":
        file_path = prompt("Document path")
        output = prompt("Output directory", "./output")
        parser_name = prompt("Parser", "mineru", PARSERS)
        method = prompt("Method", "auto", METHODS)
        backend = prompt("Backend", "pipeline", BACKENDS)
        device = prompt("Device", "cpu")
        return run_command(
            [
                python,
                "start.py",
                "parse",
                file_path,
                "--output",
                output,
                "--parser",
                parser_name,
                "--method",
                method,
                "--backend",
                backend,
                "--device",
                device,
                "--stats",
            ]
        )

    if selection == "2":
        pdf = prompt("PDF path")
        output = prompt("Output directory", "./large_pdf_output")
        page_window = prompt("Pages per MinerU run (0 = try whole PDF)", "0")
        method = prompt("Method", "auto", METHODS)
        backend = prompt("Backend", "pipeline", BACKENDS)
        vlm_url = ""
        if backend == "vlm-http-client":
            vlm_url = prompt("VLM URL", "http://127.0.0.1:30000")
        device = prompt("Device", "cpu")
        retries = prompt("Retries per run", "1")
        adaptive = prompt_yes_no("Split automatically if the run is too large", True)
        min_page_window = prompt("Smallest adaptive page window", "25")
        command = [
            python,
            "start.py",
            "large-pdf",
            pdf,
            "--output",
            output,
            "--page-window",
            page_window,
            "--method",
            method,
            "--backend",
            backend,
            "--device",
            device,
            "--retries",
            retries,
            "--min-page-window",
            min_page_window,
        ]
        if not adaptive:
            command.append("--no-adaptive-page-window")
        if vlm_url:
            command.extend(["--vlm-url", vlm_url])
        return run_command(command)

    if selection == "3":
        path = prompt("File or folder path")
        output = prompt("Output directory", "./batch_output")
        parser_name = prompt("Parser", "mineru", PARSERS)
        method = prompt("Method", "auto", METHODS)
        workers = prompt("Workers", "2")
        recursive = prompt_yes_no("Search subfolders", True)
        dry_run = prompt_yes_no("Dry run first", True)
        command = [
            python,
            "start.py",
            "batch",
            path,
            "--output",
            output,
            "--parser",
            parser_name,
            "--method",
            method,
            "--workers",
            workers,
        ]
        if recursive:
            command.append("--recursive")
        if dry_run:
            command.append("--dry-run")
        return run_command(command)

    if selection == "4":
        file_path = prompt("Document path")
        output = prompt("Parser output directory", "./output")
        working_dir = prompt("RAG working directory", "./rag_storage")
        parser_name = prompt("Parser", "mineru", PARSERS)
        api_key = prompt("API key", os.getenv("LLM_BINDING_API_KEY", ""))
        command = [
            python,
            "start.py",
            "rag",
            file_path,
            "--output",
            output,
            "--working-dir",
            working_dir,
            "--parser",
            parser_name,
        ]
        if api_key:
            command.extend(["--api-key", api_key])
        return run_command(command)

    if selection == "5":
        parser_name = prompt("Parser", "mineru", PARSERS)
        return run_command([python, "start.py", "check", "--parser", parser_name])

    if selection == "6":
        input_path = prompt("Markdown input path")
        output = prompt("PDF output path", "./output.pdf")
        return run_command([python, "start.py", "markdown-pdf", input_path, output])

    print("Unknown selection")
    return 1


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Starter launcher for RAG-Anything workflows"
    )
    subparsers = parser.add_subparsers(dest="workflow")

    parse_parser = subparsers.add_parser("parse", help="Parse one document")
    parse_parser.add_argument("file", help="Document path")
    parse_parser.add_argument("--output", "-o", help="Output directory")
    add_parser_options(parse_parser)
    parse_parser.add_argument("--stats", action="store_true", help="Show stats")
    parse_parser.set_defaults(func=handle_parse)

    batch_parser = subparsers.add_parser("batch", help="Batch process files/folders")
    batch_parser.add_argument("paths", nargs="+", help="Files or folders")
    batch_parser.add_argument("--output", "-o", required=True, help="Output directory")
    batch_parser.add_argument("--parser", choices=PARSERS, default="mineru")
    batch_parser.add_argument("--method", choices=METHODS, default="auto")
    batch_parser.add_argument("--workers", type=int, default=2)
    batch_parser.add_argument("--timeout", type=int, default=300)
    batch_parser.add_argument(
        "--recursive",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Search subfolders recursively.",
    )
    batch_parser.add_argument("--lang", help="OCR language hint")
    batch_parser.add_argument("--backend", choices=BACKENDS, default="pipeline")
    batch_parser.add_argument("--vlm-url")
    batch_parser.add_argument("--device")
    batch_parser.add_argument("--source", choices=SOURCES, default="huggingface")
    batch_parser.add_argument("--no-formula", action="store_true")
    batch_parser.add_argument("--no-table", action="store_true")
    batch_parser.add_argument("--no-progress", action="store_true")
    batch_parser.add_argument("--dry-run", action="store_true")
    batch_parser.set_defaults(func=handle_batch)

    pdf_parser = subparsers.add_parser(
        "large-pdf", help="Process a large PDF by page ranges"
    )
    pdf_parser.add_argument("pdf", help="PDF path")
    pdf_parser.add_argument("--output", "-o", required=True, help="Output directory")
    pdf_parser.add_argument(
        "--page-window",
        type=int,
        default=0,
        help="Pages per MinerU run. Use 0 to try the whole PDF in one run.",
    )
    pdf_parser.add_argument("--total-pages", type=int)
    pdf_parser.add_argument("--method", choices=METHODS, default="auto")
    pdf_parser.add_argument("--retries", type=int, default=1)
    pdf_parser.add_argument("--no-resume", action="store_true")
    pdf_parser.add_argument(
        "--adaptive-page-window",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Split a failed range into smaller ranges until it fits the device.",
    )
    pdf_parser.add_argument("--min-page-window", type=int, default=25)
    pdf_parser.add_argument("--lang")
    pdf_parser.add_argument("--backend", choices=BACKENDS, default="pipeline")
    pdf_parser.add_argument("--vlm-url")
    pdf_parser.add_argument("--device")
    pdf_parser.add_argument("--source", choices=SOURCES, default="huggingface")
    pdf_parser.add_argument("--no-formula", action="store_true")
    pdf_parser.add_argument("--no-table", action="store_true")
    pdf_parser.set_defaults(func=handle_large_pdf)

    rag_parser = subparsers.add_parser("rag", help="Run the full RAG example")
    rag_parser.add_argument("file", help="Document path")
    rag_parser.add_argument("--working-dir", default="./rag_storage")
    rag_parser.add_argument("--output", "-o", default="./output")
    rag_parser.add_argument("--api-key", default=os.getenv("LLM_BINDING_API_KEY"))
    rag_parser.add_argument("--base-url", default=os.getenv("LLM_BINDING_HOST"))
    rag_parser.add_argument("--parser", choices=PARSERS, default="mineru")
    rag_parser.set_defaults(func=handle_rag)

    check_parser = subparsers.add_parser("check", help="Check parser installation")
    check_parser.add_argument("--parser", choices=PARSERS, default="mineru")
    check_parser.set_defaults(func=handle_check)

    markdown_parser = subparsers.add_parser(
        "markdown-pdf", help="Convert markdown to PDF"
    )
    markdown_parser.add_argument("input", help="Markdown input file")
    markdown_parser.add_argument("output", help="PDF output file")
    markdown_parser.add_argument(
        "--method",
        choices=["reportlab", "auto", "weasyprint", "pandoc", "pandoc_system"],
        default="reportlab",
    )
    markdown_parser.set_defaults(func=handle_markdown_pdf)

    return parser


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()
    if not args.workflow:
        return interactive()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
