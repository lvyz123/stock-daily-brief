from datetime import date

import pandas as pd
import pytest

from brief import config, history
from brief.analyst import AnalysisError, parse_output
from brief.render import markdown_to_html

SAMPLE = """我先查一下存储板块大涨的原因。
<subject>存储领涨费半，设备有望接力</subject>
<report>
## 今日要点
- 存储/HBM 板块 +6.5%，闪迪 +11.0%。

## 美股｜09月18日 复盘 · 09月21日 展望
### AI 与半导体
| 细分 | 当日 |
|---|---|
| 存储 | +6.5% |
</report>
<picks>
```json
[{"market": "US", "code": "mu", "name": "美光", "segment": "存储/HBM", "horizon": "1-3日", "confidence": "高", "thesis": "x"},
 {"market": "CN", "code": "300308", "name": "中际旭创", "segment": "光模块", "horizon": "1-2周", "confidence": "中", "thesis": "y"}]
```
</picks>"""


def test_parse_output_extracts_sections():
    a = parse_output(SAMPLE)
    assert a.subject == "存储领涨费半，设备有望接力"
    assert a.report_md.startswith("## 今日要点") and "我先查" not in a.report_md
    assert [p["code"] for p in a.picks] == ["mu", "300308"]


def test_parse_output_requires_report():
    with pytest.raises(AnalysisError):
        parse_output("<subject>x</subject>")


def test_markdown_to_html_styles_and_colors():
    html = markdown_to_html(parse_output(SAMPLE).report_md)
    assert '<table style="' in html and '<h2 style="' in html
    assert f'color:{config.UP_COLOR};font-weight:600;">+6.5%</span>' in html
    assert "width:100%" in html  # 样式里的百分比不会被着色


@pytest.mark.parametrize("market, code, expected", [
    ("US", "mu", "MU"),
    ("HK", "0981.HK", "hk00981"),
    ("HK", "hk00700", "hk00700"),
    ("CN", "300308", "sz300308"),
    ("CN", "688981.SH", "sh688981"),
    ("CN", "512480", "sh512480"),
    ("CN", "159995", "sz159995"),
])
def test_normalize_code(market, code, expected):
    assert history.normalize_code(market, code) == expected


def test_save_and_track(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "REPORTS_DIR", tmp_path)
    monkeypatch.setattr(config, "PICKS_DIR", tmp_path / "picks")
    picks = [{"market": "US", "code": "MU", "name": "美光", "segment": "存储", "horizon": "1-3日", "ref_price": 100.0}]
    history.save(date(2026, 9, 18), "标题", "正文", picks)
    history.save(date(2026, 9, 19), "标题2", "正文2", [])

    assert history.already_sent(date(2026, 9, 19))
    prev = history.previous_report(date(2026, 9, 19))
    assert prev[0] == date(2026, 9, 18) and "正文" in prev[1]

    recent = history.recent_picks(date(2026, 9, 21), issues=3)
    assert [d for d, _ in recent] == [date(2026, 9, 18)]  # 空推荐的那期被跳过
    frames = {"MU": pd.DataFrame({"close": [105.0]}, index=pd.to_datetime(["2026-09-19"]))}
    rows = history.track_rows(recent, frames)
    assert rows[0].ret == pytest.approx(5.0)
    assert "+5.0" in history.track_table_for_llm(rows)
