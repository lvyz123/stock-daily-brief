"""运行配置。敏感信息只从环境变量读取（GitHub Secrets 注入）。"""
import os
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Shanghai")
ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = ROOT / "reports"
PICKS_DIR = REPORTS_DIR / "picks"
OUT_DIR = ROOT / "out"

# 发送时间（北京时间）
SEND_HOUR, SEND_MINUTE = 18, 30

# Claude
MODEL = os.getenv("BRIEF_MODEL", "claude-opus-5")
EFFORT = os.getenv("BRIEF_EFFORT", "high")
WEB_SEARCH_MAX_USES = int(os.getenv("BRIEF_WEB_SEARCH_MAX_USES", "12"))
MAX_PAUSE_CONTINUATIONS = 5

# 邮件
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.qq.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
MAIL_TO = os.getenv("MAIL_TO", "") or SMTP_USER
SENDER_NAME = "每日股市简报"

# 推荐跟踪：邮件底部展示最近几期推荐的表现
TRACK_RECORD_ISSUES = int(os.getenv("BRIEF_TRACK_RECORD_ISSUES", "3"))
SHOW_TRACK_RECORD = os.getenv("BRIEF_SHOW_TRACK_RECORD", "1") == "1"

# 颜色：中国习惯红涨绿跌
UP_COLOR = "#d9363e"
DOWN_COLOR = "#16a34a"
