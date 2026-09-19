"""每日股市简报入口。

用法：
  python main.py                 正式运行：判定交易日 → 生成 → 等到 18:30 → 发送 → 存档
  python main.py --dry-run       只生成 out/preview.html，不发送、不存档
  python main.py --skip-llm      不调用 Claude（验证数据与排版，无需 API Key）
  python main.py --force         无视“已发送”和“今天不是交易日”，用各市场最近一个交易日生成
  python main.py --no-wait       生成后立即发送，不等 18:30
  python main.py --no-archive    发送后不存档（手动测试用，避免挡住当天的定时发送）
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import date, datetime

from brief import config, history
from brief.analyst import Analysis, run_analysis
from brief.calendar_gate import WEEKDAYS, review_date, resolve
from brief.cn_boards import board_rankings
from brief.market_data import (build_quotes, fetch_codes, fetch_market, fetch_tencent, fetch_us_earnings,
                               fetch_yahoo, group_stats, last_bar_date, market_tables)
from brief.mailer import send
from brief.prompts import build_user_content
from brief.render import build_email, markdown_to_html, snapshot_html, track_html
from brief.universe import GATE_INDEX, MARKETS, US

log = logging.getLogger("brief")


def gate_last_bars(run_date: date) -> dict[str, date | None]:
    """各市场代表指数不晚于应复盘日的最新 K 线日期。"""
    us = fetch_yahoo([GATE_INDEX["US"]], period="1mo")
    asia, _ = fetch_tencent([GATE_INDEX["HK"], GATE_INDEX["CN"]], count=20)
    frames = {"US": us.get(GATE_INDEX["US"]), "HK": asia.get(GATE_INDEX["HK"]), "CN": asia.get(GATE_INDEX["CN"])}
    return {k: last_bar_date(df, not_after=review_date(k, run_date)) for k, df in frames.items()}


def wait_until_send_time() -> None:
    now = datetime.now(config.TZ)
    target = now.replace(hour=config.SEND_HOUR, minute=config.SEND_MINUTE, second=0, microsecond=0)
    if now < target:
        secs = (target - now).total_seconds()
        log.info("等待 %.0f 秒，到 %s 发送", secs, target.strftime("%H:%M"))
        time.sleep(secs)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="每日股市简报")
    p.add_argument("--date", type=date.fromisoformat, help="北京日期 YYYY-MM-DD，默认今天")
    p.add_argument("--force", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--skip-llm", action="store_true")
    p.add_argument("--no-wait", action="store_true")
    p.add_argument("--no-archive", action="store_true")
    p.add_argument("--to", help="覆盖收件人（测试用）")
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("yfinance").setLevel(logging.CRITICAL)
    run_date = args.date or datetime.now(config.TZ).date()
    weekday = WEEKDAYS[run_date.weekday()]

    if history.already_sent(run_date) and not (args.force or args.dry_run):
        log.info("%s 的简报已发送过，跳过", run_date)
        return 0

    # 1. 交易日判定
    statuses = resolve(run_date, gate_last_bars(run_date), force=args.force)
    for st in statuses.values():
        log.info("%s：%s，复盘日 %s，下一交易日 %s（依据：%s）", st.key, "开市" if st.open else "未开市",
                 st.session_date, st.next_session, st.source)
    open_keys = [k for k, st in statuses.items() if st.open]
    if not open_keys:
        log.info("过去 24 小时三地均未开市，今天不发送")
        return 0

    # 2. 行情
    quotes, stats, tables = {}, {}, {}
    for key in open_keys:
        market = MARKETS[key]
        frames = fetch_market(market)
        quotes[key] = build_quotes(market, frames, statuses[key].session_date)
        stats[key] = group_stats(market, quotes[key])
        tables[key] = market_tables(market, quotes[key], stats[key])
        log.info("%s：%d 个标的有数据", market.name, len(quotes[key]))
    if "CN" in open_keys:
        boards = board_rankings()
        if boards:
            tables["CN"] += "\n\n" + boards

    earnings = []
    if "US" in open_keys:
        focus_codes = [c for g in US.groups if g.focus for c in g.members]
        earnings = fetch_us_earnings(focus_codes, start=run_date)

    # 3. 推荐跟踪（上期推荐的最新价格）
    recent = history.recent_picks(run_date, config.TRACK_RECORD_ISSUES)
    track_codes = [pk["code"] for _, picks in recent for pk in picks]
    track_frames = fetch_codes(track_codes) if track_codes else {}
    track = history.track_rows(recent, track_frames)

    # 4. 分析
    user_content = build_user_content(run_date, statuses, tables, earnings,
                                      history.track_table_for_llm(track), history.previous_report(run_date))
    config.OUT_DIR.mkdir(exist_ok=True)
    (config.OUT_DIR / "prompt.md").write_text(user_content, encoding="utf-8")

    if args.skip_llm:
        analysis = Analysis(subject="（skip-llm 模式，未调用分析）", report_md="*skip-llm 模式：仅验证数据与排版。*")
    else:
        try:
            analysis = run_analysis(user_content)
        except Exception as e:
            log.exception("分析生成失败")
            analysis = Analysis(subject="分析生成失败，仅含行情快照",
                                report_md=f"> 今日 AI 分析生成失败（{type(e).__name__}），以下仅为程序生成的行情快照。")

    # 推荐：统一代码格式，记录推荐时价格
    picks = []
    for pk in analysis.picks:
        pk["code"] = history.normalize_code(pk.get("market", ""), pk["code"])
        picks.append(pk)
    if picks:
        ref_frames = fetch_codes([pk["code"] for pk in picks])
        for pk in picks:
            pk["ref_price"] = history.latest_close(ref_frames.get(pk["code"]))

    # 5. 渲染
    subject = f"股市日报 {run_date:%m月%d日} 周{weekday}｜{analysis.subject or '今日简报'}"
    track_block = track_html(track) if config.SHOW_TRACK_RECORD else ""
    email_html = build_email(run_date, analysis.subject or "今日简报",
                             snapshot_html(statuses, quotes, stats), markdown_to_html(analysis.report_md),
                             track_block, analysis.usage_note)
    text_body = f"{subject}\n\n{analysis.report_md}\n\n以上内容由 AI 自动生成，仅供参考，不构成投资建议。"
    (config.OUT_DIR / "preview.html").write_text(email_html, encoding="utf-8")
    (config.OUT_DIR / "report.md").write_text(f"# {subject}\n\n{analysis.report_md}\n", encoding="utf-8")
    log.info("已生成 %s", config.OUT_DIR / "preview.html")

    if args.dry_run:
        log.info("dry-run：不发送、不存档")
        return 0

    # 6. 发送与存档
    if not args.no_wait:
        wait_until_send_time()
    send(subject, email_html, text_body, to=args.to)
    if not args.no_archive:
        history.save(run_date, analysis.subject, analysis.report_md, picks)
    return 0


if __name__ == "__main__":
    sys.exit(main())
