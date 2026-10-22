"""The service's only source of time.

Every other module calls clock.now() instead of datetime.now(), so a test can
freeze the clock and move it forward (for the 60-minute and 24-hour rules)
without waiting.
"""

from datetime import UTC, datetime, timedelta

_frozen: datetime | None = None


def now() -> datetime:
    """Current time in UTC (or the frozen time, in tests)."""
    return _frozen if _frozen is not None else datetime.now(UTC)


def freeze(moment: datetime) -> None:
    """Tests only: make now() return this moment until unfreeze() is called."""
    global _frozen
    _frozen = moment


def advance(delta: timedelta) -> None:
    """Tests only: move a frozen clock forward."""
    freeze(now() + delta)


def unfreeze() -> None:
    global _frozen
    _frozen = None
