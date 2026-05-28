import importlib.util
from pathlib import Path
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "raganything_start", PROJECT_ROOT / "start.py"
)
start = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(start)


def test_markdown_pdf_uses_output_option(monkeypatch):
    captured = {}

    def fake_run_command(command):
        captured["command"] = command
        return 0

    monkeypatch.setattr(start, "run_command", fake_run_command)

    result = start.handle_markdown_pdf(
        SimpleNamespace(
            input="/tmp/input.md",
            output="/tmp/output.pdf",
            method="auto",
        )
    )

    assert result == 0
    assert captured["command"] == start.module_main_command(
        "raganything.enhanced_markdown",
        "/tmp/input.md",
        "--output",
        "/tmp/output.pdf",
        "--method",
        "auto",
    )


def test_markdown_pdf_defaults_to_reportlab(tmp_path):
    input_path = tmp_path / "input.md"
    output_path = tmp_path / "custom-name.pdf"
    input_path.write_text("# Test\n", encoding="utf-8")

    result = start.handle_markdown_pdf(
        SimpleNamespace(input=str(input_path), output=str(output_path), method=None)
    )

    assert result == 0
    assert output_path.read_bytes().startswith(b"%PDF")


def test_large_pdf_passes_vlm_url_option(monkeypatch):
    captured = {}

    def fake_run_command(command):
        captured["command"] = command
        return 0

    monkeypatch.setattr(start, "run_command", fake_run_command)

    result = start.handle_large_pdf(
        SimpleNamespace(
            pdf="/tmp/input.pdf",
            output="/tmp/out",
            page_window=100,
            total_pages=None,
            method="auto",
            retries=1,
            no_resume=False,
            lang=None,
            backend="vlm-http-client",
            vlm_url="http://127.0.0.1:30000",
            device="cpu",
            source="huggingface",
            no_formula=False,
            no_table=False,
        )
    )

    assert result == 0
    assert captured["command"][:2] == [start.sys.executable, "-c"]
    assert "--vlm-url" in captured["command"]
    assert "http://127.0.0.1:30000" in captured["command"]
