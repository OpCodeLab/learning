"""Account-sharing protection: device limit, one video at a time, sharing signals.

Applies to students only; the admin is never limited.
"""
import re
import time

from . import config, store

PLAY_FRESH = 45        # s: a device "is playing" if it pinged within this window


def device_name(ua):
    """'Mozilla/5.0 (Windows NT 10.0; ...) Chrome/131...' -> 'Chrome on Windows'."""
    ua = ua or ""
    os_name = next((n for p, n in (
        (r"iPhone|iPod", "iPhone"), (r"iPad", "iPad"), (r"Android", "Android"), (r"Windows", "Windows"),
        (r"Mac OS X|Macintosh", "Mac"), (r"CrOS", "ChromeOS"), (r"Linux", "Linux")) if re.search(p, ua)), "unknown OS")
    browser = next((n for p, n in (
        (r"Edg/", "Edge"), (r"OPR/|Opera", "Opera"), (r"Firefox/|FxiOS", "Firefox"), (r"SamsungBrowser", "Samsung"),
        (r"Chrome/|CriOS", "Chrome"), (r"Safari/", "Safari")) if re.search(p, ua)), "browser")
    return "%s on %s" % (browser, os_name)


def log(c, uid, kind, ip, device):
    c.execute("INSERT INTO events (user_id, at, kind, ip, device) VALUES (?,?,?,?,?)",
              (uid, store.now(), kind, ip, device))


# --- 1. device limit ---------------------------------------------------------------
def enforce_device_limit(c, uid, keep_hash):
    """Keep at most MAX_DEVICES signed-in sessions; sign out the oldest ones."""
    rows = c.execute("SELECT token_hash, ip, device FROM sessions WHERE user_id = ? AND stage = 'ok' "
                     "ORDER BY (token_hash = ?) DESC, last_seen DESC, created_at DESC, rowid DESC",
                     (uid, keep_hash)).fetchall()
    for r in rows[config.MAX_DEVICES:]:
        c.execute("DELETE FROM sessions WHERE token_hash = ?", (r["token_hash"],))
        log(c, uid, "evicted", r["ip"], r["device"])


def devices(c, uid):
    return c.execute("SELECT * FROM sessions WHERE user_id = ? AND stage = 'ok' AND expires_at > ? "
                     "ORDER BY last_seen DESC", (uid, store.now())).fetchall()


# --- 2. one video at a time ----------------------------------------------------------
def playing_elsewhere(c, uid, session_hash):
    """The other device currently playing for this account, or None."""
    p = c.execute("SELECT * FROM playback WHERE user_id = ?", (uid,)).fetchone()
    if p and p["session"] != session_hash and p["updated_at"] > time.time() - PLAY_FRESH:
        # the lock only counts while that session still exists (not signed out / evicted)
        alive = c.execute("SELECT 1 FROM sessions WHERE token_hash = ?", (p["session"],)).fetchone()
        if alive:
            return p
    return None


def take_playback(c, uid, session_hash, device):
    c.execute("INSERT INTO playback (user_id, session, device, updated_at) VALUES (?,?,?,?) "
              "ON CONFLICT (user_id) DO UPDATE SET session = excluded.session, device = excluded.device, "
              "updated_at = excluded.updated_at", (uid, session_hash, device, store.now()))


def release_playback(c, uid, session_hash):
    c.execute("DELETE FROM playback WHERE user_id = ? AND session = ?", (uid, session_hash))


# --- 3. sharing signals --------------------------------------------------------------
def ip_prefix(ip):
    """Group addresses of the same network (mobile and home IPs change inside it)."""
    if ":" in ip:
        return ":".join(ip.split(":")[:3]) + "::/48"
    parts = ip.split(".")
    return ".".join(parts[:3]) + ".0/24" if len(parts) == 4 else ip


def signals(c, uid):
    """Counts over the last 30 days and a list of human-readable warnings."""
    since = store.now() - 30 * 86400
    week = store.now() - 7 * 86400
    ev = c.execute("SELECT * FROM events WHERE user_id = ? AND at > ? ORDER BY at DESC", (uid, since)).fetchall()
    logins = [e for e in ev if e["kind"] == "login"]
    nets = {ip_prefix(e["ip"]) for e in logins if e["ip"]}
    devs = {e["device"] for e in logins if e["device"]}
    nets_week = {ip_prefix(e["ip"]) for e in logins if e["ip"] and e["at"] > week}
    evicted = sum(1 for e in ev if e["kind"] == "evicted" and e["at"] > week)
    takeovers = sum(1 for e in ev if e["kind"] in ("takeover", "blocked") and e["at"] > week)
    warn = []
    if len(nets_week) >= 5:
        warn.append("%d different networks this week" % len(nets_week))
    if len(devs) >= 5:
        warn.append("%d different devices in 30 days" % len(devs))
    if evicted >= 4:
        warn.append("%d devices signed out by the 2-device limit this week" % evicted)
    if takeovers >= 6:
        warn.append("%d play conflicts this week (two devices at once)" % takeovers)
    return dict(logins=len(logins), networks=len(nets), devices=len(devs), evicted=evicted,
                takeovers=takeovers, warnings=warn, events=ev[:40])
