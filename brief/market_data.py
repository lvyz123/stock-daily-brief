"""行情抓取与指标计算。

美股走雅虎财经（yfinance）。港股和 A股走腾讯行情：雅虎的 A股/港股指数和 ETF 日线缺失、滞后严重，
东方财富接口又会拒绝海外 IP。
"""
from __future__ import annotations

import json
import logging
import math
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import pandas as pd
import requests
import yfinance as yf

from .universe import Market, all_codes

log = logging.getLogger(__name__)

# 两个域名走不同的 WAF，一个被限流时另一个通常还能用
TENCENT_KLINE_URLS = [
    "https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get",
    "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get",
]
HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Referer": "https://gu.qq.com/",
}
OHLCV = ["open", "high", "low", "close", "volume"]

yf.set_tz_cache_location(tempfile.mkdtemp(prefix="yf-tz-"))


# ---------------------------------------------------------------- 抓取

def fetch_yahoo(codes: list[str], period: str = "1y", retries: int = 3) -> dict[str, pd.DataFrame]:
    out: dict[str, pd.DataFrame] = {}
    pending = list(dict.fromkeys(codes))
    for attempt in range(retries):
        if not pending:
            break
        try:
            raw = yf.download(pending, period=period, interval="1d", group_by="ticker",
                              auto_adjust=False, progress=False, threads=True)
        except Exception as e:  # 网络 / 限流
            log.warning("yfinance 下载失败（第 %d 次）：%s", attempt + 1, e)
            raw = None
        if raw is not None and not raw.empty:
            for code in pending:
                try:
                    sub = raw[code] if isinstance(raw.columns, pd.MultiIndex) else raw
                except KeyError:
                    continue
                sub = sub.rename(columns=str.lower)
                if not set(OHLCV) <= set(sub.columns):
                    continue
                sub = sub[OHLCV].dropna(subset=["close"])
                if len(sub):
                    sub.index = pd.to_datetime(sub.index).tz_localize(None).normalize()
                    out[code] = sub
        pending = [c for c in pending if c not in out]
        if pending and attempt < retries - 1:
            time.sleep(5 * (attempt + 1))
    if pending:
        log.warning("雅虎未取到：%s", ", ".join(pending))
    return out


def _fetch_tencent_one(session: requests.Session, url: str, code: str, count: int) -> tuple[pd.DataFrame | None, str | None]:
    params = {"param": f"{code},day,,,{count},qfq"}
    for attempt in range(2):
        try:
            r = session.get(url, params=params, headers=HTTP_HEADERS, timeout=15)
            r.raise_for_status()  # 被 WAF 拦截时返回 501 + JS 验证页
            data = r.json().get("data", {}).get(code)
            if not isinstance(data, dict):
                return None, None
            rows = data.get("qfqday") or data.get("day") or []
            if not rows:
                return None, None
            # 腾讯行列顺序：日期, 开, 收, 高, 低, 量（行尾可能还有其他字段）
            df = pd.DataFrame([row[:6] for row in rows], columns=["date", "open", "close", "high", "low", "volume"])
            df["date"] = pd.to_datetime(df["date"])
            df = df.set_index("date")[OHLCV].apply(pd.to_numeric, errors="coerce").dropna(subset=["close"])
            qt = data.get("qt", {}).get(code)
            name = qt[1] if isinstance(qt, list) and len(qt) > 1 else None
            return df, name
        except (requests.RequestException, ValueError) as e:
            log.debug("腾讯 %s %s 第 %d 次失败：%s", url, code, attempt + 1, e)
            time.sleep(1.5 * (attempt + 1))
    return None, None


def _fetch_sina_cn_one(session: requests.Session, code: str, count: int) -> pd.DataFrame | None:
    """新浪日线（不复权），仅 A股。"""
    url = "https://quotes.sina.cn/cn/api/jsonp_v2.php/var%20_x=/CN_MarketDataService.getKLineData"
    try:
        r = session.get(url, params={"symbol": code, "scale": 240, "ma": "no", "datalen": count},
                        headers={**HTTP_HEADERS, "Referer": "https://finance.sina.com.cn"}, timeout=15)
        r.raise_for_status()
        payload = r.text[r.text.index("(") + 1: r.text.rindex(")")]
        rows = json.loads(payload)
        if not rows:
            return None
        df = pd.DataFrame(rows).rename(columns={"day": "date"})
        df["date"] = pd.to_datetime(df["date"])
        return df.set_index("date")[OHLCV].apply(pd.to_numeric, errors="coerce").dropna(subset=["close"])
    except (requests.RequestException, ValueError) as e:
        log.debug("新浪 %s 失败：%s", code, e)
        return None


