"""Video lengths, read from the MP4 header over HTTP Range requests to the Pi.

An MP4 file is a list of boxes ("atoms"). The movie header box (moov > mvhd) holds the
timescale and duration. We read the box headers one by one (a few bytes each), jump over the
big media box (mdat), and read only the start of moov. So a 100 MB video costs ~3 small requests.

Results are kept in SQLite (table durations) by path, size and mtime: they are read once per
file, and again only if the file changes. Missing ones are read in a background thread, so
pages never wait for the Pi. A file whose header can't be read is stored with seconds = NULL
(and reported on the admin Courses page): usually an upload that was cut short.
"""
import struct
import threading
import urllib.parse
import urllib.request

from . import config, store

_lock = threading.Lock()
_running = set()   # course slugs being filled right now


def _reader(slug, path):
    url = "%s/raw/%s/%s" % (config.MEDIA_URL, urllib.parse.quote(slug), urllib.parse.quote(path))

    def read(offset, length):
        req = urllib.request.Request(url, headers={"Range": "bytes=%d-%d" % (offset, offset + length - 1)})
        with urllib.request.urlopen(req, timeout=10) as r:
            if r.status != 206 and offset:     # server ignored Range: don't download the whole file
                return b""
            return r.read(length)
    return read


def mp4_duration(read, file_size):
    """Seconds, or None if the file has no readable movie header."""
    off = 0
    for _ in range(64):
        if off + 8 > file_size:
            return None
        h = read(off, 16)
        if len(h) < 8:
            return None
        size, kind = struct.unpack(">I4s", h[:8])
        hdr = 8
        if size == 1:
            if len(h) < 16:
                return None
            size, hdr = struct.unpack(">Q", h[8:16])[0], 16
        elif size == 0:          # box runs to the end of the file: no moov after it
            size = file_size - off
        if kind == b"moov":
            return _mvhd(read(off + hdr, min(size - hdr, 65536)))
        if size < hdr:
            return None
        off += size
    return None


def _mvhd(data):
    i = 0
    while i + 8 <= len(data):
        size, kind = struct.unpack(">I4s", data[i:i + 8])
        if kind == b"mvhd":
            b = data[i + 8:]
            if b[:1] == b"\x01" and len(b) >= 32:
                ts, dur = struct.unpack(">IQ", b[20:32])
            elif len(b) >= 20:
                ts, dur = struct.unpack(">II", b[12:20])
            else:
                return None
            return round(dur / ts, 1) if ts else None
        if size < 8:
            return None
        i += size
    return None


def known(slug):
    """{path: (size, mtime, seconds or None)} for one course."""
    with store.db() as c:
        rows = c.execute("SELECT path, size, mtime, seconds FROM durations WHERE course = ?", (slug,)).fetchall()
    return {r["path"]: (r["size"], r["mtime"], r["seconds"]) for r in rows}


def apply(course, on_update=None):
    """Set lesson.duration from the database; read missing ones in the background.
    on_update() is called once the background pass stored new lengths."""
    have = known(course.slug)
    missing = []
    for les in course.lessons:
        f = les.file
        k = have.get(f.path)
        if k and k[0] == f.size and k[1] == f.mtime:
            les.duration = k[2]
            les.unreadable = k[2] is None
        else:
            missing.append(f)
    if missing:
        with _lock:
            if course.slug in _running:
                return
            _running.add(course.slug)
        threading.Thread(target=_fill, args=(course.slug, missing, on_update), daemon=True).start()


def _fill(slug, files, on_update):
    try:
        for f in files:
            try:
                sec = mp4_duration(_reader(slug, f.path), f.size)
            except Exception:
                continue      # Pi offline or slow: try again on a later page view
            with store.db() as c:
                c.execute("INSERT INTO durations (course, path, size, mtime, seconds) VALUES (?,?,?,?,?) "
                          "ON CONFLICT (course, path) DO UPDATE SET size = excluded.size, "
                          "mtime = excluded.mtime, seconds = excluded.seconds",
                          (slug, f.path, f.size, f.mtime, sec))
    finally:
        with _lock:
            _running.discard(slug)
        if on_update:
            on_update()


def fmt(seconds):
    """Lesson length like Udemy: '9 min' (at least 1 min)."""
    if not seconds:
        return ""
    return "%d min" % max(1, round(seconds / 60))


def fmt_total(seconds):
    """'21 h 12 min', '45 min'."""
    if not seconds:
        return ""
    m = max(1, int(round(seconds / 60)))
    h, m = divmod(m, 60)
    return ("%d h %d min" % (h, m)) if h else "%d min" % m
