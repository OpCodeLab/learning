"""Courses = folders on the Pi's disk, read through the media server.

    Training_Opcode/
      linux_udemy/              <- a course once it contains course.yaml
        course.yaml             <- title:, description:  (both optional)
        cover.jpg               <- optional card image
        01 Getting started/     <- section (numbers set the order, then are hidden)
          01 Welcome.mp4        <- lesson
          01 Welcome.pdf        <- attachment of lesson 01 (same leading number)
          cheatsheet.pdf        <- section resource (no matching number)
          01 Code on GitHub.url <- link (a Windows internet shortcut), same rules as files
        02 Shell basics/
          ...
Videos lying directly in the course folder form one section, "Lessons".
Links for the whole course go in course.yaml:  links: [{title: ..., url: https://...}]
"""
import hashlib
import json
import re
import threading
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

import yaml

from . import config, durations

VIDEO_EXT = {".mp4", ".m4v", ".webm"}
PLAYABLE_WARN_EXT = {".mkv", ".avi", ".mov", ".wmv", ".flv", ".ts"}
COVER_NAMES = {"cover.jpg", "cover.jpeg", "cover.png", "cover.webp"}
PARTIAL_EXT = {".tmp", ".part", ".crdownload", ".partial"}   # uploads still in progress
LINK_EXT = {".url"}         # Windows internet shortcut: "[InternetShortcut]" then "URL=https://..."
# "03 - Title", "03_Title", and "S1_L03_Title" (section 1, lesson 3): the lesson number is 3.
_NUM = re.compile(r"^\s*(?:S\d+[\s._-]*L)?(\d+)[\s._\-)]*", re.I)


class Unavailable(Exception):
    """The Pi (or its disk) can't be reached right now."""


@dataclass
class File:
    path: str
    size: int
    mtime: int

    @property
    def id(self):
        return hashlib.sha1(self.path.encode()).hexdigest()[:12]

    @property
    def name(self):
        return self.path.rsplit("/", 1)[-1]

    @property
    def ext(self):
        n = self.name
        return n[n.rfind("."):].lower() if "." in n else ""


@dataclass
class Link:
    title: str
    url: str


def safe_url(url):
    """Only plain web links (no javascript:, file:, ...)."""
    url = str(url or "").strip()
    p = urllib.parse.urlsplit(url)
    return url if p.scheme in ("http", "https") and p.netloc and len(url) <= 2000 else None


def parse_url_file(data):
    """URL= line of a .url file (bytes), or None."""
    for line in data.decode("utf-8", "replace").splitlines():
        if line.strip().lower().startswith("url="):
            return safe_url(line.strip()[4:])
    return None


def course_links(meta, warnings):
    """course.yaml links: a list of {title, url}, or a mapping title: url."""
    raw = meta.get("links") or []
    items = raw.items() if isinstance(raw, dict) else [
        ((x.get("title"), x.get("url")) if isinstance(x, dict) else (None, None)) for x in (raw if isinstance(raw, list) else [])]
    out = []
    for title, url in items:
        u = safe_url(url)
        if u:
            out.append(Link(str(title or u), u))
        else:
            warnings.append("course.yaml links: %r is not an http(s) link" % (url,))
    return out


@dataclass
class Lesson:
    file: File
    title: str
    number: int | None
    section: str
    attachments: list = field(default_factory=list)
    links: list = field(default_factory=list)
    index: int = 0               # position in the whole course (0-based)
    duration: float | None = None    # seconds, from the MP4 header (durations.py)
    unreadable: bool = False         # the MP4 header couldn't be read (broken upload?)

    @property
    def num(self):
        """Number shown to students: from the file name (S4_L21 -> 21), else the position."""
        return self.number if self.number is not None else self.index + 1

    @property
    def id(self):
        return self.file.id


@dataclass
class Section:
    title: str
    lessons: list = field(default_factory=list)
    resources: list = field(default_factory=list)
    links: list = field(default_factory=list)


@dataclass
class Course:
    slug: str
    title: str
    description: str
    sections: list
    cover: File | None
    warnings: list
    links: list = field(default_factory=list)

    @property
    def lessons(self):
        return [l for s in self.sections for l in s.lessons]

    @property
    def total_duration(self):
        return sum(l.duration or 0 for l in self.lessons)

    def lesson(self, lid):
        return next((l for l in self.lessons if l.id == lid), None)

    def file(self, fid):
        """Any downloadable file of the course (attachment, resource, cover)."""
        for s in self.sections:
            for f in s.resources:
                if f.id == fid:
                    return f
            for l in s.lessons:
                for f in l.attachments:
                    if f.id == fid:
                        return f
        if self.cover and self.cover.id == fid:
            return self.cover
        return None


def natural_key(s):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


def tidy(text):
    """'Why-multithreading-Amdahl-s-law' -> 'Why multithreading Amdahl's law' (names without spaces only)."""
    if " " in text or not re.search(r"[-_]", text):
        return text
    text = re.sub(r"(?<=[A-Za-z])-s(?=-|$)", "'s", text)
    return re.sub(r"[-_]+", " ", text).strip()


def split_title(name):
    """'03 - File permissions.mp4' -> (3, 'File permissions'); 'S1_L03_fork-and-wait.mp4' -> (3, 'fork and wait')"""
    stem = name.rsplit(".", 1)[0] if "." in name else name
    m = _NUM.match(stem)
    if not m:
        return None, tidy(stem.strip())
    rest = stem[m.end():].strip()
    return int(m.group(1)), tidy(rest) if rest else stem.strip()


