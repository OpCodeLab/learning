"""End-to-end test: real media server (pi/media_server.py) + the app in dev-proxy mode.

    python3 -m venv /tmp/learnvenv && /tmp/learnvenv/bin/pip install -r app/requirements.txt httpx
    /tmp/learnvenv/bin/python tests/test_e2e.py
"""
import os
import re
import struct
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
work = tempfile.mkdtemp(prefix="learn-test-")
media = os.path.join(work, "Training_Opcode")
PORT = 18092


def make(path, data=b""):
    full = os.path.join(media, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "wb") as f:
        f.write(data)


VIDEO = bytes(range(256)) * 4096          # 1 MiB of known bytes
make("linux_udemy/course.yaml", ("title: Linux from scratch\ndescription: Shell, files, processes.\n"
                                  "links:\n  - title: Course code\n    url: https://github.com/OpCodeLab/linux-course\n"
                                  "  - title: Bad\n    url: javascript:alert(1)\n").encode())
make("linux_udemy/01 Getting started/01 Code on GitHub.url", b"[InternetShortcut]\r\nURL=https://github.com/OpCodeLab/lesson1\r\n")
make("linux_udemy/01 Getting started/Man pages.url", b"[InternetShortcut]\nURL=https://man7.org/linux/man-pages/\n")
make("linux_udemy/01 Getting started/02 Evil.url", b"[InternetShortcut]\nURL=javascript:alert(1)\n")
make("linux_udemy/01 Getting started/01 Welcome.mp4", VIDEO)
make("linux_udemy/01 Getting started/01 Welcome.pdf", b"%PDF-1.4 welcome")
make("linux_udemy/01 Getting started/02 - Install Ubuntu.mp4", VIDEO[:1000])
make("linux_udemy/01 Getting started/cheatsheet.txt", b"ls cd pwd")
# A real MP4 box layout: ftyp, a big mdat, then moov/mvhd at the end (125.0 s), as phones write it.
MP4 = (struct.pack(">I4s", 16, b"ftyp") + b"isom\x00\x00\x00\x00" + struct.pack(">I4s", 8 + 2000, b"mdat") + VIDEO[:2000]
       + struct.pack(">I4s", 8 + 8 + 100, b"moov") + struct.pack(">I4s", 8 + 100, b"mvhd")
       + struct.pack(">B3xIIII", 0, 0, 0, 1000, 125000) + bytes(80))
make("linux_udemy/02 Shell/10 Pipes.mp4", MP4)
make("linux_udemy/02 Shell/9 Redirection.mkv", b"x")
make("linux_udemy/02 Shell/upload-chunk-123.tmp", b"x")
make("linux_udemy/$RECYCLE.BIN/secret.mp4", b"x")
make("rtos_record/course.yaml", b"title: RTOS\n")
make("rtos_record/01 Intro.mp4", VIDEO[:500])
make("not_a_course/readme.txt", b"hi")
make("Linux_Embedded.pptx", b"pptx")

srv = subprocess.Popen([sys.executable, os.path.join(ROOT, "pi", "media_server.py"), "--root", media,
                        "--bind", "127.0.0.1", "--port", str(PORT)], stdout=subprocess.DEVNULL)
for _ in range(50):
    try:
        urllib.request.urlopen("http://127.0.0.1:%d/list" % PORT, timeout=1)
        break
    except OSError:
        time.sleep(0.1)

os.environ.update(LEARN_DB=os.path.join(work, "learn.sqlite"), LEARN_MEDIA_URL="http://127.0.0.1:%d" % PORT,
                  LEARN_BASE_URL="http://testserver", LEARN_DEV_PROXY="1", LEARN_COOKIE_SECURE="0",
                  LEARN_SMTP_HOST="smtp.invalid", LEARN_SMTP_USER="learn@opcode.test",
                  LEARN_TRAINER_EMAIL="trainer@opcode.test")
sys.path.insert(0, os.path.join(ROOT, "app"))
from starlette.testclient import TestClient  # noqa: E402
from learn import mailer, security, store, web  # noqa: E402

sent = []   # emails, captured instead of sent
mailer.ASYNC = False
mailer.deliver = lambda msg: sent.append(msg)

