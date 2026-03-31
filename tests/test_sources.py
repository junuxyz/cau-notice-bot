"""Tests for shared HTML notice sources."""

from unittest.mock import MagicMock, patch

import requests

from src.domain import SourceContext, build_daily_notice_window
from src.notice_check import check_disu_notices
from src.sources import DisuNoticeSource, NipaNoticeSource, SoftwareDeptNoticeSource
from tests.conftest import (
    create_disu_notice_list_html,
    create_kst_datetime,
    create_nipa_notice_list_html,
    create_sw_notice_list_html,
)


def _mock_html_response(html: str):
    mock = MagicMock()
    mock.content = html.encode("utf-8")
    mock.raise_for_status = MagicMock()
    return mock


def _source_context(state=None):
    return SourceContext(
        window=build_daily_notice_window(create_kst_datetime(2026, 3, 25, 9, 0)),
        state=state,
    )


class TestSharedCursorHtmlSources:
    def test_bootstraps_with_latest_notice_only(self):
        html = create_sw_notice_list_html(
            [
                {"uid": 2103, "title": "최신 공지", "date": "2026.03.07"},
                {"uid": 2102, "title": "이전 공지", "date": "2026.03.06"},
                {"uid": 2101, "title": "더 이전 공지", "date": "2026.03.05"},
            ]
        )

        source = SoftwareDeptNoticeSource(
            "https://cse.cau.ac.kr/sub05/sub0501.php?offset=1&nmode=list&code=oktomato_bbs05"
        )

        with patch("requests.get", return_value=_mock_html_response(html)):
            batch = source.fetch(_source_context(state=None))

        assert batch.latest_cursor == 2103
        assert [notice.title for notice in batch.notices] == ["최신 공지"]

    def test_returns_new_notices_sorted_oldest_first_across_pages(self):
        page1 = create_sw_notice_list_html(
            [
                {"uid": 1005, "title": "다섯 번째 공지", "date": "2026.03.09"},
                {"uid": 1004, "title": "네 번째 공지", "date": "2026.03.08"},
            ]
        )
        page2 = create_sw_notice_list_html(
            [
                {"uid": 1003, "title": "세 번째 공지", "date": "2026.03.07"},
                {"uid": 1002, "title": "두 번째 공지", "date": "2026.03.06"},
            ]
        )
        page3 = create_sw_notice_list_html(
            [
                {"uid": 1001, "title": "첫 번째 공지", "date": "2026.03.05"},
            ]
        )

        source = SoftwareDeptNoticeSource(
            "https://cse.cau.ac.kr/sub05/sub0501.php?offset=1&nmode=list&code=oktomato_bbs05"
        )

        with patch(
            "requests.get",
            side_effect=[
                _mock_html_response(page1),
                _mock_html_response(page2),
                _mock_html_response(page3),
            ],
        ):
            batch = source.fetch(_source_context(state=1002))

        assert batch.latest_cursor == 1005
        assert [notice.title for notice in batch.notices] == [
            "세 번째 공지",
            "네 번째 공지",
            "다섯 번째 공지",
        ]

    def test_returns_empty_batch_on_fetch_failure_without_advancing_cursor(self):
        page1 = create_sw_notice_list_html(
            [
                {"uid": 1005, "title": "다섯 번째 공지", "date": "2026.03.09"},
                {"uid": 1004, "title": "네 번째 공지", "date": "2026.03.08"},
            ]
        )

        source = SoftwareDeptNoticeSource(
            "https://cse.cau.ac.kr/sub05/sub0501.php?offset=1&nmode=list&code=oktomato_bbs05"
        )

        with patch(
            "requests.get",
            side_effect=[
                _mock_html_response(page1),
                requests.exceptions.Timeout(),
            ],
        ):
            batch = source.fetch(_source_context(state=1000))

        assert batch.notices == []
        assert batch.latest_cursor is None

    def test_strips_new_badge_text_from_software_titles(self):
        html = """
        <html><body>
        <table class='table-basic'><tbody>
        <tr>
          <td><span class='tag blue'>공지</span></td>
          <td class='pc-only'></td>
          <td class='aleft'>
            <a href='?nmode=view&code=oktomato_bbs05&uid=3336&offset=1'>
              2026년도 서울캠퍼스 예비군 훈련 안내
              <span class='tag new'>NEW</span>
            </a>
          </td>
          <td class='pc-only'>학부사무실</td>
          <td class='pc-only'>2026.03.20</td>
          <td class='pc-only'>0</td>
        </tr>
        </tbody></table>
        </body></html>
        """

        source = SoftwareDeptNoticeSource(
            "https://cse.cau.ac.kr/sub05/sub0501.php?offset=1&nmode=list&code=oktomato_bbs05"
        )

        with patch("requests.get", return_value=_mock_html_response(html)):
            batch = source.fetch(_source_context(state=3335))

        assert batch.notices[0].title == "2026년도 서울캠퍼스 예비군 훈련 안내"


