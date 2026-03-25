"""
Tests for main.py entry point.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.main import main
from tests.conftest import (
    create_cau_api_response,
    create_cau_notice,
    create_disu_notice_list_html,
    create_kst_datetime,
    create_library_api_response,
    create_library_notice,
    create_sw_notice_list_html,
)


def _mock_api_response(data):
    """Helper to create mock API response"""
    mock = MagicMock()
    mock.json.return_value = data
    mock.raise_for_status = MagicMock()
    return mock


def _mock_discord_session(status=200):
    """Helper to create mock Discord session"""
    mock_response = AsyncMock(status=status, text=AsyncMock(return_value="{}"))
    mock_session = MagicMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)
    mock_session.post = MagicMock(
        return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=mock_response),
            __aexit__=AsyncMock(return_value=None),
        )
    )
    return mock_session


def _mock_html_response(html: str):
    """Helper to create mock HTML response"""
    mock = MagicMock()
    mock.content = html.encode("utf-8")
    mock.raise_for_status = MagicMock()
    return mock


class TestMain:
    """Tests for main entry point function"""

    @pytest.mark.asyncio
    async def test_success_with_notices(self, mock_env):
        """Returns 0 when notices are sent successfully"""
        cau_response = _mock_api_response(
            create_cau_api_response(
                [create_cau_notice("2026-01-19 07:30:00", "CAU Notice")]
            )
        )
        sw_response = _mock_html_response(
            create_sw_notice_list_html(
                [
                    {"uid": 3002, "title": "SW Notice", "date": "2026.01.19"},
                ]
            )
        )
        sw_page2_response = _mock_html_response(create_sw_notice_list_html([]))
        library_response = _mock_api_response(
            create_library_api_response(
                [create_library_notice("2026-01-19 07:30:00", "Library Notice")]
            )
        )
        disu_response = _mock_html_response(create_disu_notice_list_html([]))

        with (
            patch.dict("os.environ", mock_env, clear=True),
            patch("src.services.get_korea_datetime") as mock_now,
            patch(
                "requests.get",
                side_effect=[
                    cau_response,
                    sw_response,
                    sw_page2_response,
                    library_response,
                    disu_response,
                ],
            ),
            patch("src.services.load_last_seen_uid", side_effect=[3001, None]),
            patch("src.services.save_last_seen_uid") as mock_save_uid,
            patch("aiohttp.ClientSession", return_value=_mock_discord_session()),
        ):
            mock_now.return_value = create_kst_datetime(2026, 1, 19, 15, 0)
            exit_code = await main()

        assert exit_code == 0
        mock_save_uid.assert_called_once_with(".state/sw_last_seen_uid.txt", 3002)

    @pytest.mark.asyncio
    async def test_success_no_notices(self, mock_env):
        """Returns 0 when no notices found (still successful)"""
        cau_response = _mock_api_response({"data": {"list": []}})
        sw_response = _mock_html_response(create_sw_notice_list_html([]))
        library_response = _mock_api_response({"success": True, "data": {"list": []}})
        disu_response = _mock_html_response(create_disu_notice_list_html([]))

        with (
            patch.dict("os.environ", mock_env, clear=True),
            patch(
                "requests.get",
                side_effect=[cau_response, sw_response, library_response, disu_response],
            ),
            patch("src.services.load_last_seen_uid", side_effect=[999, None]),
            patch("src.services.save_last_seen_uid") as mock_save_uid,
        ):
            exit_code = await main()

        assert exit_code == 0
        mock_save_uid.assert_not_called()

    @pytest.mark.asyncio
    async def test_missing_env_returns_1(self):
        """Returns 1 when environment variables are missing"""
        with patch.dict("os.environ", {}, clear=True):
            exit_code = await main()

        assert exit_code == 1

    @pytest.mark.asyncio
    async def test_api_error_returns_1(self, mock_env):
        """Returns 1 when API call fails"""
        with (
            patch.dict("os.environ", mock_env, clear=True),
            patch("requests.get", side_effect=Exception("Network error")),
        ):
            exit_code = await main()

        assert exit_code == 1

    @pytest.mark.asyncio
    async def test_discord_send_failure_returns_1(self, mock_env):
        """Returns 1 when Discord send fails"""
        cau_response = _mock_api_response(
            create_cau_api_response(
                [create_cau_notice("2026-01-19 07:30:00", "Notice")]
            )
        )
        sw_response = _mock_html_response(create_sw_notice_list_html([]))
        library_response = _mock_api_response({"success": True, "data": {"list": []}})
        disu_response = _mock_html_response(create_disu_notice_list_html([]))

        with (
            patch.dict("os.environ", mock_env, clear=True),
            patch("src.services.get_korea_datetime") as mock_now,
            patch(
                "requests.get",
                side_effect=[cau_response, sw_response, library_response, disu_response],
            ),
            patch(
                "aiohttp.ClientSession", return_value=_mock_discord_session(status=403)
            ),
        ):
            mock_now.return_value = create_kst_datetime(2026, 1, 19, 15, 0)
            exit_code = await main()

        assert exit_code == 1

    @pytest.mark.asyncio
    async def test_e2e_payload_sw_notice_matches_existing_field_format(self, mock_env):
        """SW notices should render with the same embed field format as other sources."""
        cau_response = _mock_api_response({"data": {"list": []}})
        sw_response = _mock_html_response(
            create_sw_notice_list_html(
                [
                    {"uid": 777, "title": "SW Formatter Test", "date": "2026.01.19"},
                ]
            )
        )
        sw_page2_response = _mock_html_response(create_sw_notice_list_html([]))
        library_response = _mock_api_response({"success": True, "data": {"list": []}})
        disu_response = _mock_html_response(create_disu_notice_list_html([]))

        mock_response = AsyncMock(status=200, text=AsyncMock(return_value="{}"))
        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.post = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_response),
                __aexit__=AsyncMock(return_value=None),
            )
        )

        with (
            patch.dict("os.environ", mock_env, clear=True),
            patch("src.services.get_korea_datetime") as mock_now,
            patch(
                "requests.get",
                side_effect=[
                    cau_response,
                    sw_response,
                    sw_page2_response,
                    library_response,
                    disu_response,
                ],
            ),
            patch("src.services.load_last_seen_uid", side_effect=[776, None]),
            patch("src.services.save_last_seen_uid"),
            patch("aiohttp.ClientSession", return_value=mock_session),
        ):
            mock_now.return_value = create_kst_datetime(2026, 1, 19, 15, 0)
            exit_code = await main()

        assert exit_code == 0
        sent_payload = mock_session.post.call_args.kwargs["json"]
        fields = sent_payload["embeds"][0]["fields"]
        sw_field = fields[0]

        assert sw_field["name"] == "[소프트웨어학과 공지] SW Formatter Test"
        assert sw_field["inline"] is False
        assert "날짜: 2026.01.19" in sw_field["value"]
        assert "[바로가기](" in sw_field["value"]

    @pytest.mark.asyncio
    async def test_initial_run_sends_only_latest_sw_notice_and_saves_uid(self, mock_env):
        """Initial run should send latest SW notice once and initialize state."""
        cau_response = _mock_api_response({"data": {"list": []}})
        sw_response = _mock_html_response(
            create_sw_notice_list_html(
                [
                    {"uid": 901, "title": "이전 SW 공지", "date": "2026.01.18"},
                    {"uid": 902, "title": "최신 SW 공지", "date": "2026.01.19"},
                ]
            )
        )
        library_response = _mock_api_response({"success": True, "data": {"list": []}})
        disu_response = _mock_html_response(create_disu_notice_list_html([]))

        mock_response = AsyncMock(status=200, text=AsyncMock(return_value="{}"))
        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.post = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_response),
                __aexit__=AsyncMock(return_value=None),
            )
        )

        with (
            patch.dict("os.environ", mock_env, clear=True),
            patch("src.services.get_korea_datetime") as mock_now,
            patch(
                "requests.get",
                side_effect=[cau_response, sw_response, library_response, disu_response],
            ),
            patch("src.services.load_last_seen_uid", side_effect=[None, None]),
            patch("src.services.save_last_seen_uid") as mock_save_uid,
            patch("aiohttp.ClientSession", return_value=mock_session),
        ):
            mock_now.return_value = create_kst_datetime(2026, 1, 19, 15, 0)
            exit_code = await main()

        assert exit_code == 0
        mock_save_uid.assert_called_once_with(".state/sw_last_seen_uid.txt", 902)
        sent_payload = mock_session.post.call_args.kwargs["json"]
        fields = sent_payload["embeds"][0]["fields"]
        sw_fields = [
            field
            for field in fields
            if field["name"].startswith("[소프트웨어학과 공지]")
        ]
        assert len(sw_fields) == 1
        assert sw_fields[0]["name"] == "[소프트웨어학과 공지] 최신 SW 공지"
        assert "uid=902" in sw_fields[0]["value"]