ok = True
from learn.catalog import split_title  # noqa: E402


def check(name, cond, extra=""):
    global ok
    ok &= bool(cond)
    print(("PASS " if cond else "FAIL ") + name + (("  [%s]" % extra) if extra and not cond else ""))


H = {"Origin": "http://testserver"}


def csrf_of(html):
    m = re.search(r'name="csrf" value="([^"]+)"', html) or re.search(r'data-csrf="([^"]+)"', html)
    return m.group(1) if m else ""


try:
    # --- title parsing ------------------------------------------------------------
    check("title: 'S3_L11_Why-multithreading-Amdahl-s-law.mp4'",
          split_title("S3_L11_Why-multithreading-Amdahl-s-law.mp4") == (11, "Why multithreading Amdahl's law"))
    check("title: '02 - Install Ubuntu.mp4'", split_title("02 - Install Ubuntu.mp4") == (2, "Install Ubuntu"))
    check("title: section folder kept", split_title("Section 1 - Linux basics") == (None, "Section 1 - Linux basics"))

    # --- media server on its own ------------------------------------------------
    import json
    raw = lambda p, **h: urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:%d%s" % (PORT, p), headers=h))
    lst = json.loads(raw("/list").read())
    check("media: lists folders, marks courses", {(f["name"], f["course"]) for f in lst} ==
          {("linux_udemy", True), ("rtos_record", True), ("not_a_course", False)}, lst)
    tree = json.loads(raw("/tree/linux_udemy").read())["files"]
    check("media: tree hides $RECYCLE.BIN", not any("RECYCLE" in f["path"] for f in tree))
    r = raw("/raw/linux_udemy/01%20Getting%20started/01%20Welcome.mp4", Range="bytes=100-199")
    check("media: range request -> 206 + exact bytes", r.status == 206 and r.read() == VIDEO[100:200]
          and r.headers["Content-Range"] == "bytes 100-199/%d" % len(VIDEO))
    for bad in ("/raw/../../etc/passwd", "/raw/linux_udemy/%2e%2e/%2e%2e/x", "/raw/linux_udemy/$RECYCLE.BIN/secret.mp4"):
        try:
            raw(bad)
            check("media: blocks " + bad, False)
        except urllib.error.HTTPError as e:
            check("media: blocks " + bad, e.code == 404)

    # --- app ------------------------------------------------------------------
    store.init()
    with store.db() as c:
        totp = security.new_totp_secret()
        store.create_user(c, "admin@example.com", is_admin=True, pw_hash=security.hash_password("admin-password-123"),
                          totp_secret=totp)
    app = TestClient(web.app, base_url="http://testserver", follow_redirects=False)

    check("anonymous -> login", app.get("/").headers.get("location", "").startswith("/login"))
    check("anonymous media -> 401", app.get("/media/linux_udemy/x").status_code == 401)
    check("POST without Origin refused", app.post("/login", data={"email": "a", "password": "b"}).status_code == 403)
    r = app.post("/login", data={"email": "admin@example.com", "password": "wrong"}, headers=H)
    check("wrong password -> 401", r.status_code == 401)
    r = app.post("/login", data={"email": "admin@example.com", "password": "admin-password-123"}, headers=H)
    check("admin password ok -> asks code", r.status_code == 303 and r.headers["location"].startswith("/login/code"))
    check("half-logged admin can't open /admin", app.get("/admin").status_code == 303)
    r = app.post("/login/code", data={"code": "000000"}, headers=H)
    check("wrong code -> 401", r.status_code == 401)
    code = security.totp_at(totp, int(time.time()) // 30)
    r = app.post("/login/code", data={"code": code}, headers=H)
    check("right code -> admin", r.status_code == 303 and r.headers["location"] == "/admin")
    r = app.get("/admin")
    check("admin page", r.status_code == 200 and "No students yet" in r.text)
    check("CSP header set", "script-src 'self'" in r.headers.get("content-security-policy", ""))
    csrf = csrf_of(r.text)

    r = app.get("/admin/courses")
    check("courses page lists both courses + warning", "Linux from scratch" in r.text and "RTOS" in r.text
          and ".mkv" in r.text and "not_a_course" in r.text, r.text[:200])

    # create a student for linux only
    r = app.post("/admin/new", data={"csrf": csrf, "email": "Alice@Example.com", "name": "Alice",
                                     "course": ["linux_udemy", "bogus"], "expires": "2099-01-01"}, headers=H)
    m = re.search(r'value="(http://testserver/invite/[^"]+)"', r.text)
    check("student created, invite link shown", r.status_code == 200 and m, r.text[:300])
    invite = m.group(1).replace("http://testserver", "")
    r = app.post("/admin/new", data={"csrf": "nope", "email": "x@y.z"}, headers=H)
    check("admin form without csrf refused", r.status_code == 403)

    # student side
    st = TestClient(web.app, base_url="http://testserver", follow_redirects=False)
    r = st.post(invite, data={"password": "short", "password2": "short"}, headers=H)
    check("invite: short password refused", r.status_code == 400)
    r = st.post(invite, data={"password": "alice-pass-123", "password2": "alice-pass-123"}, headers=H)
    check("invite: password set, logged in", r.status_code == 303 and st.cookies.get("learn_s"))
    check("invite link single use", st.get(invite).status_code == 404)
    r = st.get("/")
    check("student home shows linux only", "Linux from scratch" in r.text and "RTOS" not in r.text)
    r = st.get("/course/linux_udemy")
    check("course link goes straight to the first video", r.status_code == 303
          and re.fullmatch(r"/course/linux_udemy/[0-9a-f]{12}", r.headers["location"]), r.headers.get("location"))
    r = st.get(r.headers["location"])
    check("course content: sections, titles without numbers", "Getting started" in r.text and "Install Ubuntu" in r.text
          and "Pipes" in r.text and "cheatsheet.txt" in r.text)
    check("unplayable .mkv hidden from students", "Redirection" not in r.text)
    check("unfinished uploads (.tmp) hidden", "upload-chunk" not in r.text)
    check("lesson link from a .url file",
          'href="https://github.com/OpCodeLab/lesson1" target="_blank" rel="noopener noreferrer">Code on GitHub' in r.text)
    check("section link (no number) and course link from course.yaml",
          ">Man pages <" in r.text and 'href="https://github.com/OpCodeLab/linux-course"' in r.text)
    check("non-web links refused", "javascript:" not in r.text and ".url" not in r.text)
    check("lessons numbered like Udemy", "1. Welcome" in r.text and "10. Pipes" in r.text)
    lids = list(dict.fromkeys(re.findall(r'<a href="/course/linux_udemy/([0-9a-f]{12})"', r.text)))
    first = lids[0]
    r = st.get("/course/linux_udemy/" + first)
    check("lesson page has player + attachment", "<video" in r.text and "01 Welcome.pdf" in r.text)
    scsrf = csrf_of(r.text)
    r = st.get("/media/linux_udemy/" + first, headers={"Range": "bytes=0-9"})
    check("video range through app", r.status_code == 206 and r.content == VIDEO[:10], r.status_code)
    att = re.search(r'href="/media/linux_udemy/([0-9a-f]{12})">01 Welcome.pdf', st.get("/course/linux_udemy/" + first).text)
    r = st.get("/media/linux_udemy/" + att.group(1))
    check("attachment download", r.content.startswith(b"%PDF") and "attachment" in r.headers["content-disposition"])
    check("student blocked from rtos course page", st.get("/course/rtos_record").status_code == 404)
    rtl = app.get("/course/rtos_record").headers["location"].rsplit("/", 1)[1]
    check("student blocked from rtos media", st.get("/media/rtos_record/" + rtl).status_code == 404)
    check("student blocked from admin", st.get("/admin").status_code == 404)

    # progress
    r = st.post("/api/progress", json={"course": "linux_udemy", "lesson": first, "position": 30, "duration": 100},
                headers=H)
    check("progress without csrf refused", r.status_code == 403)
    r = st.post("/api/progress", json={"course": "linux_udemy", "lesson": first, "position": 30, "duration": 100},
                headers=dict(H, **{"X-CSRF-Token": scsrf}))
    check("progress saved", r.json() == {"ok": True, "completed": False})
    check("resume position on page", 'data-start="30.0"' in st.get("/course/linux_udemy/" + first).text)
    st.post("/api/progress", json={"course": "linux_udemy", "lesson": first, "position": 95, "duration": 100},
            headers=dict(H, **{"X-CSRF-Token": scsrf}))
    r = st.get("/")
    check("course % after one of three lessons", "1 / 3 lessons" in r.text, re.findall(r"\d+ / \d+ lessons", r.text))
    r = st.get("/course/linux_udemy")
    check("course link resumes at lesson 2", r.headers.get("location") == "/course/linux_udemy/" + lids[1])

    # lesson lengths, read from the MP4 header in the background
    from learn import durations
    for _ in range(50):
        if "▶ 2 min" in st.get("/course/linux_udemy/" + first).text:
            break
        time.sleep(0.1)
    check("lesson length from the MP4 header (125 s -> 2 min)", "▶ 2 min" in st.get("/course/linux_udemy/" + first).text)
    lens = {k.rsplit("/", 1)[1]: v[2] for k, v in durations.known("linux_udemy").items()}
    check("length stored; garbage file marked unreadable", lens.get("10 Pipes.mp4") == 125.0
          and "01 Welcome.mp4" in lens and lens["01 Welcome.mp4"] is None, lens)
    check("unreadable video reported to the admin", "video header can" in app.get("/admin/courses").text)
    check("format", durations.fmt(9 * 60 + 20) == "9 min" and durations.fmt_total(76320) == "21 h 12 min")

    # ticking lessons by hand (course content checkboxes)
    J = dict(H, **{"X-CSRF-Token": scsrf})
    r = st.post("/api/complete", json={"course": "linux_udemy", "lesson": lids[2], "completed": True}, headers=J)
    check("tick a lesson by hand", r.status_code == 200 and r.json()["done"] == 2, r.text)
    r = st.post("/api/complete", json={"course": "linux_udemy", "lesson": lids[2], "completed": False}, headers=J)
    check("untick it again", r.json()["done"] == 1, r.text)
    check("tick without csrf refused", st.post("/api/complete", json={"course": "linux_udemy", "lesson": lids[2],
                                                                     "completed": True}, headers=H).status_code == 403)
    check("ticking doesn't move the resume point",
          st.get("/course/linux_udemy").headers.get("location") == "/course/linux_udemy/" + lids[1])
    with store.db() as c:
        uid0 = store.user_by_email(c, "alice@example.com")["id"]

    # --- anti-sharing ---------------------------------------------------------------
    UA = {"pc": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0 Safari/537.36",
          "phone": "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/131.0 Mobile Safari/537.36",
          "mac": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_1) AppleWebKit/605.1.15 Version/17.1 Safari/605.1.15"}

    def device(name, ip):
        cl = TestClient(web.app, base_url="http://testserver", follow_redirects=False,
                        headers={"User-Agent": UA[name], "X-Real-IP": ip})
        r = cl.post("/login", data={"email": "alice@example.com", "password": "alice-pass-123"}, headers=H)
        assert r.status_code == 303, r.status_code
        return cl, csrf_of(cl.get("/course/linux_udemy/" + first).text)

    pc, pc_csrf = device("pc", "81.10.0.5")
    phone, ph_csrf = device("phone", "41.226.7.9")
    check("2 extra devices: the oldest (invite session) is signed out", st.get("/").status_code == 303)
    mac, mac_csrf = device("mac", "196.203.1.1")
    check("3rd device signs out the least recent one (pc)", pc.get("/").status_code == 303
          and phone.get("/").status_code == 200)
    with store.db() as c:                         # the phone was used more recently than the mac
        c.execute("UPDATE sessions SET last_seen = last_seen + 60 WHERE device = 'Chrome on Android'")
    pc, pc_csrf = device("pc", "81.10.0.5")       # pc back in, mac (least recently active) out
    r = phone.get("/account")
    check("account page lists devices", "Chrome on Android" in r.text and "Chrome on Windows" in r.text
          and "Safari on Mac" not in r.text, re.findall(r"\w+ on \w+", r.text))

    JH = lambda tok: dict(H, **{"X-CSRF-Token": tok})
    play = lambda cl, tok, takeover=False: cl.post("/api/play", json={"takeover": takeover}, headers=JH(tok))
    ping = lambda cl, tok, playing: cl.post("/api/progress", json={"course": "linux_udemy", "lesson": first,
                                            "position": 10, "duration": 100, "playing": playing}, headers=JH(tok))
    check("pc starts playing", play(pc, pc_csrf).status_code == 200 and ping(pc, pc_csrf, True).status_code == 200)
    check("phone sees 'playing elsewhere'", phone.get("/api/play").json()["elsewhere"] == "Chrome on Windows")
    check("phone play refused (409)", play(phone, ph_csrf).status_code == 409)
    check("phone gets no video bytes while pc plays", phone.get("/media/linux_udemy/" + first,
          headers={"Range": "bytes=0-9"}).status_code == 409)
    check("attachments still fine on phone", phone.get("/media/linux_udemy/" + att.group(1)).status_code == 200)
    check("phone takes over", play(phone, ph_csrf, takeover=True).status_code == 200)
    check("pc heartbeat now told to stop", ping(pc, pc_csrf, True).status_code == 409)
    check("pc gets no more video bytes", pc.get("/media/linux_udemy/" + first,
          headers={"Range": "bytes=0-9"}).status_code == 409)
    check("phone pauses -> lock released", ping(phone, ph_csrf, False).status_code == 200
          and play(pc, pc_csrf).status_code == 200)
    r = app.get("/admin")
    check("admin list shows the sharing column", "Sharing (30 days)" in r.text)
    r = app.get("/admin/user/%d" % uid0)
    check("admin student page: devices + activity", "Chrome on Android" in r.text and "took over playback" in r.text
          and "signed out by the device limit" in r.text)
    app.post("/admin/user/%d" % uid0, data={"csrf": csrf, "action": "signout_all"}, headers=H)
    check("admin 'sign out everywhere'", pc.get("/").status_code == 303 and phone.get("/").status_code == 303)
    with store.db() as c:
        for i in range(6):
            web.guard.log(c, uid0, "login", "10.%d.0.1" % i, "Chrome on Windows")
        sig = web.guard.signals(c, uid0)
    check("6 networks in a week -> warning", any("networks" in w for w in sig["warnings"]), sig["warnings"])
    st.post("/login", data={"email": "alice@example.com", "password": "alice-pass-123"}, headers=H)

    # --- Android app API (bearer token, no cookies, no CSRF) ------------------------
    mob = TestClient(web.app, base_url="http://testserver", follow_redirects=False,
                     headers={"User-Agent": "OpCodeLearn/1.0 (Android 14; Pixel 7)", "X-Real-IP": "41.1.1.1"})
    check("app: wrong password -> 401", mob.post("/api/v1/login", json={"email": "alice@example.com",
                                                                        "password": "nope"}).status_code == 401)
    r = mob.post("/api/v1/login", json={"email": "alice@example.com", "password": "alice-pass-123"})
    tok = r.json().get("token", "")
    check("app: login returns a token", r.status_code == 200 and len(tok) > 20 and not mob.cookies)
    B = {"Authorization": "Bearer " + tok}
    check("app: no token -> 401", mob.get("/api/v1/courses").status_code == 401)
    r = mob.get("/api/v1/courses", headers=B)
    check("app: course list (linux only)", [c["slug"] for c in r.json()["courses"]] == ["linux_udemy"], r.text[:200])
    r = mob.get("/api/v1/courses/linux_udemy", headers=B)
    j = r.json()
    check("app: course JSON with sections, lessons, attachments, watermark",
          j["title"] == "Linux from scratch" and len(j["sections"]) == 2 and j["watermark"] == "alice@example.com"
          and j["sections"][0]["lessons"][0]["attachments"][0]["name"] == "01 Welcome.pdf", r.text[:300])
    check("app: links in course JSON",
          j["links"] == [{"title": "Course code", "url": "https://github.com/OpCodeLab/linux-course"}]
          and j["sections"][0]["lessons"][0]["links"][0]["url"] == "https://github.com/OpCodeLab/lesson1"
          and j["sections"][0]["links"][0]["title"] == "Man pages", str(j.get("links")))
    check("app: other course -> 404", mob.get("/api/v1/courses/rtos_record", headers=B).status_code == 404)
    r = mob.get("/media/linux_udemy/" + first, headers=dict(B, Range="bytes=0-9"))
    check("app: video with bearer token", r.status_code == 206 and r.content == VIDEO[:10])
    r = mob.post("/api/play", json={}, headers=B)
    check("app: play without CSRF (bearer)", r.status_code == 200, r.text)
    r = mob.post("/api/progress", json={"course": "linux_udemy", "lesson": first, "position": 12, "duration": 100,
                                        "playing": True}, headers=B)
    check("app: progress ping", r.status_code == 200)
    check("website sees the app playing", st.get("/api/play").json()["elsewhere"] == "App on Pixel 7 (Android 14)")
    check("app: me", mob.get("/api/v1/me", headers=B).json()["device"] == "App on Pixel 7 (Android 14)")
    mob.post("/api/v1/logout", headers=B)
    check("app: logout kills the token", mob.get("/api/v1/me", headers=B).status_code == 401)
    check("app: version 404 until an APK is published", mob.get("/api/v1/app").status_code in (200, 404))
    r = app.post("/api/v1/login", json={"email": "admin@example.com", "password": "admin-password-123"})
    check("app: admin needs the code", r.status_code == 401 and r.json()["error"] == "code required")
    st.post("/login", data={"email": "alice@example.com", "password": "alice-pass-123"}, headers=H)

    # questions under the video
    scsrf = csrf_of(st.get("/course/linux_udemy/" + first).text)
    SH = dict(H, **{"X-CSRF-Token": scsrf})
    r = st.get("/course/linux_udemy/" + first)
    check("questions tab on the lesson page", 'id="ask"' in r.text and "Questions</button>" in r.text)
    r = st.post("/api/questions", json={"course": "linux_udemy", "lesson": first, "position": 754.4,
                                        "body": "Why fork?"}, headers=H)
    check("question without csrf refused", r.status_code == 403)
    r = st.post("/api/questions", json={"course": "rtos_record", "lesson": rtl, "body": "Not my course"}, headers=SH)
    check("question on a course not enrolled refused", r.status_code == 403)
    r = st.post("/api/questions", json={"course": "linux_udemy", "lesson": first, "body": "x" * 5000}, headers=SH)
    check("too long question refused", r.status_code == 400)
    sent.clear()
    r = st.post("/api/questions", json={"course": "linux_udemy", "lesson": first, "position": 754.4,
                                        "body": "Why does <b>fork</b> return twice?\nLine 2"}, headers=SH)
    check("question saved", r.status_code == 200 and r.json()["question"]["at"] == "12:34", r.text)
    qid = r.json()["question"]["id"]
    m = sent[0] if sent else None
    check("trainer emailed with lesson, time and link", m is not None and m["To"] == "trainer@opcode.test"
          and "Welcome" in m["Subject"] and "\n" not in m["Subject"]
          and "at 12:34" in m.get_content() and "/admin/questions/%d" % qid in m.get_content()
          and "?t=754" in m.get_content(), m and m.get_content())
    with store.db() as c:
        check("trainer mail status stored", store.question(c, qid)["trainer_mail"] == "sent")
    r = st.get("/course/linux_udemy/" + first)
    check("student sees own question (escaped), waiting", "&lt;b&gt;fork&lt;/b&gt;" in r.text
          and "Waiting for an answer" in r.text and "Questions (1)" in r.text)
    check("?t= opens the video at that time", 'data-start="754.0"' in st.get("/course/linux_udemy/%s?t=754" % first).text)
    r = app.get("/admin/questions")
    check("admin inbox lists it, menu count", "Why does &lt;b&gt;fork" in r.text and 'class="badge">1<' in r.text)
    check("student can't open the inbox", st.get("/admin/questions").status_code == 404)
    acsrf = csrf_of(app.get("/admin/questions/%d" % qid).text)
    sent.clear()
    r = app.post("/admin/questions/%d" % qid, data={"csrf": acsrf, "action": "answer", "email": "1",
                                                   "answer": "Because the process is copied."}, headers=H)
    m = sent[0] if sent else None
    check("answer emailed to the student", r.status_code == 200 and m is not None and m["To"] == "alice@example.com"
          and "Because the process is copied." in m.get_content() and "> Why does <b>fork</b> return twice?" in m.get_content()
          and "?t=754" in m.get_content(), m and m.get_content())
    r = st.get("/course/linux_udemy/" + first)
    check("student sees the answer under the video", "Because the process is copied." in r.text)
    check("answered: inbox empty again", "No questions waiting" in app.get("/admin/questions").text)
    sent.clear()
    app.post("/admin/questions/%d" % qid, data={"csrf": acsrf, "action": "answer", "answer": "Edited."}, headers=H)
    check("answer edited without email", not sent and "Edited." in st.get("/course/linux_udemy/" + first).text)
    mailer.deliver = lambda msg: (_ for _ in ()).throw(OSError("connection refused"))
    st.post("/api/questions", json={"course": "linux_udemy", "lesson": first, "position": 1, "body": "Mail down?"},
            headers=SH)
    r = app.get("/admin/questions")
    check("failed email shown, question kept", "Mail down?" in r.text and "email failed" in r.text)
    mailer.deliver = lambda msg: sent.append(msg)
    for i in range(10):
        r = st.post("/api/questions", json={"course": "linux_udemy", "lesson": first, "body": "flood %d" % i},
                    headers=SH)
    check("max 10 questions per hour", r.status_code == 429, r.status_code)
    r = app.post("/admin/questions/%d" % qid, data={"csrf": acsrf, "action": "delete"}, headers=H)
    check("admin deletes a question", r.status_code == 303 and "Edited." not in st.get("/course/linux_udemy/" + first).text)

    # expiry and disable
    with store.db() as c:
        c.execute("UPDATE enrollments SET expires_at = 1 WHERE course = 'linux_udemy'")
    check("expired access -> course hidden", "Linux from scratch" not in st.get("/").text
          and st.get("/media/linux_udemy/" + first).status_code == 404)
    with store.db() as c:
        uid = store.user_by_email(c, "alice@example.com")["id"]
    r = app.post("/admin/user/%d" % uid, data={"csrf": csrf, "action": "enroll", "course": "linux_udemy",
                                                "expires": ""}, headers=H)
    check("admin re-opens access (no end date)", "Access saved" in r.text and st.get("/media/linux_udemy/" + first,
          headers={"Range": "bytes=0-0"}).status_code == 206)
    app.post("/admin/user/%d" % uid, data={"csrf": csrf, "action": "disable"}, headers=H)
    check("disabled student is signed out", st.get("/").status_code == 303)
    r = st.post("/login", data={"email": "alice@example.com", "password": "alice-pass-123"}, headers=H)
    check("disabled student can't sign in", r.status_code == 401)
    app.post("/admin/user/%d" % uid, data={"csrf": csrf, "action": "enable"}, headers=H)
    r = app.post("/admin/user/%d" % uid, data={"csrf": csrf, "action": "invite"}, headers=H)
    check("reset link generated", "/invite/" in r.text)
    r = st.post("/login", data={"email": "alice@example.com", "password": "alice-pass-123"}, headers=H)
    check("enabled student signs in again", r.status_code == 303)

    # throttling
    for _ in range(8):
        st.post("/login", data={"email": "bob@example.com", "password": "x"}, headers=H)
    r = st.post("/login", data={"email": "bob@example.com", "password": "x"}, headers=H)
    check("login throttled after 8 failures", r.status_code == 429)

    # delete
    r = app.post("/admin/user/%d" % uid, data={"csrf": csrf, "action": "delete", "confirm": "alice@example.com"},
                 headers=H)
    with store.db() as c:
        gone = store.user_by_email(c, "alice@example.com") is None
        left = c.execute("SELECT COUNT(*) FROM progress").fetchone()[0]
    check("delete removes user and progress", r.status_code == 303 and gone and left == 0)

    # Pi offline
    srv.terminate(); srv.wait()
    web.catalog.refresh_all()
    r = app.get("/")
    check("Pi offline -> friendly 503", r.status_code == 503 and "offline" in r.text.lower())
finally:
    if srv.poll() is None:
        srv.terminate()

print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
