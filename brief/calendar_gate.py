"""判断“股票交易日”：北京时间 T 日 18:30 之前的 24 小时内，三地至少有一个市场开过市。

窗口 [T-1 18:30, T 18:30]（北京时间）覆盖：
- 美股：纽约日期 T-1 的交易时段（北京时间 T-1 晚 21:30/22:30 开盘，T 日凌晨收盘）
- 港股 / A股：T 日的交易时段
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from functools import cache

import exchange_calendars as xcals
import pandas as pd

log = logging.getLogger(__name__)

CALENDARS = {"US": "XNYS", "HK": "XHKG", "CN": "XSHG"}
WEEKDAYS = "一二三四五六日"


@cache
def _cal(key: str):
    return xcals.get_calendar(CALENDARS[key])


def review_date(key: str, run_date: date) -> date:
    """该市场在本次窗口内应复盘的交易日（当地日期）。"""
    return run_date - timedelta(days=1) if key == "US" else run_date


def calendar_is_session(key: str, d: date) -> bool:
    return bool(_cal(key).is_session(pd.Timestamp(d)))


def next_session_after(key: str, d: date) -> date | None:
    cal = _cal(key)
    try:
        return cal.date_to_session(pd.Timestamp(d + timedelta(days=1)), direction="next").date()
    except Exception:  # 超出日历范围
        return None


def calendar_open_markets(run_date: date) -> dict[str, bool]:
    return {k: calendar_is_session(k, review_date(k, run_date)) for k in CALENDARS}


@dataclass
class MarketStatus:
    key: str
    open: bool  # 窗口内是否开市
    session_date: date  # 复盘的交易日（开市时即窗口内的那一天）
    next_session: date | None
    source: str  # data / calendar / forced


def resolve(run_date: date, last_bars: dict[str, date | None], force: bool = False) -> dict[str, MarketStatus]:
    """last_bars：各市场代表指数的最新 K 线日期（不晚于应复盘日）；None 表示没取到数据。

    有数据时以数据为准（能识别台风停市等日历不知道的休市），没数据时退回交易所日历。
    force=True 用于测试：市场即使不在窗口内开市，也拿它最近一个交易日来复盘。
    """
    out = {}
    for key in CALENDARS:
        target = review_date(key, run_date)
        lb = last_bars.get(key)
        if lb is not None:
            is_open, source = lb == target, "data"
            if not is_open and calendar_is_session(key, target):
                log.warning("%s 日历显示 %s 开市，但数据里没有这一天的 K 线，按休市处理", key, target)
        else:
            is_open, source = calendar_is_session(key, target), "calendar"
        session = target
        if not is_open and force and lb is not None and (target - lb).days <= 5:
            is_open, session, source = True, lb, "forced"
        out[key] = MarketStatus(key, is_open, session, next_session_after(key, session if is_open else target - timedelta(days=1)), source)
    return out


def fmt_day(d: date | None) -> str:
    return "—" if d is None else f"{d:%m月%d日}（周{WEEKDAYS[d.weekday()]}）"
