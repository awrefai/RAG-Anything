from pathlib import Path

import pytest

from raganything.output_safety import validate_output_dir


def test_rejects_package_output_case_insensitive(monkeypatch):
    repo_root = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(repo_root)

    with pytest.raises(ValueError, match="Unsafe output directory"):
        validate_output_dir("RagAnyThing")


def test_rejects_output_inside_package(monkeypatch):
    repo_root = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(repo_root)

    with pytest.raises(ValueError, match="Unsafe output directory"):
        validate_output_dir("raganything/runtime-output")


def test_allows_normal_output_folder(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    validate_output_dir("RagAnyThing")


def test_unsafe_output_can_be_overridden(monkeypatch):
    repo_root = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(repo_root)
    monkeypatch.setenv("RAGANYTHING_ALLOW_UNSAFE_OUTPUT", "1")

    validate_output_dir("RagAnyThing")
