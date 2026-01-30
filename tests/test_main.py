"""
Tests for main.py entry point.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.main import main
from tests.conftest import (
    create_cau_api_response,
    create_cau_notice,
    create_kst_datetime,
    create_library_api_response,
    create_library_notice,
)


def _mock_api_response(data):
    """Helper to create mock API response"""
    mock = MagicMock()
    mock.json.return_value = data
    mock.raise_for_status = MagicMock()
    return mock


def _mock_discord_session(status=200):
    """Helper to create mock Discord session"""
    mock_response = AsyncMock(status=status, text=AsyncMock(return_value='{}'))
    mock_session = MagicMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)
    mock_session.post = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=mock_response),
        __aexit__=AsyncMock(return_value=None)
    ))
    return mock_session


class TestMain:
    """Tests for main entry point function"""

    @pytest.mark.asyncio
    async def test_success_with_notices(self, mock_env):
        """Returns 0 when notices are sent successfully"""
        cau_response = _mock_api_response(create_cau_api_response([
            create_cau_notice('2026-01-19 07:30:00', 'CAU Notice')
        ]))
        library_response = _mock_api_response(create_library_api_response([
            create_library_notice('2026-01-19 07:30:00', 'Library Notice')
        ]))

        with patch.dict('os.environ', mock_env, clear=True), \
             patch('src.notice_check.get_korea_datetime') as mock_now, \
             patch('requests.get', side_effect=[cau_response, library_response]), \
             patch('aiohttp.ClientSession', return_value=_mock_discord_session()):

            mock_now.return_value = create_kst_datetime(2026, 1, 19, 15, 0)
            exit_code = await main()

        assert exit_code == 0

    @pytest.mark.asyncio
    async def test_success_no_notices(self, mock_env):
        """Returns 0 when no notices found (still successful)"""
        cau_response = _mock_api_response({'data': {'list': []}})
        library_response = _mock_api_response({'success': True, 'data': {'list': []}})

        with patch.dict('os.environ', mock_env, clear=True), \
             patch('requests.get', side_effect=[cau_response, library_response]):

            exit_code = await main()

        assert exit_code == 0

    @pytest.mark.asyncio
    async def test_missing_env_returns_1(self):
        """Returns 1 when environment variables are missing"""
        with patch.dict('os.environ', {}, clear=True):
            exit_code = await main()

        assert exit_code == 1

    @pytest.mark.asyncio
    async def test_api_error_returns_1(self, mock_env):
        """Returns 1 when API call fails"""
        with patch.dict('os.environ', mock_env, clear=True), \
             patch('requests.get', side_effect=Exception("Network error")):

            exit_code = await main()

        assert exit_code == 1

    @pytest.mark.asyncio
    async def test_discord_send_failure_returns_1(self, mock_env):
        """Returns 1 when Discord send fails"""
        cau_response = _mock_api_response(create_cau_api_response([
            create_cau_notice('2026-01-19 07:30:00', 'Notice')
        ]))
        library_response = _mock_api_response({'success': True, 'data': {'list': []}})

        with patch.dict('os.environ', mock_env, clear=True), \
             patch('src.notice_check.get_korea_datetime') as mock_now, \
             patch('requests.get', side_effect=[cau_response, library_response]), \
             patch('aiohttp.ClientSession', return_value=_mock_discord_session(status=403)):

            mock_now.return_value = create_kst_datetime(2026, 1, 19, 15, 0)
            exit_code = await main()

        assert exit_code == 1
