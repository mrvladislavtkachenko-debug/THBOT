"""End-to-end analysis service test using the mock provider and fake data."""

import pytest

from app.ai.mock_provider import MockAIProvider
from app.schemas import ChannelInfo
from app.services.analysis_service import AnalysisService
from tests.fixtures.sample_channels import sample_channel_info, sample_posts


class FakeChannelService:
    """In-process ChannelService stub returning fixture data."""

    def __init__(self, info: ChannelInfo, posts: list) -> None:
        self._info = info
        self._posts = posts

    async def validate_and_get_info(self, username):
        return self._info

    async def get_posts(self, username, limit):
        return self._posts[:limit]

    async def get_message_count(self, username):
        return len(self._posts)

    async def disconnect(self):
        return None


@pytest.mark.asyncio
async def test_full_pipeline(db_session):
    info = sample_channel_info()
    posts = sample_posts(count=8)
    fake = FakeChannelService(info, posts)

    service = AnalysisService(
        session=db_session,
        channel_service=fake,
        provider=MockAIProvider(),
    )

    progress_log: list[str] = []

    async def on_progress(msg):
        progress_log.append(msg)

    result = await service.analyze(
        "example", user_id=None, on_progress=on_progress
    )

    assert result.outcome is not None
    assert 0 <= result.outcome.quality <= 100
    assert 0 <= result.outcome.trust <= 100
    assert 0 <= result.outcome.scam_risk <= 100
    assert 0 <= result.outcome.advertising <= 100
    assert result.outcome.verdict in (
        "STRONGLY_RECOMMEND", "RECOMMEND", "NEUTRAL", "CAUTION", "NOT_RECOMMENDED"
    )
    assert result.outcome.analyzed == 8
    assert progress_log  # progress was reported


@pytest.mark.asyncio
async def test_pipeline_with_scam_posts(db_session):
    info = sample_channel_info()
    posts = sample_posts(count=6, scam_style=True)
    fake = FakeChannelService(info, posts)

    service = AnalysisService(
        session=db_session,
        channel_service=fake,
        provider=MockAIProvider(),
    )
    result = await service.analyze("example", user_id=None)
    # scam-style posts should elevate the risk score
    assert result.outcome.scam_risk > 20


@pytest.mark.asyncio
async def test_report_generation(db_session):
    info = sample_channel_info()
    posts = sample_posts(count=6)
    fake = FakeChannelService(info, posts)
    service = AnalysisService(
        session=db_session,
        channel_service=fake,
        provider=MockAIProvider(),
    )
    result = await service.analyze("example", user_id=None)
    from app.services.report_service import ReportService

    rs = ReportService()
    compact = rs.compact(result.outcome)
    full = rs.full(result.outcome)
    assert "АНАЛИЗ КАНАЛА" in compact
    assert "ПОЛНЫЙ АНАЛИЗ" in full
    assert "@example" in compact


@pytest.mark.asyncio
async def test_cache_returned_without_rerun(db_session):
    info = sample_channel_info()
    posts = sample_posts(count=4)
    fake = FakeChannelService(info, posts)
    service = AnalysisService(
        session=db_session,
        channel_service=fake,
        provider=MockAIProvider(),
    )
    from app.services.cache_service import AnalysisCache

    cache = AnalysisCache()
    service._cache = cache

    first = await service.analyze("example", user_id=None)
    assert first.outcome is not None

    second = await service.analyze("example", user_id=None)
    # second run should be served from cache
    assert second.cached is True
