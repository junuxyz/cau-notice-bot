"""Application services for CAU Notice Bot."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Awaitable, Callable, Optional

from src.bot_service import send_message_to_discord
from src.config import BotConfig
from src.domain import (
    Notice,
    RunResult,
    SourceContext,
    build_daily_notice_window,
    get_korea_datetime,
)
from src.notice_check import load_last_seen_uid, save_last_seen_uid
from src.sources import (
    CauApiNoticeSource,
    DisuNoticeSource,
    LibraryNoticeSource,
    SoftwareDeptNoticeSource,
)

Notifier = Callable[[BotConfig, list[Notice]], Awaitable[bool]]
StateLoader = Callable[[str], Optional[int]]
StateSaver = Callable[[str, int], None]
NowProvider = Callable[[], datetime]


class NoticeRunService:
    """Coordinates notice collection, delivery, and state updates."""

    def __init__(
        self,
        config: BotConfig,
        notifier: Optional[Notifier] = None,
        state_loader: Optional[StateLoader] = None,
        state_saver: Optional[StateSaver] = None,
        now_provider: Optional[NowProvider] = None,
        cau_source: Optional[CauApiNoticeSource] = None,
        library_source: Optional[LibraryNoticeSource] = None,
        software_source: Optional[SoftwareDeptNoticeSource] = None,
        disu_source: Optional[DisuNoticeSource] = None,
    ):
        self.config = config
        self.notifier = notifier or send_message_to_discord
        self.state_loader = state_loader or load_last_seen_uid
        self.state_saver = state_saver or save_last_seen_uid
        self.now_provider = now_provider or get_korea_datetime
        self.cau_source = cau_source or CauApiNoticeSource(
            config.cau_website_url,
            config.cau_api_url,
        )
        self.library_source = library_source or LibraryNoticeSource(
            config.library_website_url,
            config.library_api_url,
        )
        self.software_source = software_source or SoftwareDeptNoticeSource(
            config.sw_notice_url,
        )
        self.disu_source = disu_source or DisuNoticeSource(config.disu_notice_url)

    async def run(self) -> RunResult:
        window = build_daily_notice_window(self.now_provider())
        sw_last_seen_uid = self.state_loader(self.config.sw_notice_state_file)
        disu_last_seen_bbsidx = self.state_loader(self.config.disu_notice_state_file)
        recent_disu_notice_keys = load_recent_notice_keys(
            self.config.disu_notice_state_file
        )

        cau_batch = self.cau_source.fetch(SourceContext(window=window))
        sw_batch = self.software_source.fetch(
            SourceContext(window=window, state=sw_last_seen_uid)
        )
        library_batch = self.library_source.fetch(SourceContext(window=window))
        disu_batch = self.disu_source.fetch(
            SourceContext(window=window, state=disu_last_seen_bbsidx)
        )

        latest_sw_uid = sw_batch.latest_cursor
        if sw_last_seen_uid is not None and latest_sw_uid is not None:
            latest_sw_uid = max(latest_sw_uid, sw_last_seen_uid)

        latest_disu_bbsidx = disu_batch.latest_cursor
        if disu_last_seen_bbsidx is not None and latest_disu_bbsidx is not None:
            latest_disu_bbsidx = max(latest_disu_bbsidx, disu_last_seen_bbsidx)

        filtered_disu_notices = _filter_new_notice_keys(
            disu_batch.notices,
            recent_disu_notice_keys,
        )
        all_notices = (
            cau_batch.notices
            + sw_batch.notices
            + library_batch.notices
            + filtered_disu_notices
        )
        success = await self.notifier(self.config, all_notices)

        if success and latest_sw_uid is not None:
            self.state_saver(self.config.sw_notice_state_file, latest_sw_uid)
        if success and latest_disu_bbsidx is not None:
            self.state_saver(self.config.disu_notice_state_file, latest_disu_bbsidx)
        if success:
            save_recent_notice_keys(
                self.config.disu_notice_state_file,
                merge_recent_notice_keys(
                    recent_disu_notice_keys,
                    filtered_disu_notices,
                ),
            )

        return RunResult(
            success=success,
            notices_sent=len(all_notices),
            latest_sw_uid=latest_sw_uid,
        )


RECENT_NOTICE_KEY_LIMIT = 50


def load_recent_notice_keys(state_file: str) -> list[str]:
    path = _recent_notice_keys_path(state_file)
    if not path.exists():
        return []

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logging.warning("Failed to read recent notice key state file: %s", exc)
        return []

    if not isinstance(data, list):
        return []

    return [str(item) for item in data if isinstance(item, str)]


def save_recent_notice_keys(state_file: str, notice_keys: list[str]) -> None:
    path = _recent_notice_keys_path(state_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(notice_keys[-RECENT_NOTICE_KEY_LIMIT:], ensure_ascii=False),
        encoding="utf-8",
    )


def merge_recent_notice_keys(existing_keys: list[str], notices: list[Notice]) -> list[str]:
    merged_keys = list(existing_keys)
    seen_keys = set(existing_keys)

    for notice in notices:
        notice_key = build_notice_key(notice)
        if notice_key in seen_keys:
            continue
        merged_keys.append(notice_key)
        seen_keys.add(notice_key)

    return merged_keys[-RECENT_NOTICE_KEY_LIMIT:]


def build_notice_key(notice: Notice) -> str:
    parts = (
        _normalize_notice_key_part(notice.source),
        _normalize_notice_key_part(notice.category),
        _normalize_notice_key_part(notice.title),
        _normalize_notice_key_part(notice.post_date),
    )
    return "|".join(parts)


def _filter_new_notice_keys(notices: list[Notice], existing_keys: list[str]) -> list[Notice]:
    filtered_notices: list[Notice] = []
    seen_keys = set(existing_keys)

    for notice in notices:
        notice_key = build_notice_key(notice)
        if notice_key in seen_keys:
            continue
        filtered_notices.append(notice)
        seen_keys.add(notice_key)

    return filtered_notices


def _normalize_notice_key_part(value: str) -> str:
    return " ".join(value.split()).strip()


def _recent_notice_keys_path(state_file: str) -> Path:
    return Path(f"{state_file}.recent.json")