def to_yahoo_hk(code: str) -> str:
    special = {"hkHSI": "^HSI", "hkHSCEI": "^HSCE", "hkHSTECH": "HSTECH.HK"}
    return special.get(code) or f"{int(code[2:]):04d}.HK"


def fetch_tencent(codes: list[str], count: int = 300) -> tuple[dict[str, pd.DataFrame], dict[str, str]]:
    """港股 / A股日线。依次尝试：腾讯（两个域名）→ 新浪（A股）→ 雅虎（港股）。"""
    frames: dict[str, pd.DataFrame] = {}
    names: dict[str, str] = {}
    pending = list(dict.fromkeys(codes))
    with requests.Session() as session:
        for url in TENCENT_KLINE_URLS:
            if not pending:
                break
            with ThreadPoolExecutor(max_workers=4) as pool:
                for code, df, name in pool.map(lambda c: (c, *_fetch_tencent_one(session, url, c, count)), pending):
                    if df is not None and len(df):
                        frames[code] = df
                    if name:
                        names[code] = name
            pending = [c for c in pending if c not in frames]

        cn_pending = [c for c in pending if not c.startswith("hk")]
        if cn_pending:
            log.warning("腾讯未取到 %d 个 A股代码，改用新浪", len(cn_pending))
            with ThreadPoolExecutor(max_workers=4) as pool:
                for code, df in zip(cn_pending, pool.map(lambda c: _fetch_sina_cn_one(session, c, count), cn_pending)):
                    if df is not None and len(df):
                        frames[code] = df

    hk_pending = [c for c in pending if c.startswith("hk")]
    if hk_pending:
        log.warning("腾讯未取到 %d 个港股代码，改用雅虎", len(hk_pending))
        yahoo = fetch_yahoo([to_yahoo_hk(c) for c in hk_pending], retries=2)
        for code in hk_pending:
            if to_yahoo_hk(code) in yahoo:
                frames[code] = yahoo[to_yahoo_hk(code)]

    missing = [c for c in codes if c not in frames]
    if missing:
        log.warning("港股/A股未取到：%s", ", ".join(missing))
    return frames, names


def fetch_market(market: Market) -> dict[str, pd.DataFrame]:
    codes = list(all_codes(market))
    if market.key == "US":
        return fetch_yahoo(codes)
    return fetch_tencent(codes)[0]


def fetch_codes(codes: list[str]) -> dict[str, pd.DataFrame]:
    """按代码格式自动路由（用于推荐跟踪等零散代码）。"""
    tencent = [c for c in codes if is_tencent_code(c)]
    yahoo = [c for c in codes if not is_tencent_code(c)]
    out: dict[str, pd.DataFrame] = {}
    if yahoo:
        out.update(fetch_yahoo(yahoo, period="3mo"))
    if tencent:
        out.update(fetch_tencent(tencent, count=60)[0])
    return out


def is_tencent_code(code: str) -> bool:
    return code[:2] in ("sh", "sz", "hk", "bj")


# ---------------------------------------------------------------- 指标

@dataclass
class Quote:
    code: str
    name: str
    last_date: date
    close: float
    chg_1d: float | None
    chg_5d: float | None
    chg_20d: float | None
    vol_ratio: float | None
    rsi14: float | None
    vs_ma50: float | None
    vs_ma200: float | None
    off_high: float | None  # 相对 52 周最高价
    stale: bool  # 最新 K 线早于应有的交易日
    chg_prev_5d: float | None = None  # 再上一周（第 6~10 个交易日）的涨跌幅
    vol_ratio_week: float | None = None  # 本周日均量 / 前四周日均量


def _pct(a: float, b: float) -> float | None:
    if b is None or a is None or b == 0 or any(map(lambda x: isinstance(x, float) and math.isnan(x), (a, b))):
        return None
    return (a / b - 1) * 100


def _rsi(close: pd.Series, n: int = 14) -> float | None:
    if len(close) <= n:
        return None
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    if loss.iloc[-1] == 0:
        return 100.0
    return float(100 - 100 / (1 + gain.iloc[-1] / loss.iloc[-1]))