class TestDisuNoticeSource:
    def test_filters_categories_and_paginates_until_relevant_notice_found(self):
        page1 = create_disu_notice_list_html(
            [
                {
                    "bbsidx": 5003,
                    "category": "강원대학교",
                    "title": "강원대 공지",
                    "date": "2026-03-24",
                },
                {
                    "bbsidx": 5002,
                    "category": "숭실대학교",
                    "title": "숭실대 공지",
                    "date": "2026-03-24",
                },
            ]
        )
        page2 = create_disu_notice_list_html(
            [
                {
                    "bbsidx": 5001,
                    "category": "중앙대학교",
                    "title": "중앙대 공지",
                    "date": "2026-03-23",
                },
                {
                    "bbsidx": 5000,
                    "category": "POLARIS",
                    "title": "POLARIS 공지",
                    "date": "2026-03-22",
                },
            ]
        )
        page3 = create_disu_notice_list_html([])

        source = DisuNoticeSource("https://www.disu.ac.kr/community/notice")

        with patch(
            "requests.get",
            side_effect=[
                _mock_html_response(page1),
                _mock_html_response(page2),
                _mock_html_response(page3),
            ],
        ):
            batch = source.fetch(_source_context(state=4999))

        assert batch.latest_cursor == 5003
        assert [notice.title for notice in batch.notices] == [
            "POLARIS 공지",
            "중앙대 공지",
        ]
        assert [notice.category for notice in batch.notices] == [
            "차세대반도체 공지 (POLARIS)",
            "차세대반도체 공지 (중앙대학교)",
        ]

    def test_check_disu_notices_uses_shared_source_logic(self):
        html = create_disu_notice_list_html(
            [
                {
                    "bbsidx": 8602,
                    "category": "강원대학교",
                    "title": "제외 공지",
                    "date": "2026-03-24",
                },
                {
                    "bbsidx": 8601,
                    "category": "중앙대학교",
                    "title": "포함 공지",
                    "date": "2026-03-23",
                },
            ]
        )

        with patch("requests.get", return_value=_mock_html_response(html)):
            notices, latest_bbsidx = check_disu_notices(
                "https://www.disu.ac.kr/community/notice",
                8600,
            )

        assert latest_bbsidx == 8602
        assert [notice["title"] for notice in notices] == ["포함 공지"]
        assert notices[0]["category"] == "차세대반도체 공지 (중앙대학교)"
        assert "bbsidx=8601" in notices[0]["url"]


class TestNipaNoticeSource:
    def test_bootstraps_with_latest_notice_only(self):
        html = create_nipa_notice_list_html(
            [
                {
                    "number": 385,
                    "ntt_no": 16626,
                    "title": "최신 NIPA 공고",
                    "date": "2026-03-30",
                },
                {
                    "number": 384,
                    "ntt_no": 16615,
                    "title": "이전 NIPA 공고",
                    "date": "2026-03-29",
                },
            ]
        )

        source = NipaNoticeSource("https://nipa.kr/home/2-2")

        with patch("requests.get", return_value=_mock_html_response(html)):
            batch = source.fetch(_source_context(state=None))

        assert batch.latest_cursor == 16626
        assert [notice.title for notice in batch.notices] == ["최신 NIPA 공고"]
        assert batch.notices[0].category == "NIPA 사업공고"
        assert batch.notices[0].url == "https://nipa.kr/home/2-2/16626"

    def test_returns_new_notices_sorted_oldest_first_across_pages(self):
        page1 = create_nipa_notice_list_html(
            [
                {
                    "number": 385,
                    "ntt_no": 16626,
                    "title": "세 번째 공고",
                    "date": "2026-03-30",
                },
                {
                    "number": 384,
                    "ntt_no": 16625,
                    "title": "두 번째 공고",
                    "date": "2026-03-29",
                },
            ]
        )
        page2 = create_nipa_notice_list_html(
            [
                {
                    "number": 383,
                    "ntt_no": 16624,
                    "title": "첫 번째 공고",
                    "date": "2026-03-28",
                },
            ]
        )

        source = NipaNoticeSource("https://nipa.kr/home/2-2")

        with patch(
            "requests.get",
            side_effect=[
                _mock_html_response(page1),
                _mock_html_response(page2),
                _mock_html_response(create_nipa_notice_list_html([])),
            ],
        ):
            batch = source.fetch(_source_context(state=16623))

        assert batch.latest_cursor == 16626
        assert [notice.title for notice in batch.notices] == [
            "첫 번째 공고",
            "두 번째 공고",
            "세 번째 공고",
        ]
