"""
Tests for bot_service.py - Discord message creation and sending.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.bot_service import (
    DISCORD_EMBED_COLOR_BLUE,
    create_notice_embed,
    load_config,
    send_message_to_discord,
)


class TestLoadConfig:
    """Tests for load_config function"""

    def test_load_config_success(self, mock_env):
        """Successfully loads config from environment variables"""
        with patch.dict("os.environ", mock_env, clear=True):
            config = load_config()

        assert config.bot_token == "test_bot_token"
        assert config.discord_channel_ids == [
            "123456789012345678",
            "987654321098765432",
        ]
        assert config.cau_website_url == "https://www.cau.ac.kr/cms/FR_CON/BoardView.do"
        assert config.cau_api_url == "https://www.cau.ac.kr/ajax/FR_SVC/BBSViewList2.do"
        assert (
            config.library_website_url
            == "https://library.cau.ac.kr/guide/bulletins/notice"
        )
        assert (
            config.library_api_url
            == "https://library.cau.ac.kr/pyxis-api/1/bulletin-boards/1/bulletins"
        )
        assert config.sw_notice_url.startswith(
            "https://cse.cau.ac.kr/sub05/sub0501.php"
        )
        assert config.sw_notice_state_file == ".state/sw_last_seen_uid.txt"
        assert config.disu_notice_url == "https://www.disu.ac.kr/community/notice"
        assert config.disu_notice_state_file == ".state/disu_last_seen_bbsidx.txt"

    def test_load_config_single_channel_id_success(self, mock_env):
        """Single channel ID in DISCORD_CHANNEL_IDS is accepted"""
        single_channel_env = dict(mock_env)
        single_channel_env["DISCORD_CHANNEL_IDS"] = "123456789012345678"

        with patch.dict("os.environ", single_channel_env, clear=True):
            config = load_config()

        assert config.discord_channel_ids == ["123456789012345678"]

    def test_load_config_channel_ids_filters_empty_tokens(self, mock_env):
        """Whitespace and empty tokens are removed from DISCORD_CHANNEL_IDS"""
        env_with_whitespace = dict(mock_env)
        env_with_whitespace["DISCORD_CHANNEL_IDS"] = (
            "123456789012345678, ,987654321098765432,"
        )

        with patch.dict("os.environ", env_with_whitespace, clear=True):
            config = load_config()

        assert config.discord_channel_ids == [
            "123456789012345678",
            "987654321098765432",
        ]

    def test_load_config_missing_env_raises_keyerror(self):
        """Missing environment variable raises KeyError (fail-fast)"""
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(KeyError) as exc_info:
                load_config()

        assert "DISCORD_BOT_TOKEN" in str(exc_info.value)

    def test_load_config_partial_env_raises_keyerror(self, mock_env):
        """Partial environment variables raise KeyError"""
        partial_env = {k: v for k, v in mock_env.items() if k != "CAU_API_URL"}

        with patch.dict("os.environ", partial_env, clear=True):
            with pytest.raises(KeyError) as exc_info:
                load_config()

        assert "CAU_API_URL" in str(exc_info.value)

    def test_load_config_missing_channel_ids_raises_keyerror(self, mock_env):
        """DISCORD_CHANNEL_IDS is required"""
        env_without_channel_ids = {
            k: v for k, v in mock_env.items() if k != "DISCORD_CHANNEL_IDS"
        }

        with patch.dict("os.environ", env_without_channel_ids, clear=True):
            with pytest.raises(KeyError) as exc_info:
                load_config()

        assert "DISCORD_CHANNEL_IDS" in str(exc_info.value)


class TestCreateNoticeEmbed:
    """Tests for create_notice_embed function"""

    def test_returns_none_for_empty_notices(self):
        """Empty list returns None"""
        assert create_notice_embed([]) is None

    def test_creates_embed_with_correct_structure(self):
        """Single notice creates valid embed dict"""
        notices = [
            {
                "title": "Test Notice",
                "post_date": "2026-01-19 10:00",
                "category": "CAU 공지",
                "url": "https://example.com",
            }
        ]

        embed = create_notice_embed(notices)

        assert embed["title"] == "📢 새로운 공지사항이 있습니다"
        assert embed["color"] == DISCORD_EMBED_COLOR_BLUE
        assert len(embed["fields"]) == 2  # 1 notice + rainbow links

    def test_includes_notice_fields(self):
        """Embed contains notice data in fields"""
        notices = [
            {
                "title": "Test Notice",
                "post_date": "2026-01-19 10:00",
                "category": "CAU 공지",
                "url": "https://example.com",
            }
        ]

        embed = create_notice_embed(notices)
        field = embed["fields"][0]

        assert "CAU 공지" in field["name"]
        assert "Test Notice" in field["name"]
        assert "2026-01-19 10:00" in field["value"]
        assert "바로가기" in field["value"]

    def test_includes_rainbow_links(self):
        """Embed always includes Rainbow system links"""
        notices = [
            {
                "title": "Test",
                "post_date": "2026-01-19",
                "category": "CAU 공지",
                "url": None,
            }
        ]

        embed = create_notice_embed(notices)
        rainbow_field = embed["fields"][-1]

        assert "레인보우" in rainbow_field["name"]
        assert "rainbow.cau.ac.kr" in rainbow_field["value"]

    def test_handles_notice_without_url(self):
        """Notice without URL omits link"""
        notices = [
            {
                "title": "Test",
                "post_date": "2026-01-19",
                "category": "CAU 공지",
                "url": None,
            }
        ]

        embed = create_notice_embed(notices)

        assert "바로가기" not in embed["fields"][0]["value"]

    def test_truncates_long_titles(self):
        """Long titles are truncated to 256 chars"""
        notices = [
            {
                "title": "A" * 300,
                "post_date": "2026-01-19",
                "category": "CAU 공지",
                "url": None,
            }
        ]

        embed = create_notice_embed(notices)

        assert len(embed["fields"][0]["name"]) <= 256


class TestSendMessageToDiscord:
    """Tests for send_message_to_discord function"""

    @pytest.mark.asyncio
    async def test_success(self, bot_config, mock_discord_session):
        """Successful send returns True"""
        notices = [
            {
                "title": "Test",
                "post_date": "2026-01-19",
                "category": "CAU 공지",
                "url": None,
            }
        ]

        with patch("aiohttp.ClientSession", return_value=mock_discord_session):
            result = await send_message_to_discord(bot_config, notices)

        assert result is True
        assert mock_discord_session.post.call_count == len(
            bot_config.discord_channel_ids
        )

    @pytest.mark.asyncio
    async def test_empty_notices_returns_true(self, bot_config):
        """Empty notices returns True without sending"""
        result = await send_message_to_discord(bot_config, [])
        assert result is True

    @pytest.mark.asyncio
    async def test_api_error_returns_false(self, bot_config):
        """API error returns False"""
        mock_response = AsyncMock(status=403, text=AsyncMock(return_value="Forbidden"))
        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.post = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_response),
                __aexit__=AsyncMock(return_value=None),
            )
        )

        notices = [
            {
                "title": "Test",
                "post_date": "2026-01-19",
                "category": "CAU 공지",
                "url": None,
            }
        ]

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await send_message_to_discord(bot_config, notices)

        assert result is False

    @pytest.mark.asyncio
    async def test_network_error_returns_false(self, bot_config):
        """Network errors return False"""
        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.post = MagicMock(side_effect=Exception("Network error"))

        notices = [
            {
                "title": "Test",
                "post_date": "2026-01-19",
                "category": "CAU 공지",
                "url": None,
            }
        ]

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await send_message_to_discord(bot_config, notices)

        assert result is False
