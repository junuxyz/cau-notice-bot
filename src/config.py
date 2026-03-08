"""Environment-backed configuration for CAU Notice Bot."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class DiscordConfig:
    bot_token: str
    channel_ids: list[str]


@dataclass(frozen=True)
class CauNoticeSourceConfig:
    website_url: str
    api_url: str


@dataclass(frozen=True)
class LibraryNoticeSourceConfig:
    website_url: str
    api_url: str


@dataclass(frozen=True)
class SoftwareNoticeSourceConfig:
    notice_url: str
    state_file: str


@dataclass(frozen=True)
class BotConfig:
    discord: DiscordConfig
    cau: CauNoticeSourceConfig
    library: LibraryNoticeSourceConfig
    software: SoftwareNoticeSourceConfig

    @property
    def bot_token(self) -> str:
        return self.discord.bot_token

    @property
    def discord_channel_ids(self) -> list[str]:
        return self.discord.channel_ids

    @property
    def cau_website_url(self) -> str:
        return self.cau.website_url

    @property
    def cau_api_url(self) -> str:
        return self.cau.api_url

    @property
    def library_website_url(self) -> str:
        return self.library.website_url

    @property
    def library_api_url(self) -> str:
        return self.library.api_url

    @property
    def sw_notice_url(self) -> str:
        return self.software.notice_url

    @property
    def sw_notice_state_file(self) -> str:
        return self.software.state_file


def load_config() -> BotConfig:
    """Load configuration from environment variables."""
    return BotConfig(
        discord=DiscordConfig(
            bot_token=os.environ["DISCORD_BOT_TOKEN"],
            channel_ids=_load_discord_channel_ids(),
        ),
        cau=CauNoticeSourceConfig(
            website_url=os.environ["CAU_WEBSITE_URL"],
            api_url=os.environ["CAU_API_URL"],
        ),
        library=LibraryNoticeSourceConfig(
            website_url=os.environ["CAU_LIBRARY_WEBSITE_URL"],
            api_url=os.environ["CAU_LIBRARY_API_URL"],
        ),
        software=SoftwareNoticeSourceConfig(
            notice_url=os.environ.get("CAU_SW_NOTICE_URL", ""),
            state_file=os.environ.get(
                "CAU_SW_NOTICE_STATE_FILE", ".state/sw_last_seen_uid.txt"
            ),
        ),
    )


def _load_discord_channel_ids() -> list[str]:
    channel_ids_raw = os.environ.get("DISCORD_CHANNEL_IDS", "")
    if channel_ids_raw.strip():
        channel_ids = [
            channel_id.strip()
            for channel_id in channel_ids_raw.split(",")
            if channel_id.strip()
        ]
        if channel_ids:
            return channel_ids

    raise KeyError("DISCORD_CHANNEL_IDS")
