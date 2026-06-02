"""Output path checks for CLI workflows."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Union


def _resolve_for_compare(path: Union[str, Path]) -> Path:
    path_obj = Path(path).expanduser()
    if not path_obj.is_absolute():
        path_obj = Path.cwd() / path_obj
    return path_obj.resolve(strict=False)


def _casefold_path(path: Path) -> str:
    return str(path).replace("\\", "/").casefold()


def validate_output_dir(output_dir: Optional[Union[str, Path]]) -> None:
    """Reject output paths that would write inside the source package."""
    if not output_dir:
        return

    if os.getenv("RAGANYTHING_ALLOW_UNSAFE_OUTPUT") == "1":
        return

    output_path = _resolve_for_compare(output_dir)
    package_dir = Path(__file__).resolve().parent

    output_key = _casefold_path(output_path)
    package_key = _casefold_path(package_dir)

    if output_key == package_key or output_key.startswith(f"{package_key}/"):
        raise ValueError(
            "Unsafe output directory: this path resolves inside the source "
            f"package ({package_dir}). Choose a separate folder such as "
            "./rag_output or ./batch_output. Set "
            "RAGANYTHING_ALLOW_UNSAFE_OUTPUT=1 only if you intentionally want "
            "to bypass this guard."
        )
