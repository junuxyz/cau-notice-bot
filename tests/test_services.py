"""Tests for application orchestration."""

import json
from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock, call

import pytest

from src.domain import Notice, NoticeBatch, SourceContext
from src.services import NoticeRunService, build_notice_key
from tests.conftest import create_kst_datetime


class StubSource:
    """Simple source stub that records the received execution context."""

    def __init__(self, batch: NoticeBatch):
        self.batch = batch
        self.contexts = []

    def fetch(self, context: SourceContext) -> NoticeBatch:
        self.contexts.append(context)
        return self.batch


def _fake_disu_notice(*, source_id: int, title: str, post_date: str) -> Notice:
    return Notice(
        title=title,
        post_date=post_date,
        category="Partner Feed Notice",
        url=f"https://example.com/notices/{source_id}",
        source="disu",
        source_id=source_id,
    )


class TestNoticeRunService:
    @pytest.mark.asyncio
    async def test_persists_independent_html_source_state_after_success(
        self,
        bot_config,
        tmp_path,
    ):
        bot_config = replace(
            bot_config,
            software=replace(
                bot_config.software,
                state_file=str(tmp_path / "sw_last_seen_uid.txt"),
            ),
            disu=replace(
                bot_config.disu,
                state_file=str(tmp_path / "disu_last_seen_bbsidx.txt"),
            ),
        )
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
        disu_source = StubSource(
            NoticeBatch(
                notices=[
                    _fake_disu_notice(
                        source_id=8601,
                        title="Partner Notice",
                        post_date="2026-01-19",
                    )
                ],
                latest_cursor=8601,
            )
        )
        notifier = AsyncMock(return_value=True)
        state_loader = MagicMock(side_effect=[3001, 8600])
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
            disu_source=disu_source,
        ).run()

        assert result.success is True
        assert result.notices_sent == 3
        assert state_saver.call_args_list == [
            call(str(tmp_path / "sw_last_seen_uid.txt"), 3002),
            call(str(tmp_path / "disu_last_seen_bbsidx.txt"), 8601),
        ]
        notifier.assert_awaited_once()
        sent_notices = notifier.await_args.args[1]
        assert [notice.title for notice in sent_notices] == [
            "CAU Notice",
            "SW Notice",
            "Partner Notice",
        ]

    @pytest.mark.asyncio
    async def test_does_not_persist_state_on_delivery_failure(self, bot_config):
        notifier = AsyncMock(return_value=False)
        state_saver = MagicMock()

        result = await NoticeRunService(
            bot_config,
            notifier=notifier,
            state_loader=MagicMock(side_effect=[1000, 2000]),
            state_saver=state_saver,
            now_provider=lambda: create_kst_datetime(2026, 1, 19, 15, 0),
            cau_source=StubSource(NoticeBatch(notices=[])),
            software_source=StubSource(NoticeBatch(notices=[], latest_cursor=1001)),
            library_source=StubSource(NoticeBatch(notices=[])),
            disu_source=StubSource(NoticeBatch(notices=[], latest_cursor=2001)),
        ).run()

        assert result.success is False
        state_saver.assert_not_called()

    @pytest.mark.asyncio
    async def test_passes_window_and_state_to_sources(self, bot_config):
        cau_source = StubSource(NoticeBatch(notices=[]))
        software_source = StubSource(NoticeBatch(notices=[], latest_cursor=123))
        library_source = StubSource(NoticeBatch(notices=[]))
        disu_source = StubSource(NoticeBatch(notices=[], latest_cursor=456))

        await NoticeRunService(
            bot_config,
            notifier=AsyncMock(return_value=True),
            state_loader=MagicMock(side_effect=[122, 455]),
            state_saver=MagicMock(),
            now_provider=lambda: create_kst_datetime(2026, 1, 19, 15, 0),
            cau_source=cau_source,
            software_source=software_source,
            library_source=library_source,
            disu_source=disu_source,
        ).run()

        assert cau_source.contexts[0].window.start == create_kst_datetime(
            2026, 1, 18, 8, 0
        )
        assert cau_source.contexts[0].window.end == create_kst_datetime(
            2026, 1, 19, 8, 0
        )
        assert software_source.contexts[0].state == 122
        assert library_source.contexts[0].state is None
        assert disu_source.contexts[0].state == 455

    @pytest.mark.asyncio
    async def test_filters_recent_duplicate_disu_notice_and_keeps_cursor_progress(
        self,
        bot_config,
        tmp_path,
    ):
        bot_config = replace(
            bot_config,
            disu=replace(
                bot_config.disu,
                state_file=str(tmp_path / "disu_last_seen_bbsidx.txt"),
            ),
        )
        recent_state_path = tmp_path / "disu_last_seen_bbsidx.txt.recent.json"
        previous_notice = _fake_disu_notice(
            source_id=8601,
            title="Shared Program Application Guide",
            post_date="2026-03-24",
        )
        recent_state_path.write_text(
            json.dumps([build_notice_key(previous_notice)], ensure_ascii=False),
            encoding="utf-8",
        )

        duplicate_disu_notice = _fake_disu_notice(
            source_id=8602,
            title="Shared Program Application Guide",
            post_date="2026-03-24",
        )
        disu_source = StubSource(
            NoticeBatch(notices=[duplicate_disu_notice], latest_cursor=8602)
        )
        notifier = AsyncMock(return_value=True)
        state_loader = MagicMock(side_effect=[3001, 8601])
        state_saver = MagicMock()

        result = await NoticeRunService(
            bot_config,
            notifier=notifier,
            state_loader=state_loader,
            state_saver=state_saver,
            now_provider=lambda: create_kst_datetime(2026, 3, 27, 8, 0),
            cau_source=StubSource(NoticeBatch(notices=[])),
            software_source=StubSource(NoticeBatch(notices=[], latest_cursor=3001)),
            library_source=StubSource(NoticeBatch(notices=[])),
            disu_source=disu_source,
        ).run()

        assert result.success is True
        assert result.notices_sent == 0
        notifier.assert_awaited_once()
        assert notifier.await_args.args[1] == []
        assert state_saver.call_args_list == [
            call(".state/sw_last_seen_uid.txt", 3001),
            call(str(tmp_path / "disu_last_seen_bbsidx.txt"), 8602),
        ]
        assert json.loads(recent_state_path.read_text(encoding="utf-8")) == [
            build_notice_key(previous_notice)
        ]
