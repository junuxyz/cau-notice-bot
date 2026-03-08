"""
Tests for notice_check.py - Notice fetching, parsing, and time filtering.
"""

from unittest.mock import MagicMock, patch

import pytest
import requests

from src.notice_check import (
    check_cau_notices,
    check_library_notices,
    check_notices,
    check_sw_notices,
    is_notice_in_time_range,
    load_last_seen_uid,
    save_last_seen_uid,
)
from tests.conftest import (
    create_cau_api_response,
    create_cau_notice,
    create_kst_datetime,
    create_library_api_response,
    create_library_notice,
    create_sw_notice_list_html,
)


class TestIsNoticeInTimeRange:
    """Tests for time range filtering (yesterday 8AM to today 8AM)"""

    @pytest.mark.parametrize(
        "current,notice,expected",
        [
            # Notice at boundary (today 8:00 AM) - included
            ((2024, 3, 21, 15, 0), (2024, 3, 21, 8, 0), True),
            # Notice just before end (today 7:59 AM) - included
            ((2024, 3, 21, 15, 0), (2024, 3, 21, 7, 59), True),
            # Notice at start boundary (yesterday 8:00 AM) - included
            ((2024, 3, 21, 15, 0), (2024, 3, 20, 8, 0), True),
            # Notice before start (yesterday 7:59 AM) - excluded
            ((2024, 3, 21, 15, 0), (2024, 3, 20, 7, 59), False),
            # Notice after end (today 8:01 AM) - excluded
            ((2024, 3, 21, 15, 0), (2024, 3, 21, 8, 1), False),
        ],
    )
    def test_time_range_boundaries(self, current, notice, expected):
        """Test notice filtering at time boundaries"""
        with patch("src.notice_check.get_korea_datetime") as mock_now:
            mock_now.return_value = create_kst_datetime(*current)
            notice_dt = create_kst_datetime(*notice)
            assert is_notice_in_time_range(notice_dt) == expected


class TestCheckCauNotices:
    """Tests for CAU notice fetching"""

    def _mock_response(self, data):
        """Helper to create mock response"""
        mock = MagicMock()
        mock.json.return_value = data
        mock.raise_for_status = MagicMock()
        return mock

    def test_parses_notices_correctly(self):
        """Notices within time range are parsed correctly"""
        response_data = create_cau_api_response(
            [create_cau_notice("2024-03-21 07:30:00", "Test Notice", "123")]
        )

        with (
            patch("src.notice_check.get_korea_datetime") as mock_now,
            patch("requests.get", return_value=self._mock_response(response_data)),
        ):
            mock_now.return_value = create_kst_datetime(2024, 3, 21, 15, 0)

            notices = check_cau_notices("https://cau.ac.kr", "https://api.cau.ac.kr")

        assert len(notices) == 1
        assert notices[0]["title"] == "Test Notice"
        assert notices[0]["category"] == "CAU 공지"
        assert "BBS_SEQ=123" in notices[0]["url"]

    def test_filters_out_of_range_notices(self):
        """Notices outside time range are filtered"""
        response_data = create_cau_api_response(
            [
                create_cau_notice("2024-03-21 07:30:00", "In Range"),
                create_cau_notice("2024-03-19 10:00:00", "Out of Range"),
            ]
        )

        with (
            patch("src.notice_check.get_korea_datetime") as mock_now,
            patch("requests.get", return_value=self._mock_response(response_data)),
        ):
            mock_now.return_value = create_kst_datetime(2024, 3, 21, 15, 0)

            notices = check_cau_notices("https://cau.ac.kr", "https://api.cau.ac.kr")

        assert len(notices) == 1
        assert notices[0]["title"] == "In Range"

    def test_returns_chronological_order(self):
        """Notices are sorted oldest first"""
        response_data = create_cau_api_response(
            [
                create_cau_notice("2024-03-21 07:45:00", "Later"),
                create_cau_notice("2024-03-21 07:30:00", "Earlier"),
            ]
        )

        with (
            patch("src.notice_check.get_korea_datetime") as mock_now,
            patch("requests.get", return_value=self._mock_response(response_data)),
        ):
            mock_now.return_value = create_kst_datetime(2024, 3, 21, 15, 0)

            notices = check_cau_notices("https://cau.ac.kr", "https://api.cau.ac.kr")

        assert notices[0]["title"] == "Earlier"
        assert notices[1]["title"] == "Later"

    def test_handles_empty_response(self):
        """Empty API response returns empty list"""
        with patch(
            "requests.get", return_value=self._mock_response({"data": {"list": []}})
        ):
            notices = check_cau_notices("https://cau.ac.kr", "https://api.cau.ac.kr")

        assert notices == []

    def test_handles_malformed_response(self):
        """Malformed API response returns empty list"""
        with patch("requests.get", return_value=self._mock_response({"data": None})):
            notices = check_cau_notices("https://cau.ac.kr", "https://api.cau.ac.kr")

        assert notices == []


