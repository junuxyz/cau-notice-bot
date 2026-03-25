"""Application services for CAU Notice Bot."""

from __future__ import annotations

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

        all_notices = (
            cau_batch.notices
            + sw_batch.notices
            + library_batch.notices
            + disu_batch.notices
        )
        success = await self.notifier(self.config, all_notices)

        if success and latest_sw_uid is not None:
            self.state_saver(self.config.sw_notice_state_file, latest_sw_uid)
        if success and latest_disu_bbsidx is not None:
            self.state_saver(self.config.disu_notice_state_file, latest_disu_bbsidx)

        return RunResult(
            success=success,
            notices_sent=len(all_notices),
            latest_sw_uid=latest_sw_uid,
        )
