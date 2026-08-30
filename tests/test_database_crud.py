"""Basic CRUD tests for repositories."""

import pytest

from app.database.models import Channel, Post, PostAnalysis, User
from app.database.repositories.analyses import AnalysisRepository
from app.database.repositories.channels import ChannelRepository
from app.database.repositories.posts import PostRepository
from app.database.repositories.users import UserRepository


@pytest.mark.asyncio
async def test_user_get_or_create(db_session):
    repo = UserRepository(db_session)
    user, created = await repo.get_or_create(999, username="bob")
    assert created is True
    assert user.telegram_id == 999

    again, created2 = await repo.get_or_create(999)
    assert created2 is False
    assert (await repo.count()) == 1


@pytest.mark.asyncio
async def test_channel_crud(db_session):
    repo = ChannelRepository(db_session)
    channel, created = await repo.get_or_create_by_username("Example")
    assert created is True
    assert channel.username == "example"  # lowercased

    found = await repo.get_by_username("example")
    assert found is not None

    await repo.update(channel, title="New Title", subscriber_count=100)
    assert channel.subscriber_count == 100


@pytest.mark.asyncio
async def test_post_upsert_and_analysis(db_session):
    channel_repo = ChannelRepository(db_session)
    channel, _ = await channel_repo.get_or_create_by_username("chan")

    post_repo = PostRepository(db_session)
    post = Post(
        channel_id=channel.id,
        telegram_message_id=1,
        text="hello",
    )
    saved = await post_repo.upsert(post)
    assert saved.id is not None

    # upsert again should reuse row
    post2 = Post(channel_id=channel.id, telegram_message_id=1, text="updated")
    saved2 = await post_repo.upsert(post2)
    assert saved2.id == saved.id
    assert saved2.text == "updated"

    analysis = PostAnalysis(post_id=saved.id, quality_score=8.0, topic="AI")
    await post_repo.save_analysis(analysis)
    fetched = await post_repo.get_analysis(saved.id)
    assert fetched.topic == "AI"


@pytest.mark.asyncio
async def test_analysis_and_snapshot(db_session):
    channel_repo = ChannelRepository(db_session)
    channel, _ = await channel_repo.get_or_create_by_username("chan2")
    repo = AnalysisRepository(db_session)

    from app.database.models import ChannelAnalysis, ChannelSnapshot

    analysis = ChannelAnalysis(channel_id=channel.id, quality_score=82.0, verdict="RECOMMEND")
    saved = await repo.create(analysis)
    assert saved.id is not None

    snap = ChannelSnapshot(channel_id=channel.id, analysis_id=saved.id, trust_score=70.0)
    await repo.add_snapshot(snap)
    snaps = await repo.list_snapshots(channel.id)
    assert len(snaps) == 1

    latest = await repo.latest_for_channel(channel.id)
    assert latest.quality_score == 82.0
