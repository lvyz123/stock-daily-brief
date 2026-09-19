from datetime import date

import pytest

from brief.calendar_gate import calendar_open_markets, next_session_after, resolve


@pytest.mark.parametrize(
    "run_date, expected",
    [
        # 周六：美股周五开市 → 发
        (date(2026, 9, 19), {"US": True, "HK": False, "CN": False}),
        # 周日：都不开 → 不发
        (date(2026, 9, 20), {"US": False, "HK": False, "CN": False}),
        # 周一：港股、A股开市
        (date(2026, 9, 21), {"US": False, "HK": True, "CN": True}),
        # 国庆：港股、A股休市，美股 9/30 开市 → 照发
        (date(2026, 10, 1), {"US": True, "HK": False, "CN": False}),
        # 12/26 周六：美股圣诞休市，港股、A股周末 → 不发
        (date(2026, 12, 26), {"US": False, "HK": False, "CN": False}),
        # 12/25 周五：美股 12/24 开（半日市），港股圣诞休市，A股正常
        (date(2026, 12, 25), {"US": True, "HK": False, "CN": True}),
    ],
)
def test_calendar_open_markets(run_date, expected):
    assert calendar_open_markets(run_date) == expected


def test_resolve_prefers_data_over_calendar():
    # 港股台风停市：日历说开市，但数据里没有当天 K 线
    run = date(2026, 9, 21)
    st = resolve(run, {"US": date(2026, 9, 18), "HK": date(2026, 9, 18), "CN": date(2026, 9, 21)})
    assert not st["US"].open and not st["HK"].open and st["CN"].open
    assert st["CN"].session_date == run
    assert st["CN"].next_session == date(2026, 9, 22)


def test_resolve_only_hk_open():
    run = date(2026, 9, 21)
    st = resolve(run, {"US": date(2026, 9, 18), "HK": run, "CN": date(2026, 9, 18)})
    assert [k for k, s in st.items() if s.open] == ["HK"]


def test_resolve_falls_back_to_calendar_without_data():
    st = resolve(date(2026, 9, 19), {"US": None, "HK": None, "CN": None})
    assert st["US"].open and st["US"].source == "calendar"
    assert st["US"].session_date == date(2026, 9, 18)
    assert st["US"].next_session == date(2026, 9, 21)
    # 周六：港股下一交易日是周一
    assert not st["HK"].open and st["HK"].next_session == date(2026, 9, 21)


def test_force_uses_latest_session():
    st = resolve(date(2026, 9, 20), {"US": date(2026, 9, 18), "HK": date(2026, 9, 18), "CN": date(2026, 9, 18)}, force=True)
    assert all(s.open and s.source == "forced" and s.session_date == date(2026, 9, 18) for s in st.values())


def test_next_session_skips_golden_week():
    assert next_session_after("CN", date(2026, 9, 30)) > date(2026, 10, 7)
