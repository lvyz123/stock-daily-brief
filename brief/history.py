"""报告存档、上期正文读取、推荐跟踪。存档文件由 GitHub Actions 提交回仓库。"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date

import pandas as pd

from . import config


def report_path(d: date):
    return config.REPORTS_DIR / f"{d.isoformat()}.md"


def picks_path(d: date):
    return config.PICKS_DIR / f"{d.isoformat()}.json"


def already_sent(d: date) -> bool:
    return report_path(d).exists()


def normalize_code(market: str, code: str) -> str:
    code = str(code).strip()
    market = str(market).upper()
    if market == "US":
        return code.upper()
    digits = re.sub(r"\D", "", code)
    if market == "HK":
        return code if re.fullmatch(r"hk[A-Z]+", code) else f"hk{int(digits):05d}" if digits else code
    if market == "CN":
        if re.fullmatch(r"(sh|sz|bj)\d{6}", code.lower()):
            return code.lower()
        if len(digits) == 6:
            prefix = "sh" if digits[0] in "569" else "bj" if digits[0] in "48" else "sz"
            return prefix + digits
    return code


def save(d: date, subject: str, report_md: str, picks: list[dict]) -> None:
    config.PICKS_DIR.mkdir(parents=True, exist_ok=True)
    report_path(d).write_text(f"# {subject}\n\n{report_md}\n", encoding="utf-8")
    payload = {"date": d.isoformat(), "subject": subject, "picks": picks}
    picks_path(d).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def previous_report(before: date) -> tuple[date, str] | None:
    files = sorted(p for p in config.REPORTS_DIR.glob("????-??-??.md") if p.stem < before.isoformat())
    if not files:
        return None
    last = files[-1]
    return date.fromisoformat(last.stem), last.read_text(encoding="utf-8")


def recent_picks(before: date, issues: int) -> list[tuple[date, list[dict]]]:
    files = sorted(p for p in config.PICKS_DIR.glob("????-??-??.json") if p.stem < before.isoformat())
    out = []
    for p in files[-issues:]:
        data = json.loads(p.read_text(encoding="utf-8"))
        if data.get("picks"):
            out.append((date.fromisoformat(data["date"]), data["picks"]))
    return out


def latest_close(df: pd.DataFrame | None) -> float | None:
    if df is None or df.empty:
        return None
    return float(df["close"].iloc[-1])


@dataclass
class TrackRow:
    issued: date
    market: str
    code: str
    name: str
    segment: str
    horizon: str
    ref_price: float | None
    last_price: float | None

    @property
    def ret(self) -> float | None:
        if not self.ref_price or self.last_price is None:
            return None
        return (self.last_price / self.ref_price - 1) * 100


def track_rows(recent: list[tuple[date, list[dict]]], frames: dict[str, pd.DataFrame]) -> list[TrackRow]:
    rows = []
    for issued, picks in reversed(recent):  # 最新一期在前
        for p in picks:
            rows.append(TrackRow(
                issued=issued, market=p.get("market", ""), code=p["code"], name=p.get("name", p["code"]),
                segment=p.get("segment", ""), horizon=p.get("horizon", ""),
                ref_price=p.get("ref_price"), last_price=latest_close(frames.get(p["code"])),
            ))
    return rows


def track_table_for_llm(rows: list[TrackRow]) -> str:
    if not rows:
        return "（暂无历史推荐）"
    lines = ["| 推荐日 | 标的 | 细分 | 周期 | 推荐时价 | 最新价 | 至今涨跌% |", "|---|---|---|---|---|---|---|"]
    for r in rows:
        ret = "—" if r.ret is None else f"{r.ret:+.1f}"
        ref = "—" if r.ref_price is None else f"{r.ref_price:g}"
        last = "—" if r.last_price is None else f"{r.last_price:g}"
        lines.append(f"| {r.issued:%m-%d} | {r.name}（{r.code}） | {r.segment} | {r.horizon} | {ref} | {last} | {ret} |")
    return "\n".join(lines)
