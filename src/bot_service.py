"""
Discord bot configuration and message sending.
Uses Discord HTTP API directly for simplicity.
"""

import logging
import os
from dataclasses import dataclass
from typing import Dict, List, Optional

import aiohttp

DISCORD_EMBED_COLOR_BLUE = 0x3498db


@dataclass
class BotConfig:
    bot_token: str
    discord_channel_id: str
    cau_website_url: str
    cau_api_url: str
    library_website_url: str
    library_api_url: str


def load_config() -> BotConfig:
    """Load configuration from environment variables.

    Raises KeyError if any required variable is missing (fail-fast).
    """
    return BotConfig(
        bot_token=os.environ['DISCORD_BOT_TOKEN'],
        discord_channel_id=os.environ['DISCORD_CHANNEL_ID'],
        cau_website_url=os.environ['CAU_WEBSITE_URL'],
        cau_api_url=os.environ['CAU_API_URL'],
        library_website_url=os.environ['CAU_LIBRARY_WEBSITE_URL'],
        library_api_url=os.environ['CAU_LIBRARY_API_URL'],
    )


def create_notice_embed(notices: List[Dict]) -> Optional[Dict]:
    """Create a Discord embed dict from notice data."""
    if not notices:
        return None

    fields = []

    for notice in notices:
        field_name = f"[{notice['category']}] {notice['title']}"
        field_value = f"날짜: {notice['post_date']}\n"
        if notice.get('url'):
            field_value += f"[바로가기]({notice['url']})"

        # Discord embed field name limit is 256 chars, value limit is 1024 chars
        fields.append({
            "name": field_name[:256],
            "value": field_value[:1024],
            "inline": False
        })

    # Add Rainbow system links
    fields.append({
        "name": "🌈 레인보우 시스템",
        "value": (
            "[비교과 프로그램](https://rainbow.cau.ac.kr/site/reservation/lecture/lectureList"
            "?menuid=001002002&submode=lecture&reservegroupid=1)\n"
            "[외부 프로그램](https://rainbow.cau.ac.kr/site/program/board/basicboard/list"
            "?boardtypeid=16&menuid=001002003)"
        ),
        "inline": False
    })

    return {
        "title": "📢 새로운 공지사항이 있습니다",
        "color": DISCORD_EMBED_COLOR_BLUE,
        "fields": fields
    }


async def send_message_to_discord(config: BotConfig, all_notices: List[Dict]) -> bool:
    """Send notice message to Discord channel using HTTP API."""
    if not all_notices:
        logging.info("No notices to send")
        return True

    embed = create_notice_embed(all_notices)
    url = f"https://discord.com/api/v10/channels/{config.discord_channel_id}/messages"
    headers = {
        "Authorization": f"Bot {config.bot_token}",
        "Content-Type": "application/json"
    }
    payload = {"embeds": [embed]}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as response:
                if response.status in (200, 201):
                    logging.info(f"Successfully sent {len(all_notices)} notices to Discord")
                    return True
                else:
                    error_text = await response.text()
                    logging.error(f"Failed to send Discord message: {response.status} - {error_text}")
                    return False
    except Exception as e:
        logging.error(f"Error sending Discord message: {str(e)}")
        raise
