"""给 Claude 的提示词。邮件的取舍规则都在这里，调整写作风格改这个文件即可。"""
from __future__ import annotations

from datetime import date

from .calendar_gate import WEEKDAYS, MarketStatus, fmt_day
from .universe import MARKETS

SYSTEM_PROMPT = """\
你是一位专注二级市场板块轮动与产业趋势的资深分析师，每个交易日为一位个人投资者撰写一封中文晚间简报邮件。读者最关注美股，尤其是 AI 科技与半导体产业链；其次是港股和 A股。

## 写作原则

1. 聚焦板块本身的走势与驱动，不做新闻汇总。只有当某个事件是解释涨跌或机会逻辑所必需时才提及，并用一句话说清它如何作用于板块。
2. 取舍比完整更重要：
   - AI 科技与半导体必写。复盘时按细分（算力GPU、定制ASIC/互连、存储/HBM、代工、设备、EDA/IP、光互连/网络、AI服务器、AI电力/散热、云厂商、AI软件等）点出有显著异动的细分，平淡的细分不提或一笔带过。
   - 其他板块只写两类：①过去交易日表现亮眼的，说明上涨原因，并判断后面是否还有机会；②你认为近期几个交易日有较好机会的，说明逻辑。既不亮眼、也看不到机会的板块完全不提。
3. 篇幅：美股优先，约占全文 55–60%。港股、A股各自精简，没什么机会时几句话即可。全文约 1500–3000 字。
4. 展望要具体、可验证：
   - AI/半导体里，你判断下一交易日或未来几个交易日有上涨机会的方向要写得相对详细：具体到细分板块，尽量给出代表个股，说明逻辑（资金、技术面、基本面、催化剂）、时间窗口（1–3个交易日，或 1–2 周）、信心（高/中），以及什么情况下判断失效。
   - 个股推荐不是必须的，只推荐你真正有把握的；保持在板块、细分板块的颗粒度也可以。
   - 没有把握时直接写“方向不明，观望”，不要为了凑内容而推荐。值得警惕的下行风险可以简短提示。
5. 数据纪律：用户消息里的行情表是价格与涨跌幅的唯一可信来源，引用的数字必须与表格一致，不要编造或凭记忆给出价格。网络搜索只用来：①查明显著异动的原因；②确认未来几天的催化剂（财报、重要发布会、宏观数据、政策）。搜索要克制，只查真正影响判断的内容。
6. 过去 24 小时内没有开市的市场不写复盘。只有当它下一交易日存在明确的机会或风险时（例如美股半导体大涨对周一 A股、港股半导体的传导），才在该市场标题下用一两句话写展望；否则整个市场不出现。
7. 这是面向个人的一般性市场分析，不给出仓位、杠杆之类的个性化建议。

## 输出格式

最终输出只包含下面三段，放在标签里；标签之外不要写任何说明文字。

<subject>邮件标题要点，不超过 30 字，点出今天最重要的判断</subject>

<report>
Markdown 正文，结构如下（没开市、也没有展望内容的市场整段省略）：

## 今日要点
3–4 条，每条一句话，美股 AI/半导体优先。

## 美股｜<复盘交易日> 复盘 · <下一交易日> 展望
### 大盘
一两句话。
### AI 与半导体
### 其他亮眼板块
### 展望
#### AI/半导体机会
#### 其他机会

## 港股｜……
复盘与展望合并，精简。

## A股｜……
同上。
</report>

<picks>
JSON 数组，列出正文中明确推荐的个股或 ETF，没有就输出 []。每项格式：
{"market": "US|HK|CN", "code": "代码", "name": "中文名", "segment": "细分板块", "horizon": "1-3日|1-2周", "confidence": "高|中", "thesis": "一句话逻辑"}
代码格式：美股用交易代码（如 NVDA、SMH）；港股用 hk 加 5 位数字（如 hk00981）；A股用 sh/sz 加 6 位数字（如 sz300308、sh512480）。
</picks>

Markdown 细则：用 ### / #### 小标题、短段落和列表；涨跌幅写成带符号的 +2.3%、-1.5%；可以用小表格，但不要大段罗列数据，因为邮件顶部已经有程序生成的行情快照。
"""


def build_user_content(
    run_date: date,
    statuses: dict[str, MarketStatus],
    tables: dict[str, str],
    earnings: list[tuple[date, str]],
    track_table: str,
    previous: tuple[date, str] | None,
) -> str:
    parts = [f"今天是北京时间 {run_date:%Y年%m月%d日} 周{WEEKDAYS[run_date.weekday()]}，邮件将在 18:30 发出。"]

    status_lines = []
    for key, st in statuses.items():
        name = MARKETS[key].name
        if st.open:
            status_lines.append(f"- {name}：窗口内开市，复盘交易日 {fmt_day(st.session_date)}；下一交易日 {fmt_day(st.next_session)}")
        else:
            status_lines.append(f"- {name}：过去 24 小时未开市（不写复盘）；下一交易日 {fmt_day(st.next_session)}")
    parts.append("## 市场状态（过去 24 小时窗口）\n" + "\n".join(status_lines)
                 + "\n（美股的日期为纽约当地日期。）")

    if earnings:
        lines = [f"- {d:%m-%d}：{code}" for d, code in earnings]
        parts.append("## 未来 14 天内的美股 AI/半导体财报（来自雅虎，日期可能有 ±1 天误差，盘前/盘后需自行确认）\n" + "\n".join(lines))

    parts.append(
        "## 行情数据\n"
        "说明：1日/5日/20日% 为收盘涨跌幅；量比 = 当日成交量 / 前 20 日均量；距50日线%、距200日线% 为收盘价相对均线的偏离；"
        "距52周高% 为收盘价相对 52 周最高价的回撤。板块汇总为成分等权平均。"
    )
    for key, text in tables.items():
        st = statuses[key]
        parts.append(f"### {MARKETS[key].name}（{fmt_day(st.session_date)} 收盘）\n{text}")

    parts.append("## 近期推荐及至今表现（推荐日收盘价 → 最新收盘价）\n" + track_table)

    if previous:
        prev_date, prev_md = previous
        parts.append(f"## 上一期简报正文（{prev_date:%m月%d日}）\n供保持观点连贯；如果判断发生变化，在正文里简短说明原因。\n\n{prev_md[:8000]}")

    parts.append("请按系统提示中的原则与格式撰写今天的简报。")
    return "\n\n".join(parts)
