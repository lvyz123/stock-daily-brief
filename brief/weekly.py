"""周报用的数据包：抓取三地行情，算出周度指标，输出成一个 Markdown 文件供分析时阅读。

用法：python -m brief.weekly [--date YYYY-MM-DD]
输出：out/weekly_data.md
"""
from __future__ import annotations

import argparse
import logging
from datetime import date, datetime, timedelta

from . import config
from .calendar_gate import WEEKDAYS, fmt_day, next_session_after
from .cn_boards import board_rankings
from .market_data import (GroupStat, Quote, build_quotes, fetch_market, fetch_tencent, fetch_us_earnings,
                          fetch_yahoo, fmt_pct, group_stats, last_bar_date)
from .universe import GATE_INDEX, MARKETS, US, all_codes

log = logging.getLogger(__name__)

HEAD = ("| 代码 | 名称 | 收盘 | 本周% | 上周% | 近20日% | 周量能比 | RSI14 | 距50日线% | 距52周高% |\n"
        "|---|---|---|---|---|---|---|---|---|---|")


def _price(v: float) -> str:
    return f"{v:,.0f}" if v >= 1000 else f"{v:.2f}" if v >= 10 else f"{v:.3f}"


def _row(q: Quote) -> str:
    cells = [q.code, q.name, _price(q.close), fmt_pct(q.chg_5d), fmt_pct(q.chg_prev_5d), fmt_pct(q.chg_20d),
             "—" if q.vol_ratio_week is None else f"{q.vol_ratio_week:.2f}x",
             "—" if q.rsi14 is None else f"{q.rsi14:.0f}",
             fmt_pct(q.vs_ma50), fmt_pct(q.off_high)]
    return "| " + " | ".join(cells) + " |"


def _group_table(stats: list[GroupStat]) -> str:
    rows = ["| 板块 | 重点 | 样本数 | 本周% | 上周% | 近20日% | 本周最强 | 本周最弱 |", "|---|---|---|---|---|---|---|---|"]
    for s in sorted([s for s in stats if s.n], key=lambda s: s.chg_5d if s.chg_5d is not None else -99, reverse=True):
        best = f"{s.best_week.name} {fmt_pct(s.best_week.chg_5d)}" if s.best_week else "—"
        worst = f"{s.worst_week.name} {fmt_pct(s.worst_week.chg_5d)}" if s.worst_week else "—"
        rows.append(f"| {s.name} | {'★' if s.focus else ''} | {s.n} | {fmt_pct(s.chg_5d)} | "
                    f"{fmt_pct(s.chg_prev_5d)} | {fmt_pct(s.chg_20d)} | {best} | {worst} |")
    return "\n".join(rows)


def _movers(market_key: str, quotes: dict[str, Quote], top: int = 15, bottom: int = 10) -> str:
    market = MARKETS[market_key]
    skip = set(market.indices) | set(market.context)
    ranked = sorted([q for c, q in quotes.items() if c not in skip and q.chg_5d is not None],
                    key=lambda q: q.chg_5d, reverse=True)
    if not ranked:
        return ""
    lines = ["**本周涨幅榜**", HEAD] + [_row(q) for q in ranked[:top]]
    lines += ["", "**本周跌幅榜**", HEAD] + [_row(q) for q in ranked[-bottom:][::-1]]
    return "\n".join(lines)


def build_data_pack(run_date: date | None = None) -> str:
    run_date = run_date or datetime.now(config.TZ).date()

    # 各市场最近一个交易日（以真实 K 线为准）
    us_gate = fetch_yahoo([GATE_INDEX["US"]], period="1mo")
    asia_gate, _ = fetch_tencent([GATE_INDEX["HK"], GATE_INDEX["CN"]], count=20)
    gate_frames = {"US": us_gate.get(GATE_INDEX["US"]), "HK": asia_gate.get(GATE_INDEX["HK"]),
                   "CN": asia_gate.get(GATE_INDEX["CN"])}
    sessions = {k: last_bar_date(df, not_after=run_date) for k, df in gate_frames.items()}

    parts = [f"# 周报数据包（生成于北京时间 {datetime.now(config.TZ):%Y-%m-%d %H:%M}）",
             "口径说明：本周% = 最近 5 个交易日涨跌幅；上周% = 再往前 5 个交易日的涨跌幅；近20日% = 最近 20 个交易日涨跌幅；"
             "周量能比 = 最近 5 日均量 / 此前 20 日均量；距50日线%、距52周高% 为最新收盘价相对该均线、相对 52 周最高价的偏离。"
             "板块为成分股等权平均。"]

    status_lines = []
    for key, sess in sessions.items():
        nxt = next_session_after(key, sess) if sess else None
        status_lines.append(f"- {MARKETS[key].name}：最近交易日 {fmt_day(sess)}，下一交易日 {fmt_day(nxt)}")
    parts.append("## 交易日\n" + "\n".join(status_lines))

    for key, sess in sessions.items():
        market = MARKETS[key]
        if sess is None:
            parts.append(f"## {market.name}\n（数据获取失败）")
            continue
        frames = fetch_market(market)
        quotes = build_quotes(market, frames, sess)
        stats = group_stats(market, quotes)
        log.info("%s：%d/%d 个标的有数据", market.name, len(quotes), len(all_codes(market)))

        block = [f"## {market.name}（截至 {fmt_day(sess)} 收盘）"]
        idx_rows = [_row(quotes[c]) for c in market.indices if c in quotes]
        if idx_rows:
            block.append("### 指数\n" + HEAD + "\n" + "\n".join(idx_rows))
        ctx_rows = [_row(quotes[c]) for c in market.context if c in quotes]
        if ctx_rows:
            block.append("### 背景指标（期货、利率、汇率、商品为最新值）\n" + HEAD + "\n" + "\n".join(ctx_rows))
        block.append("### 板块周度排名（★=AI/半导体重点板块）\n" + _group_table(stats))
        for g in market.groups:
            rows = [_row(quotes[c]) for c in g.members if c in quotes]
            if rows:
                block.append(f"### {g.name}{' ★' if g.focus else ''}\n" + HEAD + "\n" + "\n".join(rows))
        movers = _movers(key, quotes)
        if movers:
            block.append("### 本周个股/ETF 涨跌排行（剔除指数与背景指标）\n" + movers)
        parts.append("\n\n".join(block))

        if key == "CN":
            boards = board_rankings()
            if boards:
                parts.append(f"## A股板块榜（{fmt_day(sess)} 单日，来自新浪分类）\n{boards}")

    focus_codes = [c for g in US.groups if g.focus for c in g.members]
    start = min([s for s in sessions.values() if s] or [run_date])
    earnings = fetch_us_earnings(focus_codes, start=start, days=21)
    if earnings:
        parts.append("## 未来三周的美股 AI/半导体财报（来自雅虎，日期可能有 ±1 天误差）\n"
                     + "\n".join(f"- {d:%m-%d}（周{WEEKDAYS[d.weekday()]}）：{code}" for d, code in earnings))

    text = "\n\n".join(parts) + "\n"
    config.OUT_DIR.mkdir(exist_ok=True)
    path = config.OUT_DIR / "weekly_data.md"
    path.write_text(text, encoding="utf-8")
    return str(path)


def main() -> None:
    p = argparse.ArgumentParser(description="生成周报数据包")
    p.add_argument("--date", type=date.fromisoformat, help="北京日期 YYYY-MM-DD，默认今天")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("yfinance").setLevel(logging.CRITICAL)
    print("已生成：" + build_data_pack(args.date))


if __name__ == "__main__":
    main()
