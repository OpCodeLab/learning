"""Settings, from the environment (/etc/opcode-learn/learn.env on the VPS)."""
import os

DB_PATH = os.environ.get("LEARN_DB", "/var/lib/opcode-learn/learn.sqlite")
# The Pi's read-only media server, through WireGuard.
MEDIA_URL = os.environ.get("LEARN_MEDIA_URL", "http://10.8.3.3:8092").rstrip("/")
BASE_URL = os.environ.get("LEARN_BASE_URL", "https://learn.opcode-labs.com").rstrip("/")
SITE_NAME = os.environ.get("LEARN_SITE_NAME", "OpCode Learn")
# Production: nginx streams the file (X-Accel-Redirect + cache on the VPS).
# Dev/tests: the app proxies the bytes itself.
DEV_PROXY = os.environ.get("LEARN_DEV_PROXY") == "1"
COOKIE_SECURE = os.environ.get("LEARN_COOKIE_SECURE", "1") == "1"

STUDENT_SESSION_DAYS = 14
ADMIN_SESSION_HOURS = 8
INVITE_DAYS = 14
MIN_PASSWORD = 10
CATALOG_TTL = 60          # seconds between re-reads of the course folders
