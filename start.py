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
import json
import os
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.request
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
PROJECT_ROOT = Path(__file__).resolve().parent
RUNTIME_DIR = PROJECT_ROOT / ".runtime"
MINERU_API_PID_FILE = RUNTIME_DIR / "mineru-api.pid"
MINERU_API_LOG_FILE = RUNTIME_DIR / "mineru-api.log"


def run_command(args: List[str]) -> int:
    print("\nRunning:")
    print(shlex.join(args))
    print()
    return subprocess.call(args)


def validate_output_argument(output_dir: Optional[str]) -> bool:
    if not output_dir:
        return True
    from raganything.output_safety import validate_output_dir

    try:
        validate_output_dir(output_dir)
    except ValueError as exc:
        print(f"Error: {exc}")
        return False
    return True


def module_main_command(module: str, *args: str) -> List[str]:
    """Run a module CLI through main() without runpy pre-import warnings."""
    return [
        sys.executable,
        "-c",
        f"from {module} import main; raise SystemExit(main())",
        *args,
    ]


def _mineru_api_executable() -> str:
    executable = shutil.which("mineru-api")
    if executable:
        return executable
    candidate = Path(sys.executable).parent / (
        "mineru-api.exe" if os.name == "nt" else "mineru-api"
    )
    return str(candidate) if candidate.exists() else "mineru-api"


def _port_is_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


def _mineru_api_health(host: str, port: int) -> Optional[dict]:
    try:
        with urllib.request.urlopen(
            f"http://{host}:{port}/health", timeout=1.5
        ) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    if (
        isinstance(payload, dict)
        and payload.get("status") == "healthy"
        and isinstance(payload.get("protocol_version"), int)
    ):
        return payload
    return None


def _read_service_pid() -> Optional[int]:
    try:
        return int(MINERU_API_PID_FILE.read_text(encoding="ascii").strip())
    except (OSError, ValueError):
        return None


def _pid_is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _pid_is_managed_api(pid: int) -> bool:
    if not _pid_is_running(pid):
        return False
    try:
        command = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ")
    except OSError:
        return False
    return b"mineru-api" in command


