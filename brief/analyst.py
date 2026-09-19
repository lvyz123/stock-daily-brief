"""调用 Claude 生成分析正文。"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

import anthropic

from . import config
from .prompts import SYSTEM_PROMPT

log = logging.getLogger(__name__)

# Opus 5 每百万 token 价格（美元），web search 每千次 10 美元。仅用于日志里的费用估算。
PRICE_IN, PRICE_OUT, PRICE_SEARCH = 5.0, 25.0, 10.0 / 1000


class AnalysisError(RuntimeError):
    pass


@dataclass
class Analysis:
    subject: str
    report_md: str
    picks: list[dict] = field(default_factory=list)
    usage_note: str = ""


def _tag(text: str, name: str) -> str | None:
    m = re.search(rf"<{name}>(.*?)</{name}>", text, re.S)
    return m.group(1).strip() if m else None


def parse_output(text: str) -> Analysis:
    report = _tag(text, "report")
    if not report:
        raise AnalysisError("模型输出里没有 <report> 段")
    subject = (_tag(text, "subject") or "").replace("\n", " ").strip()
    picks: list[dict] = []
    raw_picks = _tag(text, "picks")
    if raw_picks:
        raw_picks = re.sub(r"^```(?:json)?|```$", "", raw_picks.strip(), flags=re.M).strip()
        try:
            loaded = json.loads(raw_picks)
            picks = [p for p in loaded if isinstance(p, dict) and p.get("code")] if isinstance(loaded, list) else []
        except json.JSONDecodeError as e:
            log.warning("推荐 JSON 解析失败：%s", e)
    return Analysis(subject=subject, report_md=report, picks=picks)


def run_analysis(user_content: str) -> Analysis:
    client = anthropic.Anthropic(max_retries=4, timeout=1200)
    tools = [{"type": "web_search_20260209", "name": "web_search", "max_uses": config.WEB_SEARCH_MAX_USES}]
    assistant_blocks: list = []
    tokens_in = tokens_out = searches = 0

    for _ in range(config.MAX_PAUSE_CONTINUATIONS + 1):
        messages = [{"role": "user", "content": user_content}]
        if assistant_blocks:  # pause_turn：把已完成的部分交回去，让服务端接着跑
            messages.append({"role": "assistant", "content": assistant_blocks})
        with client.beta.messages.stream(
            model=config.MODEL,
            max_tokens=64000,
            system=SYSTEM_PROMPT,
            messages=messages,
            tools=tools,
            thinking={"type": "adaptive"},
            output_config={"effort": config.EFFORT},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        ) as stream:
            msg = stream.get_final_message()

        u = msg.usage
        tokens_in += (u.input_tokens or 0) + (u.cache_read_input_tokens or 0) + (u.cache_creation_input_tokens or 0)
        tokens_out += u.output_tokens or 0
        if u.server_tool_use:
            searches += u.server_tool_use.web_search_requests or 0

        if msg.stop_reason == "refusal":
            raise AnalysisError(f"模型拒绝回答：{msg.stop_details}")
        assistant_blocks += list(msg.content)
        if msg.stop_reason != "pause_turn":
            break
        log.info("pause_turn，继续生成")

    if msg.stop_reason == "max_tokens":
        log.warning("输出达到 max_tokens 上限，正文可能不完整")
    text = "".join(b.text for b in assistant_blocks if b.type == "text")
    cost = tokens_in / 1e6 * PRICE_IN + tokens_out / 1e6 * PRICE_OUT + searches * PRICE_SEARCH
    note = f"模型 {msg.model}，输入 {tokens_in:,} tokens，输出 {tokens_out:,} tokens，搜索 {searches} 次，估算费用 ${cost:.2f}"
    log.info(note)

    result = parse_output(text)
    result.usage_note = note
    return result
