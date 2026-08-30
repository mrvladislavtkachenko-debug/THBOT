"""Tests for the Telegram link / username parser."""

import pytest

from app.utils.validators import (
    InvalidChannelLinkError,
    parse_channel_link,
    normalize_channel_input,
)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("https://t.me/test", "test"),
        ("http://t.me/test", "test"),
        ("t.me/test", "test"),
        ("@channel", "channel"),
        ("channel", "channel"),
        ("https://t.me/channel/123", "channel"),
        ("https://t.me/s/channel", "channel"),
        ("https://telegram.me/channel", "channel"),
        ("https://telegram.dog/channel", "channel"),
    ],
)
def test_parse_channel_link(text, expected):
    ref = parse_channel_link(text)
    assert ref.username == expected


def test_post_link_detected():
    ref = parse_channel_link("https://t.me/channel/123")
    assert ref.is_post_link is True
    assert ref.message_id == 123
    # post number is ignored as a channel reference
    assert ref.username == "channel"


def test_canonical_url():
    assert normalize_channel_input("https://t.me/foobar") == "https://t.me/foobar"
    assert normalize_channel_input("@channels") == "https://t.me/channels"


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        "https://google.com",
        "not a channel @",
        "@",
        "a",  # too short
        "has space name",
        "https://t.me/",
    ],
)
def test_invalid_links_raise(text):
    with pytest.raises(InvalidChannelLinkError):
        parse_channel_link(text)
