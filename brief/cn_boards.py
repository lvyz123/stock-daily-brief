"""A股新浪行业 / 概念板块当日涨跌榜（东方财富接口会拒绝海外 IP，所以用新浪）。取不到时返回空字符串。"""
from __future__ import annotations

import json
import logging

import requests

log = logging.getLogger(__name__)

SOURCES = {
    "行业板块": "https://vip.stock.finance.sina.com.cn/q/view/newSinaHy.php",
    "概念板块": "https://money.finance.sina.com.cn/q/view/newFLJK.php?param=class",
}
HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn"}
# 不是真正的行业/主题，排名没有参考意义
EXCLUDE = {"次新股", "开发区", "ST板块", "其它行业", "其他行业"}


def _fetch(url: str) -> list[dict]:
    r = requests.get(url, headers=HEADERS, timeout=15)
    r.raise_for_status()
    r.encoding = "gbk"
    text = r.text
    payload = json.loads(text[text.index("{"): text.rindex("}") + 1])
    boards = []
    for raw in payload.values():
        f = raw.split(",")
        # 代码, 名称, 成分数, 均价, 涨跌额, 涨跌幅, 成交量, 成交额, 领涨股代码, 领涨涨幅, 领涨价, 领涨涨跌额, 领涨股名称
        try:
            boards.append({"name": f[1], "n": int(f[2]), "chg": float(f[5]), "leader": f[12], "leader_chg": float(f[9])})
        except (IndexError, ValueError):
            continue
    return boards


def board_rankings(top: int = 12, bottom: int = 5, min_members: int = 8) -> str:
    parts = []
    for label, url in SOURCES.items():
        try:
            boards = [b for b in _fetch(url) if b["n"] >= min_members and b["name"] not in EXCLUDE]
        except Exception as e:
            log.warning("新浪%s获取失败：%s", label, e)
            continue
        if not boards:
            continue
        boards.sort(key=lambda b: b["chg"], reverse=True)

        def line(b: dict) -> str:
            return f"| {b['name']} | {b['chg']:+.2f} | {b['n']} | {b['leader']} {b['leader_chg']:+.1f} |"

        head = f"#### {label}（新浪分类，当日等权涨跌幅）\n| 板块 | 涨跌% | 成分数 | 领涨股 |\n|---|---|---|---|"
        rows = [line(b) for b in boards[:top]] + ["| … | | | |"] + [line(b) for b in boards[-bottom:]]
        parts.append(head + "\n" + "\n".join(rows))
    return "\n\n".join(parts)
