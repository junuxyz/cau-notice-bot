"""
Shared test fixtures and mock data.
All tests use mocked data - no actual servers are contacted.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.config import (
    BotConfig,
    CauNoticeSourceConfig,
    DiscordConfig,
    LibraryNoticeSourceConfig,
    SoftwareNoticeSourceConfig,
)

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
    return {"data": {"list": notices}}


def create_library_api_response(notices, success=True):
    """Create Library API response structure"""
    return {"success": success, "data": {"list": notices}}


def create_cau_notice(write_dt: str, subject: str, bbs_seq: str = "12345"):
    """Create a single CAU notice dict"""
    return {"WRITE_DT": write_dt, "SUBJECT": subject, "BBS_SEQ": bbs_seq}


def create_library_notice(date_created: str, title: str, notice_id: str = "12345"):
    """Create a single library notice dict"""
    return {"dateCreated": date_created, "title": title, "id": notice_id}


def create_sw_notice_list_html(rows):
    """Create a minimal software notice list HTML snippet."""
    body_rows = []
    for row in rows:
        body_rows.append(
            (
                "<tr>"
                "<td><span class='tag blue'>공지</span></td>"
                "<td class='pc-only'></td>"
                f"<td class='aleft'><a href='?nmode=view&code=oktomato_bbs05&uid={row['uid']}&offset=1'>{row['title']}</a></td>"
                "<td class='pc-only'>학부사무실</td>"
                f"<td class='pc-only'>{row['date']}</td>"
                "<td class='pc-only'>0</td>"
                "</tr>"
            )
        )

    return (
        "<html><body>"
        "<table class='table-basic'><tbody>"
        f"{''.join(body_rows)}"
        "</tbody></table>"
        "</body></html>"
    )


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def bot_config():
    """Mock BotConfig for testing"""
    return BotConfig(
        discord=DiscordConfig(
            bot_token="test_bot_token",
            channel_ids=["123456789012345678", "987654321098765432"],
        ),
        cau=CauNoticeSourceConfig(
            website_url="https://www.cau.ac.kr/cms/FR_CON/BoardView.do",
            api_url="https://www.cau.ac.kr/ajax/FR_SVC/BBSViewList2.do",
        ),
        library=LibraryNoticeSourceConfig(
            website_url="https://library.cau.ac.kr/guide/bulletins/notice",
            api_url="https://library.cau.ac.kr/pyxis-api/1/bulletin-boards/1/bulletins",
        ),
        software=SoftwareNoticeSourceConfig(
            notice_url="https://cse.cau.ac.kr/sub05/sub0501.php?offset=1&nmode=list&code=oktomato_bbs05",
            state_file=".state/sw_last_seen_uid.txt",
        ),
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
    mock_session.post = MagicMock(
        return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=mock_response),
            __aexit__=AsyncMock(return_value=None),
        )
    )

    return mock_session


@pytest.fixture
def mock_env():
    """Standard mock environment variables"""
    return {
        "DISCORD_BOT_TOKEN": "test_bot_token",
        "DISCORD_CHANNEL_IDS": "123456789012345678,987654321098765432",
        "CAU_WEBSITE_URL": "https://www.cau.ac.kr/cms/FR_CON/BoardView.do",
        "CAU_API_URL": "https://www.cau.ac.kr/ajax/FR_SVC/BBSViewList2.do",
        "CAU_LIBRARY_WEBSITE_URL": "https://library.cau.ac.kr/guide/bulletins/notice",
        "CAU_LIBRARY_API_URL": "https://library.cau.ac.kr/pyxis-api/1/bulletin-boards/1/bulletins",
        "CAU_SW_NOTICE_URL": "https://cse.cau.ac.kr/sub05/sub0501.php?offset=1&nmode=list&code=oktomato_bbs05",
        "CAU_SW_NOTICE_STATE_FILE": ".state/sw_last_seen_uid.txt",
    }
