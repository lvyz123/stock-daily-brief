# 每日股市简报

每个股票交易日北京时间 18:30 自动发送一封中文邮件：复盘过去 24 小时内开过市的美股、港股、A股，并展望下一交易日的板块机会。内容以美股 AI 科技与半导体为重点。

- **交易日判定**：北京时间 T 日 18:30 之前的 24 小时内，三地至少有一个市场开过市（美股看纽约日期 T-1，港股、A股看 T 日）。以当天是否真的有 K 线为准，取不到数据时改用交易所日历。
- **数据**：美股来自雅虎财经；港股、A股来自腾讯行情，取不到时依次换用新浪（A股）、雅虎（港股）；A股行业/概念板块榜来自新浪。
- **分析**：Claude Opus 5 加网络搜索。行情表是数字的唯一来源，搜索只用来查异动原因和近期催化剂。
- **邮件**：顶部是程序生成的行情快照（红涨绿跌），中间是分析正文，底部是近期推荐跟踪。

## 部署

1. 在 GitHub 新建**私有**仓库，把本目录推上去。
2. 在仓库的 Settings → Secrets and variables → Actions → New repository secret 里添加：

   | Name | 值 |
   |---|---|
   | `ANTHROPIC_API_KEY` | 在 console.anthropic.com 创建的 API Key |
   | `SMTP_USER` | 发件 QQ 邮箱，如 `819320358@qq.com` |
   | `SMTP_PASS` | QQ 邮箱授权码（设置 → 账号 → POP3/SMTP 服务 → 生成授权码），不是 QQ 密码 |
   | `MAIL_TO` | 收件邮箱 |

3. 在 Actions 页面手动运行一次 **每日股市简报**，确认能正常工作（见下一节）。之后每天会自动运行。

## 手动测试（Actions → 每日股市简报 → Run workflow）

| 选项 | 作用 |
|---|---|
| `dry_run`（默认勾选） | 只生成预览，不发邮件。运行结束后在该次运行页面底部的 Artifacts 下载 `preview`，里面有 `preview.html`（邮件效果）、`report.md`（正文）、`prompt.md`（给 Claude 的输入）。 |
| `force` | 周末、节假日也能测：用各市场最近一个交易日的数据生成。 |
| `skip_llm` | 不调用 Claude，只测数据抓取和邮件排版，不产生 API 费用。 |
| `archive` | 发送后存档。默认不存档，这样白天的测试不会挡住当晚 18:30 的定时发送。 |

想收到一封真实的测试邮件：取消勾选 `dry_run`，并勾选 `force`。

## 运行机制

- 定时任务在北京时间 18:05 触发，生成大约需要 5–10 分钟，然后等到 18:30 发送。GitHub 的定时任务经常延迟，所以 18:35 还有一次兜底触发：如果当天已经发送过，它会直接退出。
- 发送后，报告和推荐会存到 `reports/` 并提交回仓库。这份存档用来防止重复发送、在第二天的分析里保持观点连贯，以及计算推荐的后续表现。
- Claude 分析失败时，仍然会发一封只含行情快照的邮件。
- 运行日志里会打印每次的 token 用量和估算费用，大约每封 0.8–1.5 美元。

## 本地运行

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt pytest   # macOS/Linux 用 .venv/bin/pip
.venv/Scripts/python -m pytest -q
.venv/Scripts/python main.py --skip-llm --dry-run --force   # 不需要任何密钥，输出 out/preview.html
.venv/Scripts/python -m brief.market_data                   # 检查所有代码是否都能取到数据
```

`main.py` 的参数：`--dry-run`、`--skip-llm`、`--force`、`--no-wait`（不等 18:30）、`--no-archive`、`--date YYYY-MM-DD`、`--to 其他邮箱`。

## 自定义

- **关注的板块和标的**：编辑 `brief/universe.py`。美股用雅虎代码，港股、A股用腾讯代码（`hk00700`、`sh512480`、`sz300308`）。改完运行 `python -m brief.market_data`，确认每个代码都有数据。
- **写作风格和取舍规则**：编辑 `brief/prompts.py` 里的 `SYSTEM_PROMPT`。
- **模型等参数**：在 workflow 的“生成并发送”这一步的 `env` 下添加环境变量：`BRIEF_MODEL`（默认 `claude-opus-5`）、`BRIEF_EFFORT`（默认 `high`）、`BRIEF_WEB_SEARCH_MAX_USES`（默认 12）、`BRIEF_SHOW_TRACK_RECORD`（`0` 关闭推荐跟踪）、`BRIEF_TRACK_RECORD_ISSUES`（默认跟踪最近 3 期）。

## 文件结构

```
main.py                   入口
brief/calendar_gate.py    交易日判定
brief/universe.py         板块与标的
brief/market_data.py      行情抓取与指标
brief/cn_boards.py        A股板块榜
brief/prompts.py          提示词
brief/analyst.py          调用 Claude
brief/render.py           邮件 HTML
brief/mailer.py           SMTP 发送
brief/history.py          存档与推荐跟踪
reports/                  每日存档（由 Actions 自动提交）
```

免责声明：邮件内容由 AI 自动生成，仅供参考，不构成投资建议。
