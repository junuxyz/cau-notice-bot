"""Notice source adapters."""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Protocol
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from src.domain import KST, Notice, NoticeBatch, SourceContext


class NoticeSource(Protocol):
    def fetch(self, context: SourceContext) -> NoticeBatch:
        """Fetch notices for the given execution context."""


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

    def fetch(self, context: SourceContext) -> NoticeBatch:
        if not self.notice_url:
            return NoticeBatch(notices=[])

        try:
            res = requests.get(self.notice_url, timeout=10)
            res.raise_for_status()
        except Exception as exc:
            logging.error(f"Failed to fetch software department notices: {exc}")
            return NoticeBatch(notices=[])

        soup = BeautifulSoup(res.content, "html.parser")
        rows = soup.select("table.table-basic tbody tr")

        parsed_notices: list[Notice] = []
        for row in rows:
            title_link = row.select_one("td.aleft a")
            if not title_link:
                continue

            uid = _extract_sw_notice_uid(title_link.get("href", ""))
            if uid is None:
                continue

            raw_title = title_link.get_text(separator=" ", strip=True)
            title = re.sub(r"\s+", " ", raw_title).strip()
            date_match = re.search(r"\d{4}\.\d{2}\.\d{2}", row.get_text(" ", strip=True))
            post_date = date_match.group(0) if date_match else ""

            parsed_notices.append(
                Notice(
                    title=title,
                    post_date=post_date,
                    category="소프트웨어학과 공지",
                    url=urljoin(self.notice_url, title_link.get("href", "")),
                    source="software",
                    source_id=uid,
                )
            )

        if not parsed_notices:
            return NoticeBatch(notices=[])

        latest_uid = max(notice.source_id for notice in parsed_notices if notice.source_id)
        last_seen_uid = context.state

        if last_seen_uid is None:
            logging.info(
                "Software notice state not found; sending latest notice and initializing state."
            )
            latest_notice = max(
                parsed_notices,
                key=lambda notice: notice.source_id or 0,
            )
            return NoticeBatch(
                notices=[latest_notice],
                latest_cursor=latest_uid,
            )

        new_notices = [
            notice for notice in parsed_notices if (notice.source_id or 0) > last_seen_uid
        ]
        new_notices.sort(key=lambda notice: notice.source_id or 0)
        return NoticeBatch(notices=new_notices, latest_cursor=latest_uid)


def _extract_sw_notice_uid(href: str):
    query = parse_qs(urlparse(href).query)
    uid_values = query.get("uid")
    if not uid_values:
        return None

    try:
        return int(uid_values[0])
    except ValueError:
        return None