class TestCheckLibraryNotices:
    """Tests for library notice fetching"""

    def _mock_response(self, data):
        """Helper to create mock response"""
        mock = MagicMock()
        mock.json.return_value = data
        mock.raise_for_status = MagicMock()
        return mock

    def test_parses_notices_correctly(self):
        """Library notices are parsed correctly"""
        response_data = create_library_api_response(
            [create_library_notice("2024-03-21 07:30:00", "Library Notice", "456")]
        )

        with (
            patch("src.notice_check.get_korea_datetime") as mock_now,
            patch("requests.get", return_value=self._mock_response(response_data)),
        ):
            mock_now.return_value = create_kst_datetime(2024, 3, 21, 15, 0)

            notices = check_library_notices(
                "https://library.cau.ac.kr", "https://api.library"
            )

        assert len(notices) == 1
        assert notices[0]["title"] == "Library Notice"
        assert notices[0]["category"] == "학술정보원 공지"
        assert notices[0]["url"].endswith("/456")

    def test_handles_failed_response(self):
        """Failed API response (success=False) returns empty list"""
        with patch(
            "requests.get", return_value=self._mock_response({"success": False})
        ):
            notices = check_library_notices(
                "https://library.cau.ac.kr", "https://api.library"
            )

        assert notices == []

    def test_handles_timeout(self):
        """Timeout returns empty list"""
        with patch("requests.get", side_effect=requests.exceptions.Timeout):
            notices = check_library_notices(
                "https://library.cau.ac.kr", "https://api.library"
            )

        assert notices == []

    def test_handles_connection_error(self):
        """Connection error returns empty list"""
        with patch("requests.get", side_effect=requests.exceptions.ConnectionError):
            notices = check_library_notices(
                "https://library.cau.ac.kr", "https://api.library"
            )

        assert notices == []


class TestCheckNotices:
    """Tests for combined notice checking"""

    def test_returns_tuple_of_two_lists(self, bot_config):
        """Returns (cau_notices, library_notices, sw_latest_uid) tuple"""
        mock_cau = MagicMock()
        mock_cau.json.return_value = {"data": {"list": []}}
        mock_cau.raise_for_status = MagicMock()

        mock_library = MagicMock()
        mock_library.json.return_value = {"success": True, "data": {"list": []}}
        mock_library.raise_for_status = MagicMock()

        mock_sw = MagicMock()
        mock_sw.content = create_sw_notice_list_html([]).encode("utf-8")
        mock_sw.raise_for_status = MagicMock()

        with (
            patch("requests.get", side_effect=[mock_cau, mock_sw, mock_library]),
            patch("src.notice_check.load_last_seen_uid", return_value=123),
        ):
            result = check_notices(bot_config)

        assert isinstance(result, tuple)
        assert len(result) == 3
        assert isinstance(result[0], list)
        assert isinstance(result[1], list)
        assert result[2] is None


class TestSwNoticeState:
    """Tests for software notice state persistence."""

    def test_load_last_seen_uid_returns_none_when_missing(self, tmp_path):
        missing_path = tmp_path / "missing_uid.txt"
        assert load_last_seen_uid(str(missing_path)) is None

    def test_save_and_load_last_seen_uid(self, tmp_path):
        state_path = tmp_path / "state" / "sw_uid.txt"
        save_last_seen_uid(str(state_path), 456)
        assert state_path.exists()
        assert load_last_seen_uid(str(state_path)) == 456


