"""Tests for scam-signal detection via the mock provider."""

import pytest

from app.ai.mock_provider import MockAIProvider


@pytest.mark.asyncio
async def test_detects_profit_signals():
    provider = MockAIProvider()
    result = await provider.analyze_post(
        "Гарантируем доходность 100% без риска! Переведи деньги сейчас."
    )
    assert "guaranteed_profit" in result.scam_signals
    assert "payment_request" in result.scam_signals
    assert "no_risk_claim" in result.scam_signals


@pytest.mark.asyncio
async def test_detects_urgency():
    provider = MockAIProvider()
    result = await provider.analyze_post("Успей, только сегодня! Последний шанс.")
    assert "urgency" in result.scam_signals


@pytest.mark.asyncio
async def test_detects_suspicious_links():
    provider = MockAIProvider()
    result = await provider.analyze_post("Забери бонус по ссылке https://bit.ly/xyz")
    assert "suspicious_link" in result.scam_signals


@pytest.mark.asyncio
async def test_clean_post():
    provider = MockAIProvider()
    result = await provider.analyze_post("Просто новость о погоде сегодня.")
    assert result.scam_signals == []


@pytest.mark.asyncio
async def test_advertising_detection():
    provider = MockAIProvider()
    result = await provider.analyze_post("Скидка 50%! Оформи подписку сейчас.")
    assert result.advertising_score >= 5
    assert result.post_type == "advertisement"
