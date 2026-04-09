"""Discord delivery and embed formatting."""

import logging
from typing import Mapping, Optional, Sequence, Union

import aiohttp

from src.config import BotConfig, load_config
from src.domain import Notice

DISCORD_EMBED_COLOR_BLUE = 0x3498DB
__all__ = [
    "BotConfig",
    "DISCORD_EMBED_COLOR_BLUE",
    "create_notice_embed",
    "load_config",
    "send_message_to_discord",
]

NoticeInput = Union[Notice, Mapping[str, object]]


def _notice_value(notice: NoticeInput, key: str) -> object:
    if isinstance(notice, Notice):
        return getattr(notice, key)
    return notice.get(key)


def create_notice_embed(notices: Sequence[NoticeInput]) -> Optional[dict]:
    """Create a Discord embed dict from notice data."""
    if not notices:
        return None

    fields = []

    for notice in notices:
        category = str(_notice_value(notice, "category") or "")
        title = str(_notice_value(notice, "title") or "")
        post_date = str(_notice_value(notice, "post_date") or "")
        url = _notice_value(notice, "url")
        field_name = f"[{category}] {title}"
        field_value = f"날짜: {post_date}\n"
        if url:
            field_value += f"[바로가기]({url})"

        # Discord embed field name limit is 256 chars, value limit is 1024 chars
        fields.append(
            {"name": field_name[:256], "value": field_value[:1024], "inline": False}
        )

    # Add Rainbow system links
    fields.append(
        {
            "name": "🌈 레인보우 시스템",
            "value": (
                "[비교과 프로그램](https://rainbow.cau.ac.kr/site/reservation/lecture/lectureList"
                "?menuid=001002002&submode=lecture&reservegroupid=1)\n"
                "[외부 프로그램](https://rainbow.cau.ac.kr/site/program/board/basicboard/list"
                "?boardtypeid=16&menuid=001002003)"
            ),
            "inline": False,
        }
    )

    return {
        "title": "📢 새로운 공지사항이 있습니다",
        "color": DISCORD_EMBED_COLOR_BLUE,
        "fields": fields,
    }


async def send_message_to_discord(
    config: BotConfig, all_notices: Sequence[NoticeInput]
) -> bool:
    """Send notice message to Discord channel using HTTP API."""
    if not all_notices:
        logging.info("No notices to send")
        return True

    embed = create_notice_embed(all_notices)
    headers = {
        "Authorization": f"Bot {config.bot_token}",
        "Content-Type": "application/json",
    }
    payload = {"embeds": [embed]}
    all_success = True

    try:
        async with aiohttp.ClientSession() as session:
            for channel_id in config.discord_channel_ids:
                url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
                try:
                    async with session.post(
                        url, headers=headers, json=payload
                    ) as response:
                        if response.status in (200, 201):
                            logging.info(
                                f"Successfully sent {len(all_notices)} notices to channel {channel_id}"
                            )
                        else:
                            error_text = await response.text()
                            logging.error(
                                f"Failed to send Discord message to channel {channel_id}: "
                                f"{response.status} - {error_text}"
                            )
                            all_success = False
                except Exception as e:
                    logging.error(
                        f"Error sending Discord message to channel {channel_id}: {str(e)}"
                    )
                    all_success = False

            return all_success
    except Exception as e:
        logging.error(f"Error sending Discord message: {str(e)}")
        return False
