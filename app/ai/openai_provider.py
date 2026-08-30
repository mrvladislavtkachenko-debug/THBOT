"""OpenAI implementation of the AI provider.

Uses the Chat Completions API with a system prompt loaded from
``prompts/*.txt`` and a strict JSON-format instruction. Handles network
errors, API errors and timeouts via tenacity retries.
"""

from __future__ import annotations

import json
from typing import Any

from openai import AsyncOpenAI
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.ai.base import AIError, AIProvider
from app.ai.json_extractor import InvalidJSONError, extract_json
from app.ai.prompts import load_prompt
from app.config import get_settings
from app.schemas import (
    ChannelAnalysisResult,
    PostAnalysisResult,
    ScamReport,
)

# Retry on transient network/API errors but not on invalid JSON (that is
# handled by the caller via re-prompting).
_RETRYABLE = (
    Exception,
)  # widened to any exception; retries are cheap and bounded


class OpenAIProvider(AIProvider):
    """Concrete AI provider backed by the OpenAI API."""

    name = "openai"

    def __init__(self) -> None:
        settings = get_settings()
        if not settings.openai_api_key:
            raise AIError("OPENAI_API_KEY is not configured")
        self._client = AsyncOpenAI(api_key=settings.openai_api_key)
        self._model = settings.openai_model

    # ------------------------------------------------------------------
    async def _complete(
        self, system_prompt: str, user_content: str, expect: str = "object"
    ) -> Any:
        """Run a chat completion and return parsed JSON."""
        raw = await self._chat(system_prompt, user_content)
        return extract_json(raw)

    @retry(
        retry=retry_if_exception_type(_RETRYABLE),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        reraise=True,
    )
    async def _chat(self, system_prompt: str, user_content: str) -> str:
        try:
            resp = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                temperature=0.2,
                response_format={"type": "json_object"},
            )
            content = resp.choices[0].message.content
            if not content:
                raise AIError("empty model response")
            return content
        except AIError:
            raise
        except Exception as exc:  # network, API, timeout
            raise AIError(f"OpenAI request failed: {exc}") from exc

    # ------------------------------------------------------------------
    async def analyze_post(self, text: str | None) -> PostAnalysisResult:
        if not text:
            text = "(пост без текста)"
        payload = {"text": text[:4000]}
        data = await self._complete(
            load_prompt("post_analysis"),
            json.dumps(payload, ensure_ascii=False),
        )
        return PostAnalysisResult.model_validate(data)

    async def analyze_channel(
        self,
        channel_meta: dict[str, Any],
        posts_summary: list[dict[str, Any]],
    ) -> ChannelAnalysisResult:
        payload = {"channel": channel_meta, "posts_summary": posts_summary[:200]}
        data = await self._complete(
            load_prompt("channel_analysis"),
            json.dumps(payload, ensure_ascii=False),
        )
        return ChannelAnalysisResult.model_validate(data)

    async def analyze_scam_risk(self, posts: list[dict[str, Any]]) -> ScamReport:
        payload = {"posts": posts[:200]}
        data = await self._complete(
            load_prompt("scam_detection"),
            json.dumps(payload, ensure_ascii=False),
        )
        return ScamReport.model_validate(data)
