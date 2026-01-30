"""
Shared test fixtures and mock data.
All tests use mocked data - no actual servers are contacted.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.bot_service import BotConfig

# =============================================================================
# DateTime Helpers
# =============================================================================

def create_kst_datetime(year, month, day, hour, minute, second=0):
    """Create a timezone-aware datetime in KST"""
    kst = timezone(timedelta(hours=9))
    return datetime(year, month, day, hour, minute, second, tzinfo=kst)


# =============================================================================
# Mock API Responses
# =============================================================================

def create_cau_api_response(notices):
    """Create CAU API response structure"""
    return {'data': {'list': notices}}


def create_library_api_response(notices, success=True):
    """Create Library API response structure"""
    return {'success': success, 'data': {'list': notices}}


def create_cau_notice(write_dt: str, subject: str, bbs_seq: str = '12345'):
    """Create a single CAU notice dict"""
    return {'WRITE_DT': write_dt, 'SUBJECT': subject, 'BBS_SEQ': bbs_seq}


def create_library_notice(date_created: str, title: str, notice_id: str = '12345'):
    """Create a single library notice dict"""
    return {'dateCreated': date_created, 'title': title, 'id': notice_id}


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def bot_config():
    """Mock BotConfig for testing"""
    return BotConfig(
        bot_token='test_bot_token',
        discord_channel_id='123456789012345678',
        cau_website_url='https://www.cau.ac.kr/cms/FR_CON/BoardView.do',
        cau_api_url='https://www.cau.ac.kr/ajax/FR_SVC/BBSViewList2.do',
        library_website_url='https://library.cau.ac.kr/guide/bulletins/notice',
        library_api_url='https://library.cau.ac.kr/pyxis-api/1/bulletin-boards/1/bulletins'
    )


@pytest.fixture
def mock_discord_session():
    """Create a mocked aiohttp session for Discord API success"""
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.text = AsyncMock(return_value='{"id": "123"}')

    mock_session = MagicMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)
    mock_session.post = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=mock_response),
        __aexit__=AsyncMock(return_value=None)
    ))

    return mock_session


@pytest.fixture
def mock_env():
    """Standard mock environment variables"""
    return {
        'DISCORD_BOT_TOKEN': 'test_bot_token',
        'DISCORD_CHANNEL_ID': '123456789012345678',
        'CAU_WEBSITE_URL': 'https://www.cau.ac.kr/cms/FR_CON/BoardView.do',
        'CAU_API_URL': 'https://www.cau.ac.kr/ajax/FR_SVC/BBSViewList2.do',
        'CAU_LIBRARY_WEBSITE_URL': 'https://library.cau.ac.kr/guide/bulletins/notice',
        'CAU_LIBRARY_API_URL': 'https://library.cau.ac.kr/pyxis-api/1/bulletin-boards/1/bulletins'
    }
