"""Outgoing email (SMTP over TLS): new questions to the trainer, answers to the students.

Sent in a background thread so pages never wait for the mail server; the result is written
back to the question ('sent', 'off' when no SMTP is configured, or 'error: ...').
"""
import smtplib
import ssl
import threading
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

from . import config

ASYNC = True     # tests set False (and replace deliver)


def enabled():
    return bool(config.SMTP_HOST and config.MAIL_FROM)


def one_line(s, n=120):
    """Header-safe: no line breaks, limited length."""
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[:n - 1] + "…"


def deliver(msg):
    ctx = ssl.create_default_context()
    if config.SMTP_PORT == 465:
        smtp = smtplib.SMTP_SSL(config.SMTP_HOST, config.SMTP_PORT, context=ctx, timeout=30)
    else:
        smtp = smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=30)
        smtp.starttls(context=ctx)
    with smtp:
        if config.SMTP_USER:
            smtp.login(config.SMTP_USER, config.SMTP_PASSWORD)
        smtp.send_message(msg)


def send(to, subject, body, done=None):
    """Send a plain-text mail; done(status) is called afterwards with 'sent', 'off' or 'error: ...'."""
    def run():
        if not enabled():
            status = "off"
        else:
            try:
                msg = EmailMessage()
                msg["From"] = formataddr((config.SITE_NAME, config.MAIL_FROM))
                msg["To"] = ", ".join(to) if isinstance(to, (list, tuple)) else to
                msg["Subject"] = one_line(subject, 150)
                msg["Message-ID"] = make_msgid(domain=config.MAIL_FROM.rpartition("@")[2] or None)
                msg.set_content(body)
                deliver(msg)
                status = "sent"
            except Exception as e:   # network, login, refused address...: shown on the admin page
                status = "error: " + one_line("%s: %s" % (type(e).__name__, e), 200)
        if done:
            done(status)
        return status
    if ASYNC:
        threading.Thread(target=run, daemon=True).start()
        return None
    return run()
