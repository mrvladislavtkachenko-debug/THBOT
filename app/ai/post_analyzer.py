"""Per-post AI analysis with JSON validation and retry.

Each post is analyzed with its own AI call. If the AI returns invalid or
malformed output we retry a bounded number of times; after that the post
is marked ``failed`` without aborting the channel analysis.
"""

from __future__ import annotations

import logging

from pydantic import ValidationError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
)

from app.ai.base import AIError, AIProvider
from app.ai.json_extractor import InvalidJSONError
from app.schemas import PostAnalysisResult

logger = logging.getLogger("ai.post")

MAX_JSON_RETRIES = 3


class PostAnalysisFailedError(AIError):
    """Raised when a post could not be analyzed after retries."""


class PostAnalyzer:
    """Analyzes individual posts through an AI provider."""

    def __init__(self, provider: AIProvider) -> None:
        self._provider = provider

    async def analyze(self, text: str | None) -> PostAnalysisResult:
        """Analyze a post, retrying on malformed output.

        Raises :class:`PostAnalysisFailedError` on persistent failure.
        """
        return await self._analyze_with_retry(text)

    @retry(
        retry=retry_if_exception_type((InvalidJSONError, ValidationError)),
        stop=stop_after_attempt(MAX_JSON_RETRIES),
        reraise=True,
    )
    async def _analyze_with_retry(self, text: str | None) -> PostAnalysisResult:
        try:
            result = await self._provider.analyze_post(text)
        except ValidationError as exc:
            logger.debug("post analysis validation error: %s", exc)
            raise
        except InvalidJSONError:
            raise
        except AIError:
            raise
        return result
