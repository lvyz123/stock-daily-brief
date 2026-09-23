# 股市简报

复盘美股、港股、A股走势并展望后续板块机会，内容以美股 AI 科技与半导体为重点。

> **当前用法：每周手动生成周报**（`weekly-brief` 技能）。
> 原先的「每日 18:30 自动发邮件」方案因为拿不到 Anthropic API Key 已经停用，GitHub Actions 定时任务（`.github/workflows/daily_brief.yml`）已删除，仓库里不再有任何自动运行的东西。
> 日报代码（`main.py` 及 `brief/analyst.py`、`brief/mailer.py`）保留着，配好 API Key 和 SMTP 授权码后仍可手动运行；要恢复定时任务，用 `git show 61807b2:.github/workflows/daily_brief.yml > .github/workflows/daily_brief.yml` 取回。

## 周报（当前在用）

在任意会话里说「请生成每周股市简报」或 `/weekly-brief`，会依次：抓三地行情 → 联网核实涨跌原因与下周催化剂 → 按固定规则写报告 → 发布成网页 → 导出 PDF 到 `reports/` → 存档。规则写在 `.claude/skills/weekly-brief/SKILL.md`（同一份也放在 `~/.claude/skills/` 供全局使用）。

手动生成数据包和 PDF：

```bash
.venv/Scripts/python -m brief.weekly                      # 输出 out/weekly_data.md
.venv/Scripts/python -m brief.to_pdf <周报HTML> --date YYYY-MM-DD   # 输出 reports/weekly-*.pdf
```

## 日报（已停用，保留代码）

- **交易日判定**：北京时间 T 日 18:30 之前的 24 小时内，三地至少有一个市场开过市（美股看纽约日期 T-1，港股、A股看 T 日）。以当天是否真的有 K 线为准，取不到数据时改用交易所日历。
- **数据**：美股来自雅虎财经；港股、A股来自腾讯行情，取不到时依次换用新浪（A股）、雅虎（港股）；A股行业/概念板块榜来自新浪。
- **分析**：Claude Opus 5 加网络搜索。行情表是数字的唯一来源，搜索只用来查异动原因和近期催化剂。
- **邮件**：顶部是程序生成的行情快照（红涨绿跌），中间是分析正文，底部是近期推荐跟踪。

要手动跑一次日报，需要先设置这几个环境变量：`ANTHROPIC_API_KEY`（console.anthropic.com 创建）、`SMTP_USER`（发件 QQ 邮箱）、`SMTP_PASS`（QQ 邮箱 → 设置 → 账号 → POP3/SMTP 服务 → 生成的授权码，不是 QQ 密码）、`MAIL_TO`（收件邮箱），然后 `python main.py --no-wait`。每封的 API 费用约 0.8–1.5 美元，运行日志里会打印实际用量。

分析失败时仍会发一封只含行情快照的降级邮件；发送后报告和推荐存到 `reports/`，用于防重复、保持观点连贯和计算推荐的后续表现。

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
