"""把行情快照、分析正文、推荐跟踪渲染成邮件 HTML（全部内联样式，兼容 QQ 邮箱）。"""
from __future__ import annotations

import html
import re
from datetime import date

import markdown as md

from . import config
from .calendar_gate import MarketStatus, fmt_day
from .history import TrackRow
from .market_data import GroupStat, Quote, fmt_pct
from .universe import MARKETS

FONT = "-apple-system,'PingFang SC','Hiragino Sans GB','Microsoft YaHei',sans-serif"
MUTED = "#6b7280"
BORDER = "#e5e7eb"

TAG_STYLES = {
    "h2": "font-size:18px;margin:28px 0 10px;padding-bottom:6px;border-bottom:2px solid #1f2937;color:#111827;",
    "h3": "font-size:16px;margin:20px 0 8px;color:#111827;",
    "h4": "font-size:15px;margin:14px 0 6px;color:#374151;",
    "p": "margin:8px 0;",
    "ul": "margin:6px 0;padding-left:20px;",
    "ol": "margin:6px 0;padding-left:20px;",
    "li": "margin:4px 0;",
    "table": "border-collapse:collapse;width:100%;font-size:13px;margin:8px 0;",
    "th": f"background:#f3f4f6;padding:6px 8px;border:1px solid {BORDER};text-align:left;white-space:nowrap;",
    "td": f"padding:6px 8px;border:1px solid {BORDER};",
    "blockquote": f"border-left:3px solid #d1d5db;margin:8px 0;padding:4px 12px;color:#4b5563;",
    "hr": f"border:none;border-top:1px solid {BORDER};margin:20px 0;",
}

PCT_RE = re.compile(r"(?<![\w.%])([+\-−]\d+(?:\.\d+)?%)")


def _color(v: float | None) -> str:
    if v is None or abs(v) < 0.005:
        return "#374151"
    return config.UP_COLOR if v > 0 else config.DOWN_COLOR


def _pct_cell(v: float | None, digits: int = 2) -> str:
    return f'<span style="color:{_color(v)};font-weight:600;">{fmt_pct(v, digits)}%</span>' if v is not None else "—"


def _inline_styles(fragment: str) -> str:
    def repl(m: re.Match) -> str:
        tag, attrs = m.group(1), m.group(2) or ""
        style = TAG_STYLES[tag]
        if "style=" in attrs:
            attrs = re.sub(r'style="([^"]*)"', lambda s: f'style="{style}{s.group(1)}"', attrs)
            return f"<{tag}{attrs}>"
        return f'<{tag} style="{style}"{attrs}>'

    return re.sub(rf"<({'|'.join(TAG_STYLES)})(\s[^>]*)?>", repl, fragment)


def _color_percentages(fragment: str) -> str:
    parts = re.split(r"(<[^>]+>)", fragment)
    for i, part in enumerate(parts):
        if part.startswith("<"):
            continue

        def repl(m: re.Match) -> str:
            sign = m.group(1)[0]
            color = config.UP_COLOR if sign == "+" else config.DOWN_COLOR
            return f'<span style="color:{color};font-weight:600;">{m.group(1)}</span>'

        parts[i] = PCT_RE.sub(repl, part)
    return "".join(parts)


def markdown_to_html(text: str) -> str:
    body = md.markdown(text, extensions=["tables", "sane_lists"])
    return _inline_styles(_color_percentages(body))


def _table(headers: list[str], rows: list[list[str]]) -> str:
    th = "".join(f"<th>{h}</th>" for h in headers)
    trs = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return _inline_styles(f"<table><tr>{th}</tr>{trs}</table>")


