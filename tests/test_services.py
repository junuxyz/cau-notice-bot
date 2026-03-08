"""Tests for application orchestration."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domain import Notice, NoticeBatch, SourceContext
from src.services import NoticeRunService
from tests.conftest import create_kst_datetime


class StubSource:
    """Simple source stub that records the received execution context."""

    def __init__(self, batch: NoticeBatch):
        self.batch = batch
        self.contexts = []

    def fetch(self, context: SourceContext) -> NoticeBatch:
        self.contexts.append(context)
        return self.batch


class TestNoticeRunService:
    @pytest.mark.asyncio
    async def test_persists_latest_sw_uid_only_after_success(self, bot_config):
        cau_source = StubSource(
            NoticeBatch(
                notices=[
                    Notice(
                        title="CAU Notice",
                        post_date="2026-01-19 07:30",
                        category="CAU 공지",
                        url="https://example.com/cau",
                        source="cau",
                    )
                ]
            )
        )
        software_source = StubSource(
            NoticeBatch(
                notices=[
                    Notice(
                        title="SW Notice",
                        post_date="2026.01.19",
                        category="소프트웨어학과 공지",
                        url="https://example.com/sw?uid=3002",
                        source="software",
                        source_id=3002,
                    )
                ],
                latest_cursor=3002,
            )
        )
        library_source = StubSource(NoticeBatch(notices=[]))
        notifier = AsyncMock(return_value=True)
        state_loader = MagicMock(return_value=3001)
        state_saver = MagicMock()

        result = await NoticeRunService(
            bot_config,
            notifier=notifier,
            state_loader=state_loader,
            state_saver=state_saver,
            now_provider=lambda: create_kst_datetime(2026, 1, 19, 15, 0),
            cau_source=cau_source,
            software_source=software_source,
            library_source=library_source,
        ).run()

        assert result.success is True
        assert result.notices_sent == 2
        state_saver.assert_called_once_with(".state/sw_last_seen_uid.txt", 3002)
        notifier.assert_awaited_once()
        sent_notices = notifier.await_args.args[1]
        assert [notice.title for notice in sent_notices] == ["CAU Notice", "SW Notice"]

    @pytest.mark.asyncio
    async def test_does_not_persist_state_on_delivery_failure(self, bot_config):
        notifier = AsyncMock(return_value=False)
        state_saver = MagicMock()

        result = await NoticeRunService(
            bot_config,
            notifier=notifier,
            state_loader=MagicMock(return_value=1000),
            state_saver=state_saver,
            now_provider=lambda: create_kst_datetime(2026, 1, 19, 15, 0),
            cau_source=StubSource(NoticeBatch(notices=[])),
            software_source=StubSource(NoticeBatch(notices=[], latest_cursor=1001)),
            library_source=StubSource(NoticeBatch(notices=[])),
        ).run()

        assert result.success is False
        state_saver.assert_not_called()

    @pytest.mark.asyncio
    async def test_passes_window_and_state_to_sources(self, bot_config):
        cau_source = StubSource(NoticeBatch(notices=[]))
        software_source = StubSource(NoticeBatch(notices=[], latest_cursor=123))
        library_source = StubSource(NoticeBatch(notices=[]))

        await NoticeRunService(
            bot_config,
            notifier=AsyncMock(return_value=True),
            state_loader=MagicMock(return_value=122),
            state_saver=MagicMock(),
            now_provider=lambda: create_kst_datetime(2026, 1, 19, 15, 0),
            cau_source=cau_source,
            software_source=software_source,
            library_source=library_source,
        ).run()

        assert cau_source.contexts[0].window.start == create_kst_datetime(
            2026, 1, 18, 8, 0
        )
        assert cau_source.contexts[0].window.end == create_kst_datetime(
            2026, 1, 19, 8, 0
        )
        assert software_source.contexts[0].state == 122
        assert library_source.contexts[0].state is None
