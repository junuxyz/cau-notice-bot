"""Notice source adapters."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Optional, Protocol
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

import requests
from bs4 import BeautifulSoup, Tag

from src.domain import KST, Notice, NoticeBatch, SourceContext

DISU_ALLOWED_CATEGORIES = frozenset({"중앙대학교", "POLARIS"})


class NoticeSource(Protocol):
    def fetch(self, context: SourceContext) -> NoticeBatch:
        """Fetch notices for the given execution context."""


@dataclass(frozen=True)
class ParsedCursorNoticeRow:
    cursor: Optional[int]
    notice: Optional[Notice]


PageUrlBuilder = Callable[[int], str]
RowParser = Callable[[Tag, str], Optional[ParsedCursorNoticeRow]]


class CauApiNoticeSource:
    def __init__(self, website_url: str, api_url: str):
        self.website_url = website_url
        self.api_url = api_url

    def fetch(self, context: SourceContext) -> NoticeBatch:
        params = {"SITE_NO": "2", "BOARD_SEQ": "4"}
        res = requests.get(self.api_url, params=params)
        res.raise_for_status()

        data = res.json()
        data_section = data.get("data") if data else None
        notice_list = data_section.get("list", []) if data_section else []

        notices: list[Notice] = []
        for notice in notice_list:
            try:
                notice_datetime = datetime.strptime(
                    notice["WRITE_DT"].split(".")[0], "%Y-%m-%d %H:%M:%S"
                ).replace(tzinfo=KST)

                if context.window.contains(notice_datetime):
                    url_params = {
                        "MENU_ID": "100",
                        "CONTENTS_NO": "1",
                        "SITE_NO": "2",
                        "BOARD_SEQ": "4",
                        "BBS_SEQ": notice.get("BBS_SEQ", ""),
                    }
                    notices.append(
                        Notice(
                            title=notice.get("SUBJECT", ""),
                            post_date=notice_datetime.strftime("%Y-%m-%d %H:%M"),
                            category="CAU 공지",
                            url=f"{self.website_url}?{urlencode(url_params)}",
                            source="cau",
                        )
                    )
            except Exception as exc:
                logging.error(f"Error while processing individual CAU notice: {exc}")

        notices.sort(key=lambda notice: notice.post_date)
        return NoticeBatch(notices=notices)


class LibraryNoticeSource:
    def __init__(self, website_url: str, api_url: str):
        self.website_url = website_url
        self.api_url = api_url

    def fetch(self, context: SourceContext) -> NoticeBatch:
        try:
            res = requests.get(self.api_url, timeout=10)
            res.raise_for_status()
            data = res.json()
        except Exception as exc:
            logging.error(f"Error while fetching library notices: {exc}")
            return NoticeBatch(notices=[])

        notices: list[Notice] = []
        if data.get("success") and data.get("data", {}).get("list"):
            for notice in data["data"]["list"]:
                try:
                    notice_datetime = datetime.strptime(
                        notice["dateCreated"], "%Y-%m-%d %H:%M:%S"
                    ).replace(tzinfo=KST)

                    if context.window.contains(notice_datetime):
                        notices.append(
                            Notice(
                                title=notice.get("title", ""),
                                post_date=notice_datetime.strftime("%Y-%m-%d %H:%M"),
                                category="학술정보원 공지",
                                url=f"{self.website_url}/{notice['id']}",
                                source="library",
                            )
                        )
                except Exception as exc:
                    logging.error(
                        f"Error while processing individual library notice: {exc}"
                    )

        notices.sort(key=lambda notice: notice.post_date)
        return NoticeBatch(notices=notices)


class SoftwareDeptNoticeSource:
    def __init__(self, notice_url: str):
        self.notice_url = notice_url
        self._source = CursorHtmlNoticeSource(
            source_name="software department notices",
            build_page_url=lambda page: _replace_query_params(
                notice_url,
                {"offset": str(page)},
            ),
            row_selector="table.table-basic tbody tr",
            row_parser=self._parse_row,
        )

    def fetch(self, context: SourceContext) -> NoticeBatch:
        if not self.notice_url:
            return NoticeBatch(notices=[])

        return self._source.fetch(context)

    def _parse_row(self, row: Tag, page_url: str) -> Optional[ParsedCursorNoticeRow]:
        title_link = row.select_one("td.aleft a")
        if not title_link:
            return None

        uid = _extract_query_int(title_link.get("href", ""), "uid")
        if uid is None:
            return None

        title = _extract_software_notice_title(title_link)
        date_match = re.search(r"\d{4}\.\d{2}\.\d{2}", row.get_text(" ", strip=True))
        post_date = date_match.group(0) if date_match else ""

        return ParsedCursorNoticeRow(
            cursor=uid,
            notice=Notice(
                title=title,
                post_date=post_date,
                category="소프트웨어학과 공지",
                url=urljoin(page_url, title_link.get("href", "")),
                source="software",
                source_id=uid,
            ),
        )


class DisuNoticeSource:
    def __init__(self, notice_url: str):
        self.notice_url = notice_url
        self._source = CursorHtmlNoticeSource(
            source_name="DISU notices",
            build_page_url=lambda page: _replace_query_params(
                notice_url,
                {"page": str(page)},
            ),
            row_selector="table.fixwidth tbody tr",
            row_parser=self._parse_row,
        )

    def fetch(self, context: SourceContext) -> NoticeBatch:
        if not self.notice_url:
            return NoticeBatch(notices=[])

        return self._source.fetch(context)

    def _parse_row(self, row: Tag, page_url: str) -> Optional[ParsedCursorNoticeRow]:
        cells = row.select("td")
        if len(cells) < 4:
            return None

        title_link = row.select_one("td.title a")
        if not title_link:
            return None

        bbsidx = _extract_query_int(title_link.get("href", ""), "bbsidx")
        if bbsidx is None:
            return None

        category = _normalize_html_text(cells[1].get_text(separator=" ", strip=True))
        if not category:
            return ParsedCursorNoticeRow(cursor=bbsidx, notice=None)

        if category not in DISU_ALLOWED_CATEGORIES:
            return ParsedCursorNoticeRow(cursor=bbsidx, notice=None)

        title = _normalize_html_text(title_link.get_text(separator=" ", strip=True))
        date_cell = row.select_one("td.text-center.hidden-xs-down.FS12")
        post_date = (
            _normalize_html_text(date_cell.get_text(separator=" ", strip=True))
            if date_cell
            else ""
        )

        return ParsedCursorNoticeRow(
            cursor=bbsidx,
            notice=Notice(
                title=title,
                post_date=post_date,
                category=f"차세대반도체 공지 ({category})",
                url=urljoin(page_url, title_link.get("href", "")),
                source="disu",
                source_id=bbsidx,
            ),
        )


class NipaNoticeSource:
    def __init__(self, notice_url: str):
        self.notice_url = notice_url
        self._source = CursorHtmlNoticeSource(
            source_name="NIPA notices",
            build_page_url=lambda page: _replace_query_params(
                notice_url,
                {"curPage": str(page)},
            ),
            row_selector="table.tbgg tbody tr",
            row_parser=self._parse_row,
        )

    def fetch(self, context: SourceContext) -> NoticeBatch:
        if not self.notice_url:
            return NoticeBatch(notices=[])

        return self._source.fetch(context)

    def _parse_row(self, row: Tag, page_url: str) -> Optional[ParsedCursorNoticeRow]:
        title_link = row.select_one("td.tl a")
        if not title_link:
            return None

        notice_id = _extract_path_int(title_link.get("href", ""))
        if notice_id is None:
            return None

        title = _normalize_html_text(title_link.get_text(separator=" ", strip=True))
        date_cell = row.select("td")[-1] if row.select("td") else None
        post_date = (
            _normalize_html_text(date_cell.get_text(separator=" ", strip=True))
            if date_cell
            else ""
        )

        return ParsedCursorNoticeRow(
            cursor=notice_id,
            notice=Notice(
                title=title,
                post_date=post_date,
                category="NIPA 사업공고",
                url=urljoin(page_url, title_link.get("href", "")),
                source="nipa",
                source_id=notice_id,
            ),
        )


class EventUsNoticeSource:
    def __init__(self, notice_url: str):
        self.notice_url = notice_url

    def fetch(self, context: SourceContext) -> NoticeBatch:
        if not self.notice_url:
            return NoticeBatch(notices=[])

        try:
            res = requests.get(self.notice_url, timeout=10)
            res.raise_for_status()
        except Exception as exc:
            logging.error("Failed to fetch EventUs notices: %s", exc)
            return NoticeBatch(notices=[], latest_cursor=None)

        html = res.text
        if not isinstance(html, str):
            html = res.content.decode("utf-8", errors="ignore")

        match = re.search(
            r"const eventListJson = `(?P<payload>.*?)`;",
            html,
            re.DOTALL,
        )
        if not match:
            logging.error("Failed to locate embedded EventUs event list JSON.")
            return NoticeBatch(notices=[], latest_cursor=None)

        try:
            payload = json.loads(match.group("payload"))
        except json.JSONDecodeError as exc:
            logging.error("Failed to parse EventUs event list JSON: %s", exc)
            return NoticeBatch(notices=[], latest_cursor=None)

        event_rows = [
            event
            for group in payload
            for event in group.get("list", [])
            if isinstance(event, dict)
        ]
        if not event_rows:
            return NoticeBatch(notices=[], latest_cursor=None)

        parsed_events = [
            parsed_event
            for event in event_rows
            if (parsed_event := self._parse_event(event)) is not None
        ]
        if not parsed_events:
            return NoticeBatch(notices=[], latest_cursor=None)

        latest_cursor = max(
            parsed_event.cursor for parsed_event in parsed_events if parsed_event.cursor
        )
        last_seen_cursor = context.state

        if last_seen_cursor is None:
            latest_event = max(
                parsed_events, key=lambda parsed_event: parsed_event.cursor
            )
            return NoticeBatch(
                notices=[latest_event.notice], latest_cursor=latest_cursor
            )

        notices = [
            parsed_event.notice
            for parsed_event in sorted(
                parsed_events, key=lambda parsed_event: parsed_event.cursor
            )
            if parsed_event.cursor > last_seen_cursor
        ]
        return NoticeBatch(notices=notices, latest_cursor=latest_cursor)

    def _parse_event(self, event: dict) -> Optional[ParsedCursorNoticeRow]:
        raw_id = event.get("Id")
        if raw_id is None:
            return None

        try:
            event_id = int(str(raw_id))
        except ValueError:
            return None

        title = _normalize_html_text(str(event.get("Title", "")))
        if not title:
            return None

        created_at = _parse_eventus_date(event.get("CreatedDate"))
        event_url = urljoin(self.notice_url.rstrip("/") + "/", str(event_id))
        event_type = _normalize_html_text(str(event.get("EventType", "")))
        category = "SqueezeBits 행사"
        if event_type:
            category = f"SqueezeBits 행사 ({event_type})"

        return ParsedCursorNoticeRow(
            cursor=event_id,
            notice=Notice(
                title=title,
                post_date=created_at.strftime("%Y-%m-%d %H:%M") if created_at else "",
                category=category,
                url=event_url,
                source="eventus",
                source_id=event_id,
            ),
        )


class CursorHtmlNoticeSource:
    def __init__(
        self,
        source_name: str,
        build_page_url: PageUrlBuilder,
        row_selector: str,
        row_parser: RowParser,
        max_pages: int = 10,
    ):
        self.source_name = source_name
        self.build_page_url = build_page_url
        self.row_selector = row_selector
        self.row_parser = row_parser
        self.max_pages = max_pages

    def fetch(self, context: SourceContext) -> NoticeBatch:
        last_seen_cursor = context.state
        collected_notices: dict[int, Notice] = {}
        latest_cursor: Optional[int] = None

        for page in range(1, self.max_pages + 1):
            page_url = self.build_page_url(page)
            rows = self._fetch_rows(page_url)
            if rows is None:
                return NoticeBatch(notices=[], latest_cursor=None)
            if not rows:
                break

            parsed_rows = [
                parsed_row
                for row in rows
                if (parsed_row := self.row_parser(row, page_url)) is not None
            ]

            page_cursors = [
                parsed_row.cursor
                for parsed_row in parsed_rows
                if parsed_row.cursor is not None
            ]
            if not page_cursors:
                continue

            page_latest_cursor = max(page_cursors)
            latest_cursor = (
                page_latest_cursor
                if latest_cursor is None
                else max(latest_cursor, page_latest_cursor)
            )

            eligible_rows = [
                parsed_row
                for parsed_row in parsed_rows
                if parsed_row.notice is not None and parsed_row.cursor is not None
            ]

            if last_seen_cursor is None:
                if eligible_rows:
                    logging.info(
                        "%s state not found; sending latest notice and initializing state.",
                        self.source_name.capitalize(),
                    )
                    latest_notice = max(
                        eligible_rows,
                        key=lambda parsed_row: parsed_row.cursor or 0,
                    ).notice
                    return NoticeBatch(
                        notices=[latest_notice] if latest_notice else [],
                        latest_cursor=latest_cursor,
                    )
                continue

            for parsed_row in eligible_rows:
                cursor = parsed_row.cursor or 0
                if cursor > last_seen_cursor and parsed_row.notice is not None:
                    collected_notices[cursor] = parsed_row.notice

            if page_latest_cursor <= last_seen_cursor:
                break

        notices = sorted(
            collected_notices.values(),
            key=lambda notice: notice.source_id or 0,
        )
        return NoticeBatch(notices=notices, latest_cursor=latest_cursor)

    def _fetch_rows(self, page_url: str) -> Optional[list[Tag]]:
        try:
            res = requests.get(page_url, timeout=10)
            res.raise_for_status()
        except Exception as exc:
            logging.error(f"Failed to fetch {self.source_name}: {exc}")
            return None

        soup = BeautifulSoup(res.content, "html.parser")
        return list(soup.select(self.row_selector))


def _extract_sw_notice_uid(href: str):
    return _extract_query_int(href, "uid")


def _extract_query_int(href: str, key: str):
    query = parse_qs(urlparse(href).query)
    values = query.get(key)
    if not values:
        return None

    try:
        return int(values[0])
    except ValueError:
        return None


def _extract_path_int(href: str):
    path = urlparse(href).path.rstrip("/")
    if not path:
        return None

    last_segment = path.split("/")[-1]
    try:
        return int(last_segment)
    except ValueError:
        return None


def _normalize_html_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _parse_eventus_date(raw_value: object) -> Optional[datetime]:
    if not isinstance(raw_value, str):
        return None

    match = re.search(r"/Date\((?P<epoch_ms>\d+)\)/", raw_value)
    if not match:
        return None

    try:
        return datetime.fromtimestamp(int(match.group("epoch_ms")) / 1000, tz=KST)
    except (OverflowError, ValueError):
        return None


def _extract_software_notice_title(title_link: Tag) -> str:
    fragments = [
        fragment.strip()
        for fragment in title_link.stripped_strings
        if fragment.strip() and fragment.strip().upper() != "NEW"
    ]
    return _normalize_html_text(" ".join(fragments))


def _replace_query_params(url: str, updates: dict[str, str]) -> str:
    parsed = urlparse(url)
    query = parse_qs(parsed.query, keep_blank_values=True)
    for key, value in updates.items():
        query[key] = [value]

    return parsed._replace(query=urlencode(query, doseq=True)).geturl()
