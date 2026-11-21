#!/usr/bin/env python3
"""Read-only file server for the course folder on the Pi (stdlib only).

Only the VPS (nginx + the course app) talks to it, over WireGuard; nftables drops
everyone else. It never writes anything.

  GET /list               -> JSON: top-level folders, and whether each has course.yaml
  GET /tree/<course>      -> JSON: every file below that folder (path, size, mtime)
  GET|HEAD /raw/<path>    -> the file, with single-range support (206) for video seeking
"""
import argparse
import email.utils
import json
import mimetypes
import os
import re
import stat
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HIDDEN = {"$RECYCLE.BIN", "System Volume Information", "Thumbs.db", "desktop.ini"}
CHUNK = 256 * 1024
MAX_DEPTH = 4
mimetypes.add_type("video/mp4", ".m4v")
mimetypes.add_type("text/vtt", ".vtt")


def visible(name):
    return not (name.startswith(".") or name.startswith("$") or name in HIDDEN)


class Handler(BaseHTTPRequestHandler):
    server_version = "learn-media"
    sys_version = ""
    protocol_version = "HTTP/1.1"

    # --- helpers -------------------------------------------------------------
    def resolve(self, rel):
        """Map a URL path below the root to a real path; None if outside or hidden."""
        parts = [p for p in rel.split("/") if p not in ("", ".")]
        if any(p == ".." or not visible(p) for p in parts):
            return None
        root = self.server.root
        full = os.path.realpath(os.path.join(root, *parts))
        if full != root and not full.startswith(root + os.sep):
            return None  # symlink pointing outside the course folder
        return full

    def send_json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def fail(self, code):
        self.send_json({"error": code}, code)

    def log_message(self, fmt, *args):  # journald: one short line per request
        print("%s %s" % (self.address_string(), fmt % args), flush=True)

    # --- routes --------------------------------------------------------------
    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        if self.server.mount and not os.path.ismount(self.server.mount):
            return self.fail(503)  # disk unplugged: say so instead of "empty course"
        path = urllib.parse.unquote(urllib.parse.urlsplit(self.path).path)
        try:
            if path == "/list":
                return self.list_courses()
            m = re.fullmatch(r"/tree/([^/]+)/?", path)
            if m:
                return self.tree(m.group(1))
            if path.startswith("/raw/"):
                return self.raw(path[len("/raw/"):])
            self.fail(404)
        except (BrokenPipeError, ConnectionResetError):
            pass  # viewer seeked or closed the tab
        except OSError as e:
            print("I/O error: %s" % e, flush=True)
            self.close_connection = True
            try:
                self.fail(503)
            except OSError:
                pass

    def list_courses(self):
        out = []
        with os.scandir(self.server.root) as it:
            for e in it:
                if e.is_dir(follow_symlinks=False) and visible(e.name):
                    out.append({"name": e.name,
                                "course": os.path.isfile(os.path.join(e.path, "course.yaml"))})
        self.send_json(sorted(out, key=lambda c: c["name"]))

    def tree(self, course):
        base = self.resolve(course)
        if not base or not os.path.isdir(base):
            return self.fail(404)
        files = []

        def walk(d, rel, depth):
            with os.scandir(d) as it:
                for e in it:
                    if not visible(e.name) or e.is_symlink():
                        continue
                    r = rel + e.name
                    if e.is_dir():
                        if depth < MAX_DEPTH:
                            walk(e.path, r + "/", depth + 1)
                    elif e.is_file():
                        st = e.stat()
                        files.append({"path": r, "size": st.st_size, "mtime": int(st.st_mtime)})

        walk(base, "", 1)
        self.send_json({"course": course, "files": files})

    def raw(self, rel):
        full = self.resolve(rel)
        try:
            st = os.stat(full) if full else None
        except OSError:
            st = None
        if not st or not stat.S_ISREG(st.st_mode):
            return self.fail(404)
        size = st.st_size
        start, end = 0, size - 1
        code = 200
        rng = self.headers.get("Range")
        if rng:
            m = re.fullmatch(r"bytes=(\d*)-(\d*)", rng.strip())
            if not m or (m.group(1) == "" and m.group(2) == ""):
                return self.range_error(size)
            if m.group(1) == "":  # suffix range: last N bytes
                start = max(0, size - int(m.group(2)))
            else:
                start = int(m.group(1))
                if m.group(2):
                    end = min(int(m.group(2)), size - 1)
            if start >= size or start > end:
                return self.range_error(size)
            code = 206
        length = end - start + 1
        self.send_response(code)
        self.send_header("Content-Type", mimetypes.guess_type(full)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(length))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Last-Modified", email.utils.formatdate(st.st_mtime, usegmt=True))
        if code == 206:
            self.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, size))
        self.end_headers()
        if self.command == "HEAD":
            return
        with open(full, "rb") as f:
            f.seek(start)
            left = length
            while left > 0:
                buf = f.read(min(CHUNK, left))
                if not buf:
                    break
                self.wfile.write(buf)
                left -= len(buf)

    def range_error(self, size):
        self.send_response(416)
        self.send_header("Content-Range", "bytes */%d" % size)
        self.send_header("Content-Length", "0")
        self.end_headers()


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", required=True, help="course folder, e.g. /srv/drive/data/Training_Opcode")
    ap.add_argument("--mount", default="", help="answer 503 unless this path is a mount point")
    ap.add_argument("--bind", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8092)
    a = ap.parse_args()
    srv = ThreadingHTTPServer((a.bind, a.port), Handler)
    srv.daemon_threads = True
    srv.root = os.path.realpath(a.root)
    srv.mount = a.mount
    print("serving %s on %s:%d" % (srv.root, a.bind, a.port), flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
