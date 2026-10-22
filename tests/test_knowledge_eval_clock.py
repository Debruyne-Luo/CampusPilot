"""A fixed evaluation date reaches tools without changing other requests' dates."""

import asyncio
from datetime import date

import pytest
from campuspilot.knowledge import campus_clock, campus_today


def test_fixture_clock_is_local_and_restored_on_exception() -> None:
    actual = campus_today()
    with pytest.raises(RuntimeError), campus_clock(date(2001, 2, 3)):
        assert campus_today() == date(2001, 2, 3)
        with campus_clock(date(2002, 3, 4)):
            assert campus_today() == date(2002, 3, 4)
        assert campus_today() == date(2001, 2, 3)
        raise RuntimeError("synthetic")
    assert campus_today() == actual


def test_async_tasks_and_worker_threads_keep_independent_fixture_clocks() -> None:
    actual = campus_today()

    async def scenario(day: date) -> tuple[date, date]:
        with campus_clock(day):
            await asyncio.sleep(0)
            return campus_today(), await asyncio.to_thread(campus_today)

    async def run() -> None:
        first, second = await asyncio.gather(
            scenario(date(2001, 2, 3)), scenario(date(2002, 3, 4))
        )
        assert first == (date(2001, 2, 3), date(2001, 2, 3))
        assert second == (date(2002, 3, 4), date(2002, 3, 4))
        assert campus_today() == actual

    asyncio.run(run())