class TestCheckSwNotices:
    """Tests for software department notice scraping."""

    def _mock_html_response(self, html: str):
        mock = MagicMock()
        mock.content = html.encode("utf-8")
        mock.raise_for_status = MagicMock()
        return mock

    def test_returns_new_notices_with_expected_format(self):
        html = create_sw_notice_list_html(
            [
                {"uid": 1003, "title": "세 번째 공지", "date": "2026.03.07"},
                {"uid": 1002, "title": "두 번째 공지", "date": "2026.03.06"},
                {"uid": 1001, "title": "첫 번째 공지", "date": "2026.03.05"},
            ]
        )

        with patch("requests.get", return_value=self._mock_html_response(html)):
            notices, latest_uid = check_sw_notices(
                "https://cse.cau.ac.kr/sub05/sub0501.php", 1001
            )

        assert latest_uid == 1003
        assert [notice["title"] for notice in notices] == [
            "두 번째 공지",
            "세 번째 공지",
        ]
        for notice in notices:
            assert set(notice.keys()) == {"title", "post_date", "category", "url"}
            assert notice["category"] == "소프트웨어학과 공지"
            assert notice["post_date"].count(".") == 2
            assert "nmode=view" in notice["url"]
            assert "uid=" in notice["url"]

    def test_initial_run_returns_latest_notice_and_sets_latest_uid(self):
        html = create_sw_notice_list_html(
            [
                {"uid": 1100, "title": "초기화 대상 공지", "date": "2026.03.07"},
            ]
        )

        with patch("requests.get", return_value=self._mock_html_response(html)):
            notices, latest_uid = check_sw_notices(
                "https://cse.cau.ac.kr/sub05/sub0501.php", None
            )

        assert len(notices) == 1
        assert notices[0]["title"] == "초기화 대상 공지"
        assert notices[0]["category"] == "소프트웨어학과 공지"
        assert notices[0]["post_date"] == "2026.03.07"
        assert "uid=1100" in notices[0]["url"]
        assert latest_uid == 1100

    def test_initial_run_returns_only_latest_notice_when_multiple_exist(self):
        html = create_sw_notice_list_html(
            [
                {"uid": 2103, "title": "최신 공지", "date": "2026.03.07"},
                {"uid": 2102, "title": "이전 공지", "date": "2026.03.06"},
                {"uid": 2101, "title": "더 이전 공지", "date": "2026.03.05"},
            ]
        )

        with patch("requests.get", return_value=self._mock_html_response(html)):
            notices, latest_uid = check_sw_notices(
                "https://cse.cau.ac.kr/sub05/sub0501.php", None
            )

        assert len(notices) == 1
        assert notices[0]["title"] == "최신 공지"
        assert "uid=2103" in notices[0]["url"]
        assert latest_uid == 2103

    def test_handles_timeout(self):
        with patch("requests.get", side_effect=requests.exceptions.Timeout):
            notices, latest_uid = check_sw_notices(
                "https://cse.cau.ac.kr/sub05/sub0501.php", 1000
            )

        assert notices == []
        assert latest_uid is None

    def test_uses_bytes_parsing_to_prevent_mojibake(self):
        original_title = "대학원 개설과목 <고급알고리즘> 강의실 변경 안내"
        html = create_sw_notice_list_html(
            [{"uid": 1400, "title": original_title, "date": "2026.03.07"}]
        )

        # Simulate requests.text mojibake when charset header is missing.
        bad_text = html.encode("utf-8").decode("latin-1")
        mock = MagicMock()
        mock.text = bad_text
        mock.content = html.encode("utf-8")
        mock.raise_for_status = MagicMock()

        with patch("requests.get", return_value=mock):
            notices, latest_uid = check_sw_notices(
                "https://cse.cau.ac.kr/sub05/sub0501.php", 1300
            )

        assert latest_uid == 1400
        assert notices[0]["title"] == original_title
