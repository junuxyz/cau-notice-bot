"""Compatibility helpers for notice fetching and state persistence."""

import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from src.domain import Notice, SourceContext, build_daily_notice_window
from src.domain import get_korea_datetime as _now
from src.sources import (
    CauApiNoticeSource,
    LibraryNoticeSource,
    SoftwareDeptNoticeSource,
)


def get_korea_datetime():
    """Get current datetime in Korea (KST)."""
    return _now()


def is_notice_in_time_range(notice_datetime: datetime) -> bool:
    """Check if a notice is posted in the current daily KST window."""
    return build_daily_notice_window(get_korea_datetime()).contains(notice_datetime)


def check_library_notices(
    library_website_url: str, library_api_url: str
) -> List[Dict[str, str]]:
    source = LibraryNoticeSource(library_website_url, library_api_url)
    return _batch_to_dicts(source.fetch(_source_context()))


def check_cau_notices(cau_website_url: str, cau_api_url: str) -> List[Dict[str, str]]:
    source = CauApiNoticeSource(cau_website_url, cau_api_url)
    return _batch_to_dicts(source.fetch(_source_context()))


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


def check_sw_notices(
    sw_notice_url: str, last_seen_uid: Optional[int]
) -> Tuple[List[Dict[str, str]], Optional[int]]:
    """Scrape software department notices and return (new_notices, latest_uid)."""
    source = SoftwareDeptNoticeSource(sw_notice_url)
    batch = source.fetch(_source_context(state=last_seen_uid))
    return _batch_to_dicts(batch), batch.latest_cursor


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


def _source_context(state: Optional[int] = None):
    return SourceContext(
        window=build_daily_notice_window(get_korea_datetime()),
        state=state,
    )


def _notice_to_dict(notice: Notice) -> Dict[str, str]:
    return {
        "title": notice.title,
        "post_date": notice.post_date,
        "category": notice.category,
        "url": notice.url or "",
    }


def _batch_to_dicts(batch) -> List[Dict[str, str]]:
    return [_notice_to_dict(notice) for notice in batch.notices]
