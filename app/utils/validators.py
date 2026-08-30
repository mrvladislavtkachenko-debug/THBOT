"""Input validation and Telegram link parsing.

Supported inputs:
    https://t.me/channel
    http://t.me/channel
    t.me/channel
    @channel
    channel
    https://t.me/channel/123   (post link — post id is ignored as context)
    https://t.me/s/channel
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

USERNAME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]{3,31}$")
T_ME_HOSTS = {"t.me", "telegram.me", "telegram.dog", "telegram.org", "s.telegram.org"}
T_ME_HOSTS_STRICT = {"t.me", "telegram.me", "telegram.dog"}


@dataclass(frozen=True)
class ChannelRef:
    """Parsed reference to a Telegram channel."""

    username: str
    input: str
    message_id: int | None = None
    is_post_link: bool = False

    @property
    def canonical_url(self) -> str:
        return f"https://t.me/{self.username}"


class InvalidChannelLinkError(ValueError):
    """Raised when the user input is not a valid public channel reference."""


def parse_channel_link(text: str) -> ChannelRef:
    """Parse user input into a :class:`ChannelRef`.

    Raises :class:`InvalidChannelLinkError` for unsupported inputs.
    """
    if text is None:
        raise InvalidChannelLinkError("empty input")
    raw = text.strip()
    if not raw:
        raise InvalidChannelLinkError("empty input")

    # @username
    if raw.startswith("@"):
        username = raw[1:].strip()
        _validate_username(username)
        return ChannelRef(username=username, input=raw)

    lowered = raw.lower()

    # https://t.me/channel or https://t.me/channel/123
    parsed = urlparse(raw)
    if parsed.scheme in ("http", "https"):
        if parsed.netloc and parsed.netloc.split(":")[0].lower() in T_ME_HOSTS_STRICT:
            return _parse_path(parsed.path, raw)

    # t.me/channel (no scheme)
    if lowered.startswith("t.me/"):
        return _parse_path("/" + raw[len("t.me"):], raw)

    if lowered.startswith("telegram.me/") or lowered.startswith("telegram.dog/"):
        prefix = "telegram.me/" if lowered.startswith("telegram.me/") else "telegram.dog/"
        return _parse_path("/" + raw[len(prefix):], raw)

    # Bare username
    if USERNAME_RE.match(raw):
        return ChannelRef(username=raw, input=raw)

    raise InvalidChannelLinkError(
        "не удалось распознать ссылку на Telegram-канал"
    )


def _parse_path(path: str, raw: str) -> ChannelRef:
    parts = [p for p in path.split("/") if p]
    if not parts:
        raise InvalidChannelLinkError("empty path")
    # allow "s" prefix used by t.me/s/channel previews
    if parts and parts[0] == "s":
        parts = parts[1:]
    if not parts:
        raise InvalidChannelLinkError("empty path")
    username = parts[0]
    _validate_username(username)
    message_id: int | None = None
    is_post_link = False
    if len(parts) >= 2:
        # t.me/channel/123 -> post link
        post_str = parts[1]
        # sometimes post id is negative-number-encoded like "abc-123"
        for chunk in re.split(r"-", post_str):
            if chunk.isdigit():
                message_id = int(chunk)
                break
        is_post_link = message_id is not None
    return ChannelRef(
        username=username,
        input=raw,
        message_id=message_id,
        is_post_link=is_post_link,
    )


def _validate_username(username: str) -> None:
    if not USERNAME_RE.match(username):
        raise InvalidChannelLinkError(f"некорректное имя канала: {username!r}")


def normalize_channel_input(text: str) -> str:
    """Return the canonical URL for a channel reference, or raise."""
    return parse_channel_link(text).canonical_url


def is_valid_username(username: str) -> bool:
    return bool(username and USERNAME_RE.match(username))
