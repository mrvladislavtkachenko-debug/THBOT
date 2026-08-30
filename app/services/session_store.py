"""In-memory per-user session state.

Stores the most recent :class:`AnalysisOutcome` per Telegram user so that
report-section buttons (best posts, trust explanation, risk, full report)
can render without re-running the analysis.
"""

from __future__ import annotations

import threading
from typing import Any

from app.services.report_service import AnalysisOutcome

_lock = threading.Lock()
_store: dict[int, dict[str, Any]] = {}


def save_outcome(telegram_id: int, outcome: AnalysisOutcome, analysis_id: str) -> None:
    with _lock:
        _store[telegram_id] = {"outcome": outcome, "analysis_id": analysis_id}


def get_outcome(telegram_id: int) -> tuple[AnalysisOutcome | None, str | None]:
    with _lock:
        entry = _store.get(telegram_id)
        if not entry:
            return None, None
        return entry["outcome"], entry["analysis_id"]


def clear(telegram_id: int) -> None:
    with _lock:
        _store.pop(telegram_id, None)
