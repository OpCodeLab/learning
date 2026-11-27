"""Settings, from the environment (/etc/opcode-learn/learn.env on the VPS)."""
import os

DB_PATH = os.environ.get("LEARN_DB", "/var/lib/opcode-learn/learn.sqlite")
# Read-only file lister on the same server (pi/media_server.py, run by opcode-learn-files.service)
# over the course folder /srv/learn/courses: lists the courses, serves course.yaml and link files.
MEDIA_URL = os.environ.get("LEARN_MEDIA_URL", "http://127.0.0.1:8096").rstrip("/")
BASE_URL = os.environ.get("LEARN_BASE_URL", "https://learn.opcode-labs.com").rstrip("/")
SITE_NAME = os.environ.get("LEARN_SITE_NAME", "OpCode Learn")
# Production: nginx sends the file from the VPS disk (X-Accel-Redirect to /_media/raw/).
# Dev/tests: the app proxies the bytes itself.
DEV_PROXY = os.environ.get("LEARN_DEV_PROXY") == "1"
COOKIE_SECURE = os.environ.get("LEARN_COOKIE_SECURE", "1") == "1"

STUDENT_SESSION_DAYS = 14
ADMIN_SESSION_HOURS = 8
INVITE_DAYS = 14
MIN_PASSWORD = 10
CATALOG_TTL = 60          # seconds between re-reads of the course folders
MAX_DEVICES = int(os.environ.get("LEARN_MAX_DEVICES", "2"))   # signed-in devices per student

# Questions under the videos: students ask, the trainer answers by email (mailer.py).
# Outgoing mail through an SMTP mailbox (e.g. contact@opcode-labs.com). Empty host = no email:
# questions and answers are still stored and shown on the site.
SMTP_HOST = os.environ.get("LEARN_SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("LEARN_SMTP_PORT", "465"))      # 465 = TLS from the start, 587 = STARTTLS
SMTP_USER = os.environ.get("LEARN_SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("LEARN_SMTP_PASSWORD", "")
MAIL_FROM = os.environ.get("LEARN_MAIL_FROM", "") or SMTP_USER
TRAINER_EMAIL = os.environ.get("LEARN_TRAINER_EMAIL", "")   # empty = the admin accounts' emails
QUESTION_MAX = 4000        # characters
QUESTIONS_PER_HOUR = 10    # per student