def compute_quote(code: str, name: str, df: pd.DataFrame, session_date: date | None, trim: bool = True) -> Quote | None:
    """session_date：该市场本次应复盘的交易日。trim=True 时丢弃其后的 K 线（例如美股盘前出现的当日行）。"""
    if trim and session_date is not None:
        df = df[df.index.date <= session_date]
    if df.empty:
        return None
    close = df["close"]
    last = float(close.iloc[-1])
    last_date = df.index[-1].date()

    def back(n: int) -> float | None:
        return _pct(last, float(close.iloc[-1 - n])) if len(close) > n else None

    vol = df["volume"]
    vol_ratio = None
    if len(vol) > 21 and vol.iloc[-21:-1].mean() > 0:
        vol_ratio = float(vol.iloc[-1] / vol.iloc[-21:-1].mean())

    def vs_ma(n: int) -> float | None:
        return _pct(last, float(close.iloc[-n:].mean())) if len(close) >= n else None

    vol_ratio_week = None
    if len(vol) > 25 and vol.iloc[-25:-5].mean() > 0:
        vol_ratio_week = float(vol.iloc[-5:].mean() / vol.iloc[-25:-5].mean())

    high_52w = df["high"].iloc[-250:].max()
    return Quote(
        code=code, name=name, last_date=last_date, close=last,
        chg_1d=back(1), chg_5d=back(5), chg_20d=back(20),
        vol_ratio=vol_ratio, rsi14=_rsi(close),
        vs_ma50=vs_ma(50), vs_ma200=vs_ma(200),
        off_high=_pct(last, float(high_52w)),
        stale=session_date is not None and last_date < session_date,
        chg_prev_5d=_pct(float(close.iloc[-6]), float(close.iloc[-11])) if len(close) > 10 else None,
        vol_ratio_week=vol_ratio_week,
    )


def last_bar_date(df: pd.DataFrame | None, not_after: date | None = None) -> date | None:
    if df is None or df.empty:
        return None
    idx = df.index if not_after is None else df.index[df.index.date <= not_after]
    return idx[-1].date() if len(idx) else None


def build_quotes(market: Market, frames: dict[str, pd.DataFrame], session_date: date) -> dict[str, Quote]:
    quotes: dict[str, Quote] = {}
    for code, name in all_codes(market).items():
        if code not in frames:
            continue
        # 期货、利率等背景指标保留最新值（反映截至生成时的情绪）
        trim = code not in market.context
        q = compute_quote(code, name, frames[code], session_date, trim=trim)
        if q:
            if not trim:
                q.stale = False
            quotes[code] = q
    return quotes


@dataclass
class GroupStat:
    name: str
    focus: bool
    n: int
    chg_1d: float | None
    chg_5d: float | None
    chg_20d: float | None
    best: Quote | None
    worst: Quote | None
    chg_prev_5d: float | None = None
    best_week: Quote | None = None
    worst_week: Quote | None = None


def _mean(values: list[float | None]) -> float | None:
    vals = [v for v in values if v is not None]
    return sum(vals) / len(vals) if vals else None


def group_stats(market: Market, quotes: dict[str, Quote]) -> list[GroupStat]:
    stats = []
    for g in market.groups:
        qs = [quotes[c] for c in g.members if c in quotes and not quotes[c].stale]
        with_1d = [q for q in qs if q.chg_1d is not None]
        with_5d = [q for q in qs if q.chg_5d is not None]
        stats.append(GroupStat(
            name=g.name, focus=g.focus, n=len(qs),
            chg_1d=_mean([q.chg_1d for q in qs]),
            chg_5d=_mean([q.chg_5d for q in qs]),
            chg_20d=_mean([q.chg_20d for q in qs]),
            best=max(with_1d, key=lambda q: q.chg_1d) if with_1d else None,
            worst=min(with_1d, key=lambda q: q.chg_1d) if with_1d else None,
            chg_prev_5d=_mean([q.chg_prev_5d for q in qs]),
            best_week=max(with_5d, key=lambda q: q.chg_5d) if with_5d else None,
            worst_week=min(with_5d, key=lambda q: q.chg_5d) if with_5d else None,
        ))
    return stats


# ---------------------------------------------------------------- 给 LLM 的表格

def fmt_pct(v: float | None, digits: int = 1) -> str:
    return "—" if v is None else f"{v:+.{digits}f}"


