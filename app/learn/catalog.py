"""Courses = folders on the Pi's disk, read through the media server.

    Training_Opcode/
      linux_udemy/              <- a course once it contains course.yaml
        course.yaml             <- title:, description:  (both optional)
        cover.jpg               <- optional card image
        01 Getting started/     <- section (numbers set the order, then are hidden)
          01 Welcome.mp4        <- lesson
          01 Welcome.pdf        <- attachment of lesson 01 (same leading number)
          cheatsheet.pdf        <- section resource (no matching number)
        02 Shell basics/
          ...
Videos lying directly in the course folder form one section, "Lessons".
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

from . import config

VIDEO_EXT = {".mp4", ".m4v", ".webm"}
PLAYABLE_WARN_EXT = {".mkv", ".avi", ".mov", ".wmv", ".flv", ".ts"}
COVER_NAMES = {"cover.jpg", "cover.jpeg", "cover.png", "cover.webp"}
PARTIAL_EXT = {".tmp", ".part", ".crdownload", ".partial"}   # uploads still in progress
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
class Lesson:
    file: File
    title: str
    number: int | None
    section: str
    attachments: list = field(default_factory=list)
    index: int = 0               # position in the whole course (0-based)

    @property
    def id(self):
        return self.file.id


@dataclass
class Section:
    title: str
    lessons: list = field(default_factory=list)
    resources: list = field(default_factory=list)


@dataclass
class Course:
    slug: str
    title: str
    description: str
    sections: list
    cover: File | None
    warnings: list

    @property
    def lessons(self):
        return [l for s in self.sections for l in s.lessons]

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


def build(slug, meta, files):
    """Turn a flat file list (from /tree) into a Course."""
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
        title = split_title(folder)[1] if folder else "Lessons"
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
            num, _ = split_title(o.name)
            (by_num[num].attachments if num in by_num else sec.resources).append(o)
        if sec.lessons or sec.resources:
            sections.append(sec)

    course = Course(slug=slug, title=str(meta.get("title") or slug.replace("_", " ").title()),
                    description=str(meta.get("description") or ""), sections=sections,
                    cover=cover, warnings=warnings)
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
        c = build(slug, meta, tree["files"])
        if bad:
            c.warnings.append("course.yaml is not valid YAML (title: / description:): using the folder name")
        return c

    return _cached("course:" + slug, load, refresh)


def refresh_all():
    with _lock:
        _cache.clear()
