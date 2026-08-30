"""System-prompt loading.

Prompts are stored as plain-text files under ``prompts/`` (not inside
Python code) so they can be edited independently of the source.
"""

from __future__ import annotations

from pathlib import Path

from app.config import get_settings


def load_prompt(name: str) -> str:
    """Load a system prompt by file name (without extension)."""
    path: Path = get_settings().prompts_dir / f"{name}.txt"
    if not path.exists():
        raise FileNotFoundError(f"Prompt not found: {path}")
    return path.read_text(encoding="utf-8").strip()