def _fmt_price(v: float) -> str:
    if v >= 1000:
        return f"{v:,.0f}"
    if v >= 10:
        return f"{v:.2f}"
    return f"{v:.3f}"


def _row(q: Quote) -> str:
    cells = [
        q.code, q.name, _fmt_price(q.close), fmt_pct(q.chg_1d), fmt_pct(q.chg_5d), fmt_pct(q.chg_20d),
        "—" if q.vol_ratio is None else f"{q.vol_ratio:.1f}x",
        "—" if q.rsi14 is None else f"{q.rsi14:.0f}",
        fmt_pct(q.vs_ma50), fmt_pct(q.vs_ma200), fmt_pct(q.off_high),
    ]
    if q.stale:
        cells[1] += f"（数据停在{q.last_date:%m-%d}）"
    return "| " + " | ".join(cells) + " |"


TABLE_HEAD = (
    "| 代码 | 名称 | 收盘 | 1日% | 5日% | 20日% | 量比 | RSI14 | 距50日线% | 距200日线% | 距52周高% |\n"
    "|---|---|---|---|---|---|---|---|---|---|---|"
)


def market_tables(market: Market, quotes: dict[str, Quote], stats: list[GroupStat]) -> str:
    parts = []
    idx_rows = [_row(quotes[c]) for c in market.indices if c in quotes]
    if idx_rows:
        parts.append("#### 指数\n" + TABLE_HEAD + "\n" + "\n".join(idx_rows))
    ctx_rows = [_row(quotes[c]) for c in market.context if c in quotes]
    if ctx_rows:
        parts.append("#### 背景指标（期货为截至生成时的最新价）\n" + TABLE_HEAD + "\n" + "\n".join(ctx_rows))

    summary = ["| 板块 | 重点 | 样本数 | 等权1日% | 等权5日% | 等权20日% | 当日最强 | 当日最弱 |", "|---|---|---|---|---|---|---|---|"]
    for s in stats:
        best = f"{s.best.name} {fmt_pct(s.best.chg_1d)}" if s.best else "—"
        worst = f"{s.worst.name} {fmt_pct(s.worst.chg_1d)}" if s.worst else "—"
        summary.append(f"| {s.name} | {'★' if s.focus else ''} | {s.n} | {fmt_pct(s.chg_1d)} | {fmt_pct(s.chg_5d)} | {fmt_pct(s.chg_20d)} | {best} | {worst} |")
    parts.append("#### 板块汇总（★=AI/半导体重点板块）\n" + "\n".join(summary))

    for g in market.groups:
        rows = [_row(quotes[c]) for c in g.members if c in quotes]
        if rows:
            parts.append(f"#### {g.name}{' ★' if g.focus else ''}\n" + TABLE_HEAD + "\n" + "\n".join(rows))
    return "\n\n".join(parts)


# ---------------------------------------------------------------- 财报日程

def fetch_us_earnings(codes: list[str], start: date, days: int = 14) -> list[tuple[date, str]]:
    end = start + timedelta(days=days)

    def one(code: str) -> tuple[date, str] | None:
        try:
            cal = yf.Ticker(code).calendar or {}
            for d in cal.get("Earnings Date", []) or []:
                if isinstance(d, (datetime, pd.Timestamp)):
                    d = d.date()
                if start <= d <= end:
                    return d, code
        except Exception as e:
            log.debug("财报日程 %s 失败：%s", code, e)
        return None

    with ThreadPoolExecutor(max_workers=6) as pool:
        found = [r for r in pool.map(one, codes) if r]
    return sorted(found)


# ---------------------------------------------------------------- 自检

def _check() -> None:
    from .universe import MARKETS

    logging.basicConfig(level=logging.INFO)
    for m in MARKETS.values():
        codes = all_codes(m)
        if m.key == "US":
            frames, names = fetch_yahoo(list(codes)), {}
        else:
            frames, names = fetch_tencent(list(codes))
        print(f"\n===== {m.name}：{len(frames)}/{len(codes)} 个代码有数据")
        for code, name in codes.items():
            df = frames.get(code)
            if df is None:
                print(f"  缺失  {code:<10} {name}")
                continue
            remote = names.get(code, "")
            note = f"  （腾讯名称：{remote}）" if remote and remote.replace(" ", "") != name.replace(" ", "") else ""
            print(f"  {df.index[-1].date()}  {len(df):>3}行  {code:<10} {name}{note}")


if __name__ == "__main__":
    _check()
