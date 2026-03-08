"""Domain models for CAU Notice Bot."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

KST = timezone(timedelta(hours=9))


@dataclass(frozen=True)
class Notice:
    """Normalized notice shape used across sources and delivery."""

    title: str
    post_date: str
    category: str
    url: Optional[str]
    source: str
    source_id: Optional[int] = None


@dataclass(frozen=True)
class TimeWindow:
    """Inclusive time window for source filtering."""

    start: datetime
    end: datetime

    def contains(self, notice_datetime: datetime) -> bool:
        return self.start <= notice_datetime <= self.end


@dataclass(frozen=True)
class SourceContext:
    """Shared execution context passed into source adapters."""

    window: TimeWindow
    state: Optional[int] = None


@dataclass(frozen=True)
class NoticeBatch:
    """Normalized result of fetching a single notice source."""

    notices: list[Notice]
    latest_cursor: Optional[int] = None


@dataclass(frozen=True)
class RunResult:
    """Outcome of a single application run."""

    success: bool
    notices_sent: int
    latest_sw_uid: Optional[int] = None


def get_korea_datetime() -> datetime:
    """Get current datetime in Korea (KST)."""
    return datetime.now(KST)


def build_daily_notice_window(now: Optional[datetime] = None) -> TimeWindow:
    """Build the inclusive daily window used by CAU and library notices."""
    current = now or get_korea_datetime()
    yesterday = current - timedelta(days=1)
    start_time = yesterday.replace(hour=8, minute=0, second=0, microsecond=0)
    end_time = current.replace(hour=8, minute=0, second=0, microsecond=0)
    return TimeWindow(start=start_time, end=end_time)