def handle_mineru_api(args: argparse.Namespace) -> int:
    host = args.host
    port = args.port

    if args.action == "status":
        pid = _read_service_pid()
        health = _mineru_api_health(host, port)
        if health:
            pid_text = f" (PID {pid})" if pid else ""
            print(
                f"MinerU API is running at http://{host}:{port}{pid_text}; "
                f"protocol {health['protocol_version']}, "
                f"concurrency {health.get('max_concurrent_requests', 'unknown')}"
            )
            return 0
        if _port_is_open(host, port):
            print(
                f"Port {port} is occupied, but the service is not a compatible "
                "MinerU API"
            )
            return 1
        print(f"MinerU API is not listening at http://{host}:{port}")
        return 1

    if args.action == "stop":
        pid = _read_service_pid()
        if pid is None or not _pid_is_managed_api(pid):
            MINERU_API_PID_FILE.unlink(missing_ok=True)
            print("MinerU API managed service is not running")
            return 0
        try:
            os.killpg(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        deadline = time.monotonic() + 10
        while _pid_is_running(pid) and time.monotonic() < deadline:
            time.sleep(0.25)
        if _pid_is_running(pid):
            os.killpg(pid, signal.SIGKILL)
        MINERU_API_PID_FILE.unlink(missing_ok=True)
        print("MinerU API managed service stopped")
        return 0

    if _mineru_api_health(host, port):
        print(f"MinerU API is already running at http://{host}:{port}")
        return 0
    if _port_is_open(host, port):
        print(f"Cannot start MinerU API: port {port} is occupied by another service")
        return 1

    stale_pid = _read_service_pid()
    if stale_pid and _pid_is_managed_api(stale_pid):
        print(
            f"A managed MinerU API process (PID {stale_pid}) is still starting. "
            f"See {MINERU_API_LOG_FILE}"
        )
        return 1
    MINERU_API_PID_FILE.unlink(missing_ok=True)

    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    with MINERU_API_LOG_FILE.open("ab") as log_file:
        process = subprocess.Popen(
            [
                _mineru_api_executable(),
                "--host",
                host,
                "--port",
                str(port),
            ],
            cwd=PROJECT_ROOT,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    MINERU_API_PID_FILE.write_text(str(process.pid), encoding="ascii")

    deadline = time.monotonic() + args.startup_timeout
    while time.monotonic() < deadline:
        if _mineru_api_health(host, port):
            print(f"MinerU API started at http://{host}:{port} (PID {process.pid})")
            print(f"Log: {MINERU_API_LOG_FILE}")
            return 0
        if process.poll() is not None:
            MINERU_API_PID_FILE.unlink(missing_ok=True)
            print(
                f"MinerU API exited during startup with code {process.returncode}. "
                f"See {MINERU_API_LOG_FILE}"
            )
            return 1
        time.sleep(0.5)

    print(
        f"MinerU API is still starting after {args.startup_timeout}s. "
        f"Check status again or inspect {MINERU_API_LOG_FILE}"
    )
    return 1


def handle_doctor(args: argparse.Namespace) -> int:
    checks = []

    def record(name: str, ok: bool, detail: str) -> None:
        checks.append(ok)
        print(f"[{'OK' if ok else 'FAIL'}] {name}: {detail}")

    record(
        "Python",
        sys.version_info >= (3, 10),
        f"{sys.version.split()[0]} at {sys.executable}",
    )
    record("uv", shutil.which("uv") is not None, shutil.which("uv") or "not found")
    mineru = shutil.which("mineru") or str(Path(sys.executable).parent / "mineru")
    record("MinerU CLI", Path(mineru).exists(), mineru)
    mineru_api = _mineru_api_executable()
    record("MinerU API", Path(mineru_api).exists(), mineru_api)

    try:
        import raganything

        record("RAG-Anything import", True, raganything.__version__)
    except Exception as exc:
        record("RAG-Anything import", False, str(exc))

    uv_path = shutil.which("uv")
    if uv_path:
        result = subprocess.run(
            [uv_path, "pip", "check", "--python", sys.executable],
            capture_output=True,
            text=True,
            check=False,
        )
        detail = (result.stdout or result.stderr).strip() or "dependency check complete"
        record("Dependencies", result.returncode == 0, detail)

    free_gb = shutil.disk_usage(PROJECT_ROOT).free / (1024**3)
    record("Free disk space", free_gb >= 10, f"{free_gb:.1f} GiB available")

    api_health = _mineru_api_health(args.host, args.port)
    port_conflict = _port_is_open(args.host, args.port) and api_health is None
    if port_conflict:
        record(
            "MinerU API port",
            False,
            f"port {args.port} is occupied by an incompatible service",
        )
    print(
        f"[INFO] Persistent MinerU API: "
        f"{'running' if api_health else 'not running'} at "
        f"http://{args.host}:{args.port}"
    )
    print(f"[INFO] Runtime log: {MINERU_API_LOG_FILE}")

    if all(checks):
        print("Readiness check passed")
        return 0
    print("Readiness check found one or more blocking issues")
    return 1


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
        "--api-url",
        help="Reuse an already-running MinerU API server, for example http://127.0.0.1:18080.",
    )
    parser.add_argument(
        "--device",
        help="Inference device when supported by the installed parser.",
    )
    parser.add_argument(
        "--source",
        choices=SOURCES,
        default=None,
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
    if getattr(args, "api_url", None):
        command.extend(["--api_url", args.api_url])
    if args.device:
        command.extend(["--device", args.device])
    if args.source:
        command.extend(["--source", args.source])
    if args.no_formula:
        command.append("--no-formula")
    if args.no_table:
        command.append("--no-table")


def handle_parse(args: argparse.Namespace) -> int:
    if not validate_output_argument(args.output):
        return 1
    command = module_main_command("raganything.parser", args.file)
    if args.output:
        command.extend(["--output", args.output])
    append_common_parser_args(command, args)
    if args.stats:
        command.append("--stats")
    return run_command(command)


def handle_batch(args: argparse.Namespace) -> int:
    if not validate_output_argument(args.output):
        return 1
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
    if getattr(args, "incremental", False):
        command.append("--incremental")
    if getattr(args, "log_file", None):
        command.extend(["--log-file", args.log_file])
    if args.lang:
        command.extend(["--lang", args.lang])
    if args.backend:
        command.extend(["--backend", args.backend])
    if args.vlm_url:
        command.extend(["--vlm_url", args.vlm_url])
    if getattr(args, "api_url", None):
        command.extend(["--api_url", args.api_url])
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
    if not validate_output_argument(args.output):
        return 1
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
    if getattr(args, "api_url", None):
        command.extend(["--api-url", args.api_url])
    if args.device:
        command.extend(["--device", args.device])
    if args.source:
        command.extend(["--source", args.source])
    if args.no_formula:
        command.append("--no-formula")
    if args.no_table:
        command.append("--no-table")
    if getattr(args, "log_file", None):
        command.extend(["--log-file", args.log_file])
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
    print("7. Full readiness check")
    print("8. Persistent MinerU API service")

    selection = prompt("Select workflow", "2", ["1", "2", "3", "4", "5", "6", "7", "8"])
    python = sys.executable

    if selection == "1":
        file_path = prompt("Document path")
        output = prompt("Output directory", "./output")
        parser_name = prompt("Parser", "mineru", PARSERS)
        method = prompt("Method", "auto", METHODS)
        backend = prompt("Backend", "pipeline", BACKENDS)
        api_url = prompt("MinerU API URL (blank = auto local service)", "")
        device = prompt("Device (blank = MinerU default)", "")
        command = [
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
            "--stats",
        ]
        if device:
            command.extend(["--device", device])
        if api_url:
            command.extend(["--api-url", api_url])
        return run_command(command)

    if selection == "2":
        pdf = prompt("PDF path")
        output = prompt("Output directory", "./large_pdf_output")
        page_window = prompt("Pages per MinerU run (0 = try whole PDF)", "0")
        method = prompt("Method", "auto", METHODS)
        backend = prompt("Backend", "pipeline", BACKENDS)
        vlm_url = ""
        if backend == "vlm-http-client":
            vlm_url = prompt("VLM URL", "http://127.0.0.1:30000")
        api_url = prompt("MinerU API URL (blank = auto local service)", "")
        device = prompt("Device (blank = MinerU default)", "")
        retries = prompt("Retries per run", "1")
        adaptive = prompt_yes_no("Split automatically if the run is too large", True)
        min_page_window = prompt("Smallest adaptive page window", "25")
        log_file = prompt("Log file", str(Path(output) / "large_pdf.log"))
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
            "--retries",
            retries,
            "--min-page-window",
            min_page_window,
            "--log-file",
            log_file,
        ]
        if not adaptive:
            command.append("--no-adaptive-page-window")
        if device:
            command.extend(["--device", device])
        if vlm_url:
            command.extend(["--vlm-url", vlm_url])
        if api_url:
            command.extend(["--api-url", api_url])
        return run_command(command)

    if selection == "3":
        path = prompt("File or folder path")
        output = prompt("Output directory", "./batch_output")
        parser_name = prompt("Parser", "mineru", PARSERS)
        method = prompt("Method", "auto", METHODS)
        workers = prompt("Workers", "2")
        api_url = prompt("MinerU API URL (blank = auto local service)", "")
        log_file = prompt("Log file", str(Path(output) / "batch.log"))
        recursive = prompt_yes_no("Search subfolders", True)
        incremental = prompt_yes_no("Skip unchanged files from earlier runs", True)
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
            "--log-file",
            log_file,
        ]
        if recursive:
            command.append("--recursive")
        if incremental:
            command.append("--incremental")
        if api_url:
            command.extend(["--api-url", api_url])
        if dry_run:
            dry_run_result = run_command([*command, "--dry-run"])
            if dry_run_result != 0:
                return dry_run_result
            if not prompt_yes_no("Run this batch now", False):
                return 0
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

    if selection == "7":
        return run_command([python, "start.py", "doctor"])

    if selection == "8":
        action = prompt("Action", "status", ["start", "status", "stop"])
        return run_command([python, "start.py", "mineru-api", action])

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
    batch_parser.add_argument("--api-url")
    batch_parser.add_argument("--device")
    batch_parser.add_argument("--source", choices=SOURCES, default=None)
    batch_parser.add_argument("--no-formula", action="store_true")
    batch_parser.add_argument("--no-table", action="store_true")
    batch_parser.add_argument("--no-progress", action="store_true")
    batch_parser.add_argument("--dry-run", action="store_true")
    batch_parser.add_argument("--log-file")
    batch_parser.add_argument(
        "--incremental",
        action="store_true",
        help="Skip files unchanged since the previous successful batch run.",
    )
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
    pdf_parser.add_argument("--api-url")
    pdf_parser.add_argument("--device")
    pdf_parser.add_argument("--source", choices=SOURCES, default=None)
    pdf_parser.add_argument("--no-formula", action="store_true")
    pdf_parser.add_argument("--no-table", action="store_true")
    pdf_parser.add_argument("--log-file")
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

    doctor_parser = subparsers.add_parser(
        "doctor", help="Check whether the local installation is ready"
    )
    doctor_parser.add_argument("--host", default="127.0.0.1")
    doctor_parser.add_argument("--port", type=int, default=18080)
    doctor_parser.set_defaults(func=handle_doctor)

    api_parser = subparsers.add_parser(
        "mineru-api", help="Manage the persistent local MinerU API service"
    )
    api_parser.add_argument("action", choices=["start", "status", "stop"])
    api_parser.add_argument("--host", default="127.0.0.1")
    api_parser.add_argument("--port", type=int, default=18080)
    api_parser.add_argument("--startup-timeout", type=int, default=90)
    api_parser.set_defaults(func=handle_mineru_api)

    return parser


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()
    if not args.workflow:
        return interactive()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
