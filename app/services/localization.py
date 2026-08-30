"""Localization service.

User-facing strings live in ``locales/*.json``, not in handlers. The
default language is Russian; adding English (or any language) is just a
matter of adding a ``locales/en.json`` file.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from app.config import get_settings

_language: str | None = None


def set_language(lang: str) -> None:
    """Set the active language (used mainly in tests)."""
    global _language
    _language = lang


@lru_cache(maxsize=32)
def _load_bundle(lang: str) -> dict:
    path: Path = get_settings().locales_dir / f"{lang}.json"
    if not path.exists():
        path = get_settings().locales_dir / "ru.json"
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _current_lang() -> str:
    if _language:
        return _language
    return get_settings().default_language


def t(key: str, **kwargs) -> str:
    """Translate a key, formatting placeholders ``{name}``."""
    bundle = _load_bundle(_current_lang())
    template = bundle.get(key, key)
    if kwargs:
        try:
            return template.format(**kwargs)
        except (KeyError, IndexError):
            return template
    return template
