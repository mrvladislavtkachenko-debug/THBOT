"""Robust JSON extraction + validation from AI model output.

Model responses may include code fences, markdown, or extra prose. This
module finds the JSON object/array in the text and parses it. It also
raises :class:`InvalidJSONError` so callers can retry.
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.ai.base import AIError


class InvalidJSONError(AIError):
    """Raised when the AI response does not contain valid JSON."""


def extract_json(text: str | None) -> Any:
    """Extract and parse a JSON value from model output text."""
    if not text:
        raise InvalidJSONError("empty model output")

    cleaned = text.strip()

    # Strip fenced code blocks
    fenced = re.search(r"```(?:json)?\s*(.*?)```", cleaned, re.DOTALL | re.IGNORECASE)
    if fenced:
        cleaned = fenced.group(1).strip()

    # Try to parse the whole thing first
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Find the outermost JSON object
    try:
        start = cleaned.index("{")
    except ValueError:
        raise InvalidJSONError("no JSON object found")
    depth = 0
    in_string = False
    escape = False
    end = len(cleaned)
    for i in range(start, len(cleaned)):
        ch = cleaned[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if depth != 0:
        raise InvalidJSONError("unbalanced JSON object")
    try:
        return json.loads(cleaned[start:end])
    except json.JSONDecodeError as exc:
        raise InvalidJSONError(f"JSON decode failed: {exc}")


def find_json_array(text: str | None) -> list[Any]:
    """Extract a JSON array from model output."""
    if not text:
        raise InvalidJSONError("empty model output")
    cleaned = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", cleaned, re.DOTALL | re.IGNORECASE)
    if fenced:
        cleaned = fenced.group(1).strip()
    try:
        value = json.loads(cleaned)
        if isinstance(value, list):
            return value
    except json.JSONDecodeError:
        pass
    try:
        start = cleaned.index("[")
    except ValueError:
        raise InvalidJSONError("no JSON array found")
    depth = 0
    in_string = False
    escape = False
    end = len(cleaned)
    for i in range(start, len(cleaned)):
        ch = cleaned[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if depth != 0:
        raise InvalidJSONError("unbalanced JSON array")
    try:
        return json.loads(cleaned[start:end])
    except json.JSONDecodeError as exc:
        raise InvalidJSONError(f"JSON decode failed: {exc}")