def snapshot_html(statuses: dict[str, MarketStatus], quotes: dict[str, dict[str, Quote]],
                  stats: dict[str, list[GroupStat]]) -> str:
    blocks = []
    for key, st in statuses.items():
        if not st.open or key not in quotes:
            continue
        market, q = MARKETS[key], quotes[key]
        rows = [[name, f"{q[c].close:,.2f}", _pct_cell(q[c].chg_1d), _pct_cell(q[c].chg_5d)]
                for c, name in market.indices.items() if c in q]
        block = [f'<div style="font-weight:700;margin:14px 0 4px;">{market.name} · {fmt_day(st.session_date)}</div>',
                 _table(["指数", "收盘", "当日", "5日"], rows)]

        focus = [s for s in stats.get(key, []) if s.focus and s.n and s.chg_1d is not None and "基准" not in s.name]
        if key == "US" and focus:
            seg_rows = [[s.name, _pct_cell(s.chg_1d), _pct_cell(s.chg_5d),
                         f"{html.escape(s.best.name)} {_pct_cell(s.best.chg_1d, 1)}" if s.best else "—"]
                        for s in sorted(focus, key=lambda s: s.chg_1d, reverse=True)]
            block.append(_table(["AI/半导体细分（等权）", "当日", "5日", "当日最强"], seg_rows))
            futures = [f"{q[c].name} {_pct_cell(q[c].chg_1d)}" for c in ("ES=F", "NQ=F") if c in q]
            if futures:
                block.append(f'<div style="font-size:13px;color:{MUTED};">期货（截至发信时，相对上一结算）：{"，".join(futures)}</div>')
        elif focus:
            line = "，".join(f"{s.name} {_pct_cell(s.chg_1d)}" for s in focus)
            block.append(f'<div style="font-size:13px;margin:4px 0;">AI/半导体（等权当日）：{line}</div>')
        blocks.append("".join(block))
    if not blocks:
        return ""
    return ('<div style="background:#fafaf9;border:1px solid #e7e5e4;border-radius:8px;padding:4px 12px 12px;margin:12px 0;">'
            '<div style="font-size:13px;color:#78716c;margin-top:8px;">行情快照（程序生成，红涨绿跌）</div>'
            + "".join(blocks) + "</div>")


def track_html(rows: list[TrackRow]) -> str:
    if not rows:
        return ""
    body = [[f"{r.issued:%m-%d}", html.escape(f"{r.name}"), html.escape(r.segment), html.escape(r.horizon), _pct_cell(r.ret, 1)]
            for r in rows]
    valid = [r.ret for r in rows if r.ret is not None]
    summary = ""
    if valid:
        wins = sum(1 for v in valid if v > 0)
        summary = (f'<div style="font-size:13px;color:{MUTED};">共 {len(valid)} 只，上涨 {wins} 只，'
                   f'平均 {_pct_cell(sum(valid) / len(valid), 1)}（按推荐日收盘价至最新收盘价）</div>')
    return ('<h3 style="' + TAG_STYLES["h3"] + '">近期推荐跟踪</h3>'
            + _table(["推荐日", "标的", "细分", "周期", "至今"], body) + summary)


def build_email(run_date: date, subject: str, snapshot: str, body_html: str, track: str, footer_note: str = "") -> str:
    weekday = "一二三四五六日"[run_date.weekday()]
    footer = "以上内容由 AI 基于公开行情数据自动生成，仅供参考，不构成投资建议。"
    if footer_note:
        footer += f"<br>{html.escape(footer_note)}"
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f5f5f4;">
<div style="max-width:760px;margin:0 auto;padding:18px 16px 28px;font-family:{FONT};font-size:15px;line-height:1.75;color:#1f2937;background:#ffffff;">
<div style="font-size:13px;color:{MUTED};">{run_date:%Y-%m-%d} 周{weekday} · 每日股市简报</div>
<div style="font-size:20px;font-weight:700;margin:4px 0 8px;color:#111827;">{html.escape(subject)}</div>
{snapshot}
{body_html}
{track}
<hr style="{TAG_STYLES['hr']}">
<div style="font-size:12px;color:#9ca3af;">{footer}</div>
</div></body></html>"""