def build(slug, meta, files, urls=None):
    """Turn a flat file list (from /tree) into a Course. urls: {path of a .url file: its link}."""
    urls = urls or {}
    files = [File(f["path"], f["size"], f["mtime"]) for f in files]
    warnings = []
    titles = meta.get("titles") if isinstance(meta.get("titles"), dict) else {}
    cover = next((f for f in files if "/" not in f.path and f.name.lower() in COVER_NAMES), None)
    folders = {}
    for f in files:
        if f.path == "course.yaml" or f is cover or f.ext in PARTIAL_EXT:
            continue
        if f.ext in PLAYABLE_WARN_EXT:
            warnings.append("%s: browsers can't play %s; convert it to .mp4 (see docs/content.md)" % (f.path, f.ext))
            continue  # not shown to students
        folder = f.path.rsplit("/", 1)[0] if "/" in f.path else ""
        if folder.count("/") > 0:
            # deeper than course/section/file: attach to its section, as a resource
            folder = folder.split("/", 1)[0]
        folders.setdefault(folder, []).append(f)

    sections = []
    for folder in sorted(folders, key=natural_key):
        items = sorted(folders[folder], key=lambda f: natural_key(f.name))
        if folder:
            title = split_title(folder)[1]
        else:  # files lying in the course folder itself
            title = "Lessons" if any(f.ext in VIDEO_EXT for f in items) else "Course files"
        sec = Section(title=title)
        videos = [f for f in items if f.ext in VIDEO_EXT]
        others = [f for f in items if f.ext not in VIDEO_EXT]
        by_num = {}
        for v in videos:
            num, t = split_title(v.name)
            # course.yaml "titles:" overrides, keyed by file name (with or without extension)
            t = str(titles.get(v.name) or titles.get(v.name.rsplit(".", 1)[0]) or t)
            les = Lesson(file=v, title=t, number=num, section=title)
            sec.lessons.append(les)
            if num is not None:
                by_num.setdefault(num, les)
        for o in others:
            num, t = split_title(o.name)
            if o.ext in LINK_EXT:
                if not urls.get(o.path):
                    warnings.append("%s: no http(s) URL= line in this link file" % o.path)
                    continue
                (by_num[num].links if num in by_num else sec.links).append(Link(t, urls[o.path]))
                continue
            (by_num[num].attachments if num in by_num else sec.resources).append(o)
        if sec.lessons or sec.resources or sec.links:
            sections.append(sec)

    course = Course(slug=slug, title=str(meta.get("title") or slug.replace("_", " ").title()),
                    description=str(meta.get("description") or ""), sections=sections,
                    cover=cover, warnings=warnings, links=course_links(meta, warnings))
    for i, les in enumerate(course.lessons):
        les.index = i
    if not course.lessons:
        warnings.append("no videos yet (.mp4 / .m4v / .webm)")
    return course


# --- fetching from the Pi, with a small cache ------------------------------------
_lock = threading.Lock()
_cache = {}


def _get(path, raw=False):
    url = config.MEDIA_URL + path
    try:
        with urllib.request.urlopen(url, timeout=8) as r:
            data = r.read()
    except Exception as e:
        raise Unavailable(str(e)) from e
    return data if raw else json.loads(data)


def _cached(key, loader, refresh=False):
    with _lock:
        hit = _cache.get(key)
        if hit and not refresh and time.time() - hit[0] < config.CATALOG_TTL:
            return hit[1]
    value = loader()
    with _lock:
        _cache[key] = (time.time(), value)
    return value


def folders(refresh=False):
    """[{'name': ..., 'course': bool}] for every top-level folder."""
    return _cached("list", lambda: _get("/list"), refresh)


def course_names(refresh=False):
    return [f["name"] for f in folders(refresh) if f["course"]]


def course(slug, refresh=False):
    if slug not in course_names(refresh):
        return None

    def load():
        q = urllib.parse.quote(slug)
        tree = _get("/tree/" + q)
        bad = False
        try:
            meta = yaml.safe_load(_get("/raw/%s/course.yaml" % q, raw=True)) or {}
        except yaml.YAMLError:
            meta = None
        if not isinstance(meta, dict):
            meta, bad = {}, True
        urls = {}
        for f in tree["files"]:   # link files are tiny: read them (skip anything big)
            if f["path"].lower().endswith(tuple(LINK_EXT)) and f["size"] <= 4096:
                urls[f["path"]] = parse_url_file(_get("/raw/%s/%s" % (q, urllib.parse.quote(f["path"])), raw=True))
        c = build(slug, meta, tree["files"], urls)
        if bad:
            c.warnings.append("course.yaml is not valid YAML (title: / description:): using the folder name")
        try:
            durations.apply(c, on_update=lambda: _forget("course:" + slug))
        except Exception:   # lengths are a nice-to-have: never block the course
            pass
        for les in c.lessons:
            if les.unreadable:
                c.warnings.append("%s: the video header can't be read (upload cut short? re-upload it, "
                                  "or run tools/check-videos.sh)" % les.file.path)
        return c

    return _cached("course:" + slug, load, refresh)


def _forget(key):
    with _lock:
        _cache.pop(key, None)


def refresh_all():
    with _lock:
        _cache.clear()
