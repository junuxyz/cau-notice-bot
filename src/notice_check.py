"""
Notice fetching from CAU and Library APIs.
"""

import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

import requests
from bs4 import BeautifulSoup


def get_korea_datetime():
    """Get current datetime in Korea (KST)"""
    kst = timezone(timedelta(hours=9))
    return datetime.now(kst)


def is_notice_in_time_range(notice_datetime: datetime) -> bool:
    """
    Check if the notice is posted between yesterday 8:01 AM and today 8:00 AM
    """
    now = get_korea_datetime()
    yesterday = now - timedelta(days=1)

    # yesterday 8:00 AM ~ today 8:00 AM
    start_time = yesterday.replace(hour=8, minute=0, second=0, microsecond=0)
    end_time = now.replace(hour=8, minute=0, second=0, microsecond=0)

    return start_time <= notice_datetime <= end_time


def check_cau_notices(cau_website_url: str, cau_api_url: str) -> List[Dict[str, str]]:
    params = {"SITE_NO": "2", "BOARD_SEQ": "4"}

    res = requests.get(cau_api_url, params=params)
    res.raise_for_status()

    data = res.json()
    notices = []

    # Handle malformed data
    data_section = data.get("data") if data else None
    notice_list = data_section.get("list", []) if data_section else []

    for notice in notice_list:
        try:
            notice_datetime = datetime.strptime(
                notice["WRITE_DT"].split(".")[0], "%Y-%m-%d %H:%M:%S"
            )
            notice_datetime = notice_datetime.replace(
                tzinfo=timezone(timedelta(hours=9))
            )

            if is_notice_in_time_range(notice_datetime):
                url_params = {
                    "MENU_ID": "100",
                    "CONTENTS_NO": "1",
                    "SITE_NO": "2",
                    "BOARD_SEQ": "4",
                    "BBS_SEQ": notice.get("BBS_SEQ", ""),
                }
                notice_url = f"{cau_website_url}?{urlencode(url_params)}"
                display_date = notice_datetime.strftime("%Y-%m-%d %H:%M")
                notices.append(
                    {
                        "title": notice.get("SUBJECT", ""),
                        "post_date": display_date,
                        "category": "CAU 공지",
                        "url": notice_url,
                    }
                )
        except Exception as e:
            logging.error(f"Error while processing individual CAU notice: {str(e)}")
            continue

    notices.sort(key=lambda x: x["post_date"], reverse=False)
    return notices


def check_library_notices(
    library_website_url: str, library_api_url: str
) -> List[Dict[str, str]]:
    try:
        res = requests.get(library_api_url, timeout=10)
        res.raise_for_status()
        data = res.json()

        notices = []
        if data.get("success") and data.get("data", {}).get("list"):
            for notice in data["data"]["list"]:
                try:
                    notice_datetime = datetime.strptime(
                        notice["dateCreated"], "%Y-%m-%d %H:%M:%S"
                    )
                    notice_datetime = notice_datetime.replace(
                        tzinfo=timezone(timedelta(hours=9))
                    )  # Apply KST

                    if is_notice_in_time_range(notice_datetime):
                        display_date = notice_datetime.strftime("%Y-%m-%d %H:%M")
                        notices.append(
                            {
                                "title": notice.get("title", ""),
                                "post_date": display_date,
                                "category": "학술정보원 공지",
                                "url": f"{library_website_url}/{notice['id']}",
                            }
                        )

                except Exception as e:
                    logging.error(
                        f"Error while processing individual library notice: {str(e)}"
                    )
                    continue

        notices.sort(key=lambda x: x["post_date"], reverse=False)
        return notices

    except Exception as e:
        logging.error(f"Error while fetching library notices: {str(e)}")
        return []


def load_last_seen_uid(state_file: str) -> Optional[int]:
    """Load last seen software notice UID from state file."""
    path = Path(state_file)
    if not path.exists():
        return None

    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (ValueError, OSError) as e:
        logging.warning(f"Failed to read software notice state file: {e}")
        return None


def save_last_seen_uid(state_file: str, uid: int) -> None:
    """Persist last seen software notice UID to state file."""
    path = Path(state_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(uid), encoding="utf-8")


def _extract_sw_notice_uid(href: str) -> Optional[int]:
    """Extract uid query parameter from a software notice link."""
    query = parse_qs(urlparse(href).query)
    uid_values = query.get("uid")
    if not uid_values:
        return None

    try:
        return int(uid_values[0])
    except ValueError:
        return None


def check_sw_notices(
    sw_notice_url: str, last_seen_uid: Optional[int]
) -> Tuple[List[Dict[str, str]], Optional[int]]:
    """Scrape software department notices and return (new_notices, latest_uid)."""
    if not sw_notice_url:
        return [], None

    try:
        res = requests.get(sw_notice_url, timeout=10)
        res.raise_for_status()
    except Exception as e:
        logging.error(f"Failed to fetch software department notices: {str(e)}")
        return [], None

    # Parse bytes directly so BeautifulSoup can honor the page's <meta charset>.
    # The target site does not send a charset header, and requests.text can mojibake.
    soup = BeautifulSoup(res.content, "html.parser")
    rows = soup.select("table.table-basic tbody tr")

    parsed_notices = []
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
            {
                "uid": uid,
                "title": title,
                "post_date": post_date,
                "category": "소프트웨어학과 공지",
                "url": urljoin(sw_notice_url, title_link.get("href", "")),
            }
        )

    if not parsed_notices:
        return [], None

    latest_uid = max(notice["uid"] for notice in parsed_notices)
    if last_seen_uid is None:
        logging.info(
            "Software notice state not found; sending latest notice and initializing state."
        )
        latest_notice = max(parsed_notices, key=lambda notice: notice["uid"]).copy()
        latest_notice.pop("uid", None)
        return [latest_notice], latest_uid

    new_notices = [notice for notice in parsed_notices if notice["uid"] > last_seen_uid]
    new_notices.sort(key=lambda notice: notice["uid"])

    for notice in new_notices:
        notice.pop("uid", None)

    return new_notices, latest_uid


def check_notices(config) -> Tuple[List[Dict], List[Dict], Optional[int]]:
    """Checks notices from CAU, SW department, and CAU Library and returns them."""
    cau_notices = check_cau_notices(config.cau_website_url, config.cau_api_url)

    sw_last_seen_uid = load_last_seen_uid(config.sw_notice_state_file)
    sw_notices, sw_latest_uid = check_sw_notices(config.sw_notice_url, sw_last_seen_uid)
    if sw_last_seen_uid is not None and sw_latest_uid is not None:
        sw_latest_uid = max(sw_latest_uid, sw_last_seen_uid)
    cau_notices.extend(sw_notices)

    library_notices = check_library_notices(
        config.library_website_url, config.library_api_url
    )
    return cau_notices, library_notices, sw_latest_uid
