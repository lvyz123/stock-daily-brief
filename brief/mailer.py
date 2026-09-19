"""通过 QQ 邮箱 SMTP（SSL 465）发送。SMTP_PASS 是 QQ 邮箱的授权码，不是登录密码。"""
from __future__ import annotations

import logging
import smtplib
import time
from email.message import EmailMessage
from email.utils import formataddr

from . import config

log = logging.getLogger(__name__)


def send(subject: str, html_body: str, text_body: str, to: str | None = None) -> None:
    to = to or config.MAIL_TO
    if not (config.SMTP_USER and config.SMTP_PASS and to):
        raise RuntimeError("缺少 SMTP_USER / SMTP_PASS / MAIL_TO 环境变量")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((config.SENDER_NAME, config.SMTP_USER))
    msg["To"] = to
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")

    for attempt in range(3):
        try:
            with smtplib.SMTP_SSL(config.SMTP_HOST, config.SMTP_PORT, timeout=60) as s:
                s.login(config.SMTP_USER, config.SMTP_PASS)
                s.send_message(msg)
            log.info("邮件已发送至 %s", to)
            return
        except smtplib.SMTPAuthenticationError:
            raise  # 授权码错误，重试无意义
        except (smtplib.SMTPException, OSError) as e:
            log.warning("发送失败（第 %d 次）：%s", attempt + 1, e)
            if attempt == 2:
                raise
            time.sleep(10 * (attempt + 1))
