"""把周报网页转成可当附件分享的本地 PDF（用系统里的 Edge / Chrome 无头模式打印）。

用法：
  python -m brief.to_pdf <周报HTML> [--date 2026-09-20] [--out-dir reports]

输入是发布 Artifact 用的那份 HTML（没有 <!doctype>/<head> 也可以，本模块会补上打印用的外壳）。
输出：reports/weekly-<date>.html（自带打印样式、可直接双击打开）和 reports/weekly-<date>.pdf。
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import date, datetime
from pathlib import Path

from . import config

BROWSERS = [
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    "/usr/bin/microsoft-edge",
    "/usr/bin/google-chrome",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
]

# 打印外壳：强制浅色、改用系统字体（不依赖 Google Fonts，避免国内网络下渲染卡住）、控制分页
PRINT_STYLE = """
<style>
  :root {
    --bg: #ffffff; --surface: #ffffff; --surface-2: #f2f1ed;
    --ink: #16181c; --ink-2: #33383f; --muted: #6a707a;
    --line: #d9d6ce; --line-strong: #b9b5ab;
    --accent: #1f4e79; --accent-soft: #eaf1f7;
    --up: #c1272d; --down: #0f7a52;
    --serif: "Songti SC", "SimSun", Georgia, serif;
    --sans: "Microsoft YaHei", "PingFang SC", "Hiragino Sans GB", "Noto Sans CJK SC", sans-serif;
    --mono: Consolas, "Courier New", "Microsoft YaHei", monospace;
  }
  @page { size: A4; margin: 14mm 12mm 12mm; }
  body { background: #fff; font-size: 10.5pt; line-height: 1.65; }
  .wrap { max-width: none; padding-inline: 0; padding-block: 0 0; }
  h1 { font-size: 26pt; }
  h2 { font-size: 14pt; margin-top: 20pt; break-after: avoid; page-break-after: avoid; }
  h3 { font-size: 12pt; break-after: avoid; page-break-after: avoid; }
  h4 { break-after: avoid; page-break-after: avoid; }
  section, figure, .callout, .market-card, .keypoints li, .table-wrap, .cal-item {
    break-inside: avoid; page-break-inside: avoid;
  }
  .snapshot { grid-template-columns: repeat(3, 1fr); }
  table { min-width: 0; font-size: 9.5pt; }
  .table-wrap { overflow: visible; }
  td, th { padding: 6px 8px; }
  a { color: inherit; text-decoration: none; }
  footer { margin-top: 24pt; }
</style>
"""


def wrap_for_print(page_html: str, title: str = "每周股市简报") -> str:
    return (
        '<!doctype html>\n<html lang="zh-CN">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{title}</title>\n"
        "<style>img{max-width:100%}body{margin:0}</style>\n</head>\n<body>\n"
        + page_html
        + "\n" + PRINT_STYLE + "\n</body>\n</html>\n"
    )


def find_browser() -> str:
    env = os.getenv("BRIEF_BROWSER")
    if env and Path(env).exists():
        return env
    for path in BROWSERS:
        if Path(path).exists():
            return path
    for name in ("msedge", "chrome", "google-chrome", "chromium"):
        found = shutil.which(name)
        if found:
            return found
    raise RuntimeError("找不到 Edge 或 Chrome，无法生成 PDF；可用环境变量 BRIEF_BROWSER 指定浏览器路径")


def html_to_pdf(html_path: Path, pdf_path: Path, timeout: int = 180) -> Path:
    browser = find_browser()
    with tempfile.TemporaryDirectory(prefix="brief-pdf-") as profile:
        cmd = [
            browser,
            "--headless=new",
            "--disable-gpu",
            "--no-first-run",
            "--no-default-browser-check",
            f"--user-data-dir={profile}",
            "--no-pdf-header-footer",
            "--print-to-pdf-no-header",  # 旧版本用的开关，新版本忽略
            "--virtual-time-budget=8000",
            f"--print-to-pdf={pdf_path}",
            html_path.resolve().as_uri(),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if not pdf_path.exists() or pdf_path.stat().st_size < 5000:
        raise RuntimeError(f"PDF 生成失败（{browser}）：{proc.stderr[-800:] or proc.stdout[-800:]}")
    return pdf_path


def export(page_html_path: Path, run_date: date | None = None, out_dir: Path | None = None) -> tuple[Path, Path]:
    run_date = run_date or datetime.now(config.TZ).date()
    out_dir = out_dir or config.REPORTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    page_html = page_html_path.read_text(encoding="utf-8")
    html_out = out_dir / f"weekly-{run_date.isoformat()}.html"
    html_out.write_text(wrap_for_print(page_html, f"每周股市简报 {run_date.isoformat()}"), encoding="utf-8")

    pdf_out = out_dir / f"weekly-{run_date.isoformat()}.pdf"
    html_to_pdf(html_out, pdf_out)
    return html_out, pdf_out


def main() -> None:
    p = argparse.ArgumentParser(description="周报网页转 PDF")
    p.add_argument("page", type=Path, help="周报 HTML（发布 Artifact 用的那份）")
    p.add_argument("--date", type=date.fromisoformat, help="北京日期 YYYY-MM-DD，默认今天")
    p.add_argument("--out-dir", type=Path, help=f"输出目录，默认 {config.REPORTS_DIR}")
    args = p.parse_args()
    html_out, pdf_out = export(args.page, args.date, args.out_dir)
    size_kb = pdf_out.stat().st_size / 1024
    print(f"已生成：\n  {html_out}\n  {pdf_out}（{size_kb:.0f} KB）")


if __name__ == "__main__":
    sys.exit(main())
