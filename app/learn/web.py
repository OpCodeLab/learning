"""The web app: student pages, video access control and the admin area."""
import collections
import hmac
import datetime as dt
import os
import threading
import time
import urllib.parse
import urllib.error
import urllib.request

from starlette.applications import Starlette
from starlette.exceptions import HTTPException
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, Response, StreamingResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates

from . import catalog, config, guard, security, store

HERE = os.path.dirname(__file__)
templates = Jinja2Templates(directory=os.path.join(HERE, "templates"))
templates.env.globals["site_name"] = config.SITE_NAME
templates.env.globals["max_devices"] = config.MAX_DEVICES
COOKIE = "learn_s"


def fmt_date(ts):
    return dt.datetime.fromtimestamp(ts).strftime("%d %b %Y") if ts else ""


def fmt_size(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return ("%d %s" if unit == "B" else "%.1f %s") % (n, unit)
        n /= 1024


templates.env.filters["date"] = fmt_date
templates.env.filters["datetime"] = lambda ts: dt.datetime.fromtimestamp(ts).strftime("%d %b %H:%M") if ts else ""
templates.env.filters["isodate"] = lambda ts: dt.date.fromtimestamp(ts).isoformat() if ts else ""
templates.env.filters["size"] = fmt_size


# --- login throttling (in memory; restart clears it) ------------------------------
class Throttle:
    WINDOW = 15 * 60

    def __init__(self):
        self.lock = threading.Lock()
        self.fails = collections.defaultdict(list)

    def _recent(self, key):
        t = time.time() - self.WINDOW
        self.fails[key] = [x for x in self.fails[key] if x > t]
        return self.fails[key]

    def blocked(self, ip, email):
        with self.lock:
            return len(self._recent("ip:" + ip)) >= 10 or len(self._recent("em:" + email)) >= 8

    def fail(self, ip, email):
        with self.lock:
            self.fails["ip:" + ip].append(time.time())
            self.fails["em:" + email].append(time.time())

    def clear(self, email):
        with self.lock:
            self.fails.pop("em:" + email, None)


throttle = Throttle()


def client_ip(request):
    # nginx sets X-Real-IP; the app listens on 127.0.0.1 only, so it can't be forged.
    return request.headers.get("x-real-ip") or (request.client.host if request.client else "?")


# --- sessions ---------------------------------------------------------------------
def current(request, stage="ok"):
    """(session, user) for a valid session cookie at the given stage, else (None, None)."""
    tok = request.cookies.get(COOKIE)
    if not tok:
        return None, None
    with store.db() as c:
        s = c.execute("SELECT * FROM sessions WHERE token_hash = ?", (security.token_hash(tok),)).fetchone()
        if not s or s["expires_at"] < store.now() or s["stage"] != stage:
            return None, None
        u = store.user_by_id(c, s["user_id"])
        if s["last_seen"] < store.now() - 300:   # "last active" per device, at most every 5 min
            c.execute("UPDATE sessions SET last_seen = ?, ip = ? WHERE token_hash = ?",
                      (store.now(), client_ip(request), s["token_hash"]))
    if not u or u["disabled"]:
        return None, None
    return s, u


def device_of(request):
    return guard.device_name(request.headers.get("user-agent", ""))


def start_session(request, response, user, stage, seconds):
    tok = security.new_token()
    th, ip, dev = security.token_hash(tok), client_ip(request), device_of(request)
    with store.db() as c:
        store.purge_expired(c)
        c.execute("INSERT INTO sessions (token_hash, user_id, csrf, stage, expires_at, created_at, last_seen, ip, device) "
                  "VALUES (?,?,?,?,?,?,?,?,?)", (th, user["id"], security.new_token(), stage, store.now() + seconds,
                                                 store.now(), store.now(), ip, dev))
        if stage == "ok" and not user["is_admin"]:
            guard.log(c, user["id"], "login", ip, dev)
            guard.enforce_device_limit(c, user["id"], th)
    response.set_cookie(COOKIE, tok, max_age=seconds, httponly=True, secure=config.COOKIE_SECURE,
                        samesite="lax", path="/")


def end_session(request, response):
    tok = request.cookies.get(COOKIE)
    if tok:
        with store.db() as c:
            c.execute("DELETE FROM sessions WHERE token_hash = ?", (security.token_hash(tok),))
    response.delete_cookie(COOKIE, path="/")


def same_origin(request):
    """Every POST must come from our own pages (blocks cross-site form posts)."""
    origin = request.headers.get("origin") or request.headers.get("referer") or ""
    base = urllib.parse.urlsplit(config.BASE_URL)
    o = urllib.parse.urlsplit(origin)
    return (o.scheme, o.netloc) == (base.scheme, base.netloc)


async def form_checked(request, session):
    if not same_origin(request):
        raise HTTPException(403, "Bad origin")
    form = await request.form()
    if session is not None and not hmac.compare_digest(form.get("csrf", ""), session["csrf"]):
        raise HTTPException(403, "Expired form, reload the page")
    return form


def render(request, name, status=200, **ctx):
    return templates.TemplateResponse(request, name, ctx, status_code=status)


def need_login(request):
    s, u = current(request)
    if not u:
        nxt = urllib.parse.quote(request.url.path)
        raise HTTPException(303, headers={"Location": "/login?next=" + nxt})
    return s, u


def need_admin(request):
    s, u = need_login(request)
    if not u["is_admin"]:
        raise HTTPException(404)
    return s, u


def allowed(user, slug):
    if user["is_admin"]:
        return True
    with store.db() as c:
        return slug in store.active_courses(c, user["id"])


def safe_next(nxt):
    return nxt if nxt.startswith("/") and not nxt.startswith("//") else "/"


# --- login / logout / invites -------------------------------------------------------
async def login(request: Request):
    nxt = safe_next(request.query_params.get("next", "/"))
    if request.method == "GET":
        if current(request)[1]:
            return RedirectResponse(nxt, 303)
        return render(request, "login.html", next=nxt)
    form = await form_checked(request, None)
    email = (form.get("email") or "").strip().lower()
    pw = form.get("password") or ""
    nxt = safe_next(form.get("next") or "/")
    ip = client_ip(request)
    if throttle.blocked(ip, email):
        return render(request, "login.html", 429, next=nxt, email=email,
                      error="Too many attempts. Wait 15 minutes and try again.")
    with store.db() as c:
        u = store.user_by_email(c, email)
    ok = security.verify_password(pw, u["pw_hash"] if u and u["pw_hash"] else security.DUMMY_HASH)
    if not (u and ok and not u["disabled"]):
        throttle.fail(ip, email)
        return render(request, "login.html", 401, next=nxt, email=email, error="Wrong email or password.")
    if u["is_admin"]:
        resp = RedirectResponse("/login/code?next=" + urllib.parse.quote(nxt), 303)
        start_session(request, resp, u, "totp", 300)
        return resp
    throttle.clear(email)
    with store.db() as c:
        c.execute("UPDATE users SET last_login = ? WHERE id = ?", (store.now(), u["id"]))
    resp = RedirectResponse(nxt, 303)
    start_session(request, resp, u, "ok", config.STUDENT_SESSION_DAYS * 86400)
    return resp


async def login_code(request: Request):
    s, u = current(request, stage="totp")
    if not u:
        return RedirectResponse("/login", 303)
    nxt = safe_next(request.query_params.get("next", "/admin"))
    if request.method == "GET":
        return render(request, "login_code.html", next=nxt)
    form = await form_checked(request, None)
    nxt = safe_next(form.get("next") or "/admin")
    ip = client_ip(request)
    if throttle.blocked(ip, u["email"]):
        return render(request, "login_code.html", 429, next=nxt, error="Too many attempts. Wait 15 minutes.")
    step = security.totp_check(u["totp_secret"] or "", form.get("code"), u["totp_step"])
    if step is None:
        throttle.fail(ip, u["email"])
        return render(request, "login_code.html", 401, next=nxt, error="Wrong or already used code.")
    throttle.clear(u["email"])
    with store.db() as c:
        c.execute("UPDATE users SET totp_step = ?, last_login = ? WHERE id = ?", (step, store.now(), u["id"]))
    resp = RedirectResponse(nxt if nxt != "/" else "/admin", 303)
    end_session(request, resp)
    start_session(request, resp, u, "ok", config.ADMIN_SESSION_HOURS * 3600)
    return resp


async def logout(request: Request):
    s, u = current(request)
    if s:
        await form_checked(request, s)
    resp = RedirectResponse("/login", 303)
    end_session(request, resp)
    return resp


async def invite(request: Request):
    token = request.path_params["token"]
    th = security.token_hash(token)
    with store.db() as c:
        inv = c.execute("SELECT * FROM invites WHERE token_hash = ? AND expires_at > ?", (th, store.now())).fetchone()
        u = store.user_by_id(c, inv["user_id"]) if inv else None
    if not u or u["disabled"]:
        return render(request, "message.html", 404, title="Link expired",
                      text="This link is no longer valid. Ask your trainer for a new one.")
    if request.method == "GET":
        return render(request, "invite.html", student=u)
    form = await form_checked(request, None)
    pw, pw2 = form.get("password") or "", form.get("password2") or ""
    error = None
    if len(pw) < config.MIN_PASSWORD:
        error = "Use at least %d characters." % config.MIN_PASSWORD
    elif pw != pw2:
        error = "The two passwords are different."
    if error:
        return render(request, "invite.html", 400, student=u, error=error)
    with store.db() as c:
        c.execute("UPDATE users SET pw_hash = ?, last_login = ? WHERE id = ?",
                  (security.hash_password(pw), store.now(), u["id"]))
        c.execute("DELETE FROM invites WHERE user_id = ?", (u["id"],))
        c.execute("DELETE FROM sessions WHERE user_id = ?", (u["id"],))
    resp = RedirectResponse("/", 303)
    start_session(request, resp, u, "ok", config.STUDENT_SESSION_DAYS * 86400)
    return resp


# --- student pages ------------------------------------------------------------------
def course_progress(c, uid, course):
    pm = store.progress_map(c, uid, course.slug)
    done = sum(1 for l in course.lessons if pm.get(l.file.path) and pm[l.file.path]["completed"])
    total = len(course.lessons)
    return pm, done, total, (round(100 * done / total) if total else 0)


def unavailable(request):
    return render(request, "message.html", 503, title="Courses are offline for a moment",
                  text="The video server can't be reached right now. Please try again in a few minutes.")


async def home(request: Request):
    s, u = need_login(request)
    try:
        names = catalog.course_names()
        with store.db() as c:
            mine = names if u["is_admin"] else [n for n in names if n in store.active_courses(c, u["id"])]
            ens = {e["course"]: e for e in store.enrollments(c, u["id"])}
            cards = []
            for n in mine:
                course = catalog.course(n)
                if not course:
                    continue
                _, done, total, pct = course_progress(c, u["id"], course)
                cards.append(dict(course=course, done=done, total=total, pct=pct,
                                  expires=ens.get(n)["expires_at"] if ens.get(n) else None))
    except catalog.Unavailable:
        return unavailable(request)
    return render(request, "home.html", user=u, session=s, cards=cards)


async def course_page(request: Request):
    s, u = need_login(request)
    slug = request.path_params["slug"]
    if not allowed(u, slug):
        raise HTTPException(404)
    try:
        course = catalog.course(slug)
    except catalog.Unavailable:
        return unavailable(request)
    if not course:
        raise HTTPException(404)
    with store.db() as c:
        pm, done, total, pct = course_progress(c, u["id"], course)
        last = store.last_watched(c, u["id"], slug)
    resume = next((l for l in course.lessons if last and l.file.path == last["lesson"]), None)
    if resume and pm[resume.file.path]["completed"] and resume.index + 1 < total:
        resume = course.lessons[resume.index + 1]
    return render(request, "course.html", user=u, session=s, course=course, pm=pm, done=done,
                  total=total, pct=pct, resume=resume or (course.lessons[0] if course.lessons else None))


async def lesson_page(request: Request):
    s, u = need_login(request)
    slug, lid = request.path_params["slug"], request.path_params["lid"]
    if not allowed(u, slug):
        raise HTTPException(404)
    try:
        course = catalog.course(slug)
    except catalog.Unavailable:
        return unavailable(request)
    lesson = course.lesson(lid) if course else None
    if not lesson:
        raise HTTPException(404)
    with store.db() as c:
        pm, done, total, pct = course_progress(c, u["id"], course)
    lessons = course.lessons
    prev = lessons[lesson.index - 1] if lesson.index > 0 else None
    nxt = lessons[lesson.index + 1] if lesson.index + 1 < len(lessons) else None
    p = pm.get(lesson.file.path)
    start = p["position"] if p and not p["completed"] else 0
    return render(request, "lesson.html", user=u, session=s, course=course, lesson=lesson, pm=pm,
                  pct=pct, prev=prev, next=nxt, start=start)


async def progress_api(request: Request):
    s, u = current(request)
    if not u:
        return JSONResponse({"error": "login"}, 401)
    if not (same_origin(request) and hmac.compare_digest(request.headers.get("x-csrf-token", ""), s["csrf"])):
        return JSONResponse({"error": "csrf"}, 403)
    data = await request.json()
    slug, lid = str(data.get("course", "")), str(data.get("lesson", ""))
    if not allowed(u, slug):
        return JSONResponse({"error": "forbidden"}, 403)
    try:
        course = catalog.course(slug)
    except catalog.Unavailable:
        return JSONResponse({"error": "offline"}, 503)
    lesson = course.lesson(lid) if course else None
    if not lesson:
        return JSONResponse({"error": "unknown lesson"}, 404)
    try:
        pos, dur = max(0.0, float(data.get("position", 0))), max(0.0, float(data.get("duration", 0)))
    except (TypeError, ValueError):
        return JSONResponse({"error": "bad numbers"}, 400)
    completed = bool(data.get("ended")) or (dur > 0 and pos >= 0.9 * dur)
    playing = bool(data.get("playing"))
    with store.db() as c:
        if not u["is_admin"]:
            other = guard.playing_elsewhere(c, u["id"], s["token_hash"])
            if other and playing:
                # another device took over: this one must stop (progress is still saved)
                store.save_progress(c, u["id"], slug, lesson.file.path, pos, dur, completed)
                return JSONResponse({"error": "elsewhere", "device": other["device"]}, 409)
            if playing:
                guard.take_playback(c, u["id"], s["token_hash"], s["device"])
            else:
                guard.release_playback(c, u["id"], s["token_hash"])
        store.save_progress(c, u["id"], slug, lesson.file.path, pos, dur, completed)
    return JSONResponse({"ok": True, "completed": completed})


async def play_api(request: Request):
    """Called when the player starts. 409 if the account is already playing on another device,
    unless the student chose "Watch here instead" (takeover)."""
    s, u = current(request)
    if not u:
        return JSONResponse({"error": "login"}, 401)
    if request.method == "GET":   # status only, takes nothing: is another device playing?
        if u["is_admin"]:
            return JSONResponse({"elsewhere": None})
        with store.db() as c:
            other = guard.playing_elsewhere(c, u["id"], s["token_hash"])
        return JSONResponse({"elsewhere": other["device"] if other else None})
    if not (same_origin(request) and hmac.compare_digest(request.headers.get("x-csrf-token", ""), s["csrf"])):
        return JSONResponse({"error": "csrf"}, 403)
    if u["is_admin"]:
        return JSONResponse({"ok": True})
    data = await request.json()
    with store.db() as c:
        other = guard.playing_elsewhere(c, u["id"], s["token_hash"])
        if other and not data.get("takeover"):
            guard.log(c, u["id"], "blocked", client_ip(request), s["device"])
            return JSONResponse({"error": "elsewhere", "device": other["device"]}, 409)
        if other:
            guard.log(c, u["id"], "takeover", client_ip(request), s["device"])
        guard.take_playback(c, u["id"], s["token_hash"], s["device"])
    return JSONResponse({"ok": True})


async def media(request: Request):
    """Videos, attachments and covers. Access is checked on every request (also every seek)."""
    s, u = current(request)
    if not u:
        raise HTTPException(401)
    slug, fid = request.path_params["slug"], request.path_params["fid"]
    if not allowed(u, slug):
        raise HTTPException(404)
    try:
        course = catalog.course(slug)
    except catalog.Unavailable:
        raise HTTPException(503)
    if not course:
        raise HTTPException(404)
    lesson = course.lesson(fid)
    f = lesson.file if lesson else course.file(fid)
    if not f:
        raise HTTPException(404)
    if lesson and not u["is_admin"]:
        with store.db() as c:
            if guard.playing_elsewhere(c, u["id"], s["token_hash"]):
                raise HTTPException(409)   # the other device must stop first (or be taken over)
    disposition = "inline" if lesson or f is course.cover else "attachment"
    headers = {
        "Content-Disposition": "%s; filename*=UTF-8''%s" % (disposition, urllib.parse.quote(f.name)),
        # videos: no browser cache, so every part goes through the access check above
        "Cache-Control": "private, no-store" if lesson else "private, max-age=3600",
        "X-Content-Type-Options": "nosniff",
    }
    raw_path = "/raw/" + urllib.parse.quote(slug + "/" + f.path)
    if not config.DEV_PROXY:
        # nginx serves the bytes from its cache, or fetches them from the Pi in 2 MB slices.
        # The version (mtime-size) makes a replaced file a new cache entry.
        headers["X-Accel-Redirect"] = "/_pi%s?v=%d-%d" % (raw_path, f.mtime, f.size)
        return Response(b"", headers=headers)
    req = urllib.request.Request(config.MEDIA_URL + raw_path)
    if request.headers.get("range"):
        req.add_header("Range", request.headers["range"])
    try:
        up = urllib.request.urlopen(req, timeout=15)
    except urllib.error.HTTPError as e:
        return Response(status_code=e.code)
    except OSError:
        raise HTTPException(503)
    for h in ("Content-Type", "Content-Length", "Content-Range", "Accept-Ranges", "Last-Modified"):
        if up.headers.get(h):
            headers[h] = up.headers[h]

    def body():
        with up:
            while chunk := up.read(256 * 1024):
                yield chunk
    return StreamingResponse(body(), status_code=up.status, headers=headers)


def account_page(request, s, u, status=200, **extra):
    with store.db() as c:
        devs = guard.devices(c, u["id"])
    return render(request, "account.html", status, user=u, session=s, devices=devs,
                  max_devices=config.MAX_DEVICES, **extra)


async def account(request: Request):
    s, u = need_login(request)
    if request.method == "GET":
        return account_page(request, s, u)
    form = await form_checked(request, s)
    if form.get("action") == "signout_others":
        with store.db() as c:
            c.execute("DELETE FROM sessions WHERE user_id = ? AND token_hash != ?", (u["id"], s["token_hash"]))
        return account_page(request, s, u, signed_out=True)
    cur, pw, pw2 = form.get("current") or "", form.get("password") or "", form.get("password2") or ""
    error = None
    if not security.verify_password(cur, u["pw_hash"] or security.DUMMY_HASH):
        error = "Your current password is wrong."
    elif len(pw) < config.MIN_PASSWORD:
        error = "Use at least %d characters." % config.MIN_PASSWORD
    elif pw != pw2:
        error = "The two new passwords are different."
    if error:
        return account_page(request, s, u, 400, error=error)
    with store.db() as c:
        c.execute("UPDATE users SET pw_hash = ? WHERE id = ?", (security.hash_password(pw), u["id"]))
        # sign out every other device
        c.execute("DELETE FROM sessions WHERE user_id = ? AND token_hash != ?", (u["id"], s["token_hash"]))
    return account_page(request, s, u, saved=True)


# --- admin --------------------------------------------------------------------------
def parse_date(value):
    """'2027-11-21' -> end of that day (timestamp); '' -> None (no end date)."""
    value = (value or "").strip()
    if not value:
        return None
    d = dt.datetime.strptime(value, "%Y-%m-%d") + dt.timedelta(days=1)
    return int(d.timestamp()) - 1


def default_expiry():
    return (dt.date.today() + dt.timedelta(days=365)).isoformat()


def new_invite(c, uid):
    tok = security.new_token()
    c.execute("DELETE FROM invites WHERE user_id = ?", (uid,))
    c.execute("INSERT INTO invites (token_hash, user_id, expires_at) VALUES (?,?,?)",
              (security.token_hash(tok), uid, store.now() + config.INVITE_DAYS * 86400))
    return "%s/invite/%s" % (config.BASE_URL, tok)


async def admin_home(request: Request):
    s, u = need_admin(request)
    with store.db() as c:
        rows = []
        for st in store.students(c):
            ens = store.enrollments(c, st["id"])
            rows.append(dict(user=st, enrollments=ens, invited=st["pw_hash"] is None,
                             signals=guard.signals(c, st["id"])))
    try:
        names = catalog.course_names()
    except catalog.Unavailable:
        names = None
    return render(request, "admin_home.html", user=u, session=s, rows=rows, courses=names, now=store.now())


async def admin_new(request: Request):
    s, u = need_admin(request)
    try:
        names = catalog.course_names()
    except catalog.Unavailable:
        return unavailable(request)
    if request.method == "GET":
        return render(request, "admin_new.html", user=u, session=s, courses=names, expiry=default_expiry())
    form = await form_checked(request, s)
    email = (form.get("email") or "").strip().lower()
    name = (form.get("name") or "").strip()
    chosen = [n for n in form.getlist("course") if n in names]
    error = None
    if "@" not in email or len(email) > 200:
        error = "Enter a valid email."
    try:
        expires = parse_date(form.get("expires"))
    except ValueError:
        error = "Invalid end date."
    with store.db() as c:
        if not error and store.user_by_email(c, email):
            error = "This email already has an account."
        if error:
            return render(request, "admin_new.html", 400, user=u, session=s, courses=names, error=error,
                          email=email, name=name, chosen=chosen, expiry=form.get("expires") or "")
        uid = store.create_user(c, email, name)
        for n in chosen:
            store.set_enrollment(c, uid, n, expires)
        link = new_invite(c, uid)
    return render(request, "admin_link.html", user=u, session=s, student=email, link=link, uid=uid,
                  days=config.INVITE_DAYS)


async def admin_user(request: Request):
    s, u = need_admin(request)
    uid = request.path_params["uid"]
    with store.db() as c:
        st = store.user_by_id(c, uid)
    if not st or st["is_admin"]:
        raise HTTPException(404)
    try:
        names = catalog.course_names()
    except catalog.Unavailable:
        names = []
    link = None
    msg = None
    if request.method == "POST":
        form = await form_checked(request, s)
        action = form.get("action")
        with store.db() as c:
            if action == "enroll" and form.get("course") in names:
                try:
                    store.set_enrollment(c, uid, form["course"], parse_date(form.get("expires")))
                    msg = "Access saved."
                except ValueError:
                    msg = "Invalid end date."
            elif action == "unenroll":
                store.remove_enrollment(c, uid, form.get("course", ""))
                msg = "Course removed."
            elif action == "invite":
                link = new_invite(c, uid)
                c.execute("DELETE FROM sessions WHERE user_id = ?", (uid,))
            elif action == "signout_all":
                c.execute("DELETE FROM sessions WHERE user_id = ?", (uid,))
                c.execute("DELETE FROM playback WHERE user_id = ?", (uid,))
                msg = "Signed out on every device. The password is unchanged."
            elif action == "disable":
                c.execute("UPDATE users SET disabled = 1 WHERE id = ?", (uid,))
                c.execute("DELETE FROM sessions WHERE user_id = ?", (uid,))
                msg = "Account disabled and signed out."
            elif action == "enable":
                c.execute("UPDATE users SET disabled = 0 WHERE id = ?", (uid,))
                msg = "Account enabled."
            elif action == "delete" and form.get("confirm") == st["email"]:
                c.execute("DELETE FROM users WHERE id = ?", (uid,))
                return RedirectResponse("/admin", 303)
            elif action == "delete":
                msg = "Type the email exactly to delete the account."
            elif action == "name":
                c.execute("UPDATE users SET name = ? WHERE id = ?", ((form.get("name") or "").strip(), uid))
                msg = "Name saved."
            st = store.user_by_id(c, uid)
    with store.db() as c:
        ens = store.enrollments(c, uid)
        prog = []
        for e in ens:
            try:
                course = catalog.course(e["course"])
            except catalog.Unavailable:
                course = None
            if course:
                _, done, total, pct = course_progress(c, uid, course)
                prog.append(dict(course=e["course"], title=course.title, done=done, total=total, pct=pct))
        devs = guard.devices(c, uid)
        sig = guard.signals(c, uid)
    return render(request, "admin_user.html", user=u, session=s, st=st, enrollments=ens, courses=names,
                  progress={p["course"]: p for p in prog}, link=link, msg=msg, expiry=default_expiry(),
                  now=store.now(), days=config.INVITE_DAYS, devices=devs, signals=sig,
                  max_devices=config.MAX_DEVICES)


async def admin_courses(request: Request):
    s, u = need_admin(request)
    refresh = request.query_params.get("refresh") == "1"
    if refresh:
        catalog.refresh_all()
    try:
        folders = catalog.folders(refresh)
        courses = [catalog.course(f["name"]) for f in folders if f["course"]]
    except catalog.Unavailable as e:
        return render(request, "admin_courses.html", user=u, session=s, offline=str(e), folders=[], courses=[])
    with store.db() as c:
        counts = {r["course"]: r["n"] for r in c.execute(
            "SELECT course, COUNT(*) n FROM enrollments WHERE expires_at IS NULL OR expires_at > ? GROUP BY course",
            (store.now(),))}
    return render(request, "admin_courses.html", user=u, session=s, folders=folders,
                  courses=[c for c in courses if c], counts=counts)


async def not_found(request, exc):
    if exc.status_code == 303:
        return RedirectResponse(exc.headers["Location"], 303)
    texts = {401: "Please sign in.", 403: exc.detail, 404: "This page doesn't exist or isn't available to you.",
             503: "The video server can't be reached right now."}
    return render(request, "message.html", exc.status_code, title="Error %d" % exc.status_code,
                  text=texts.get(exc.status_code, "Something went wrong."))


async def health(request):
    return Response("ok")


routes = [
    Route("/", home),
    Route("/login", login, methods=["GET", "POST"]),
    Route("/login/code", login_code, methods=["GET", "POST"]),
    Route("/logout", logout, methods=["POST"]),
    Route("/invite/{token}", invite, methods=["GET", "POST"]),
    Route("/account", account, methods=["GET", "POST"]),
    Route("/course/{slug}", course_page),
    Route("/course/{slug}/{lid}", lesson_page),
    Route("/media/{slug}/{fid}", media, methods=["GET", "HEAD"]),
    Route("/api/progress", progress_api, methods=["POST"]),
    Route("/api/play", play_api, methods=["GET", "POST"]),
    Route("/admin", admin_home),
    Route("/admin/new", admin_new, methods=["GET", "POST"]),
    Route("/admin/user/{uid:int}", admin_user, methods=["GET", "POST"]),
    Route("/admin/courses", admin_courses),
    Route("/healthz", health),
    Mount("/static", StaticFiles(directory=os.path.join(HERE, "static")), name="static"),
]


class SecurityHeaders:
    """Strict CSP: only our own scripts, styles and media."""
    CSP = ("default-src 'self'; img-src 'self' data:; media-src 'self'; style-src 'self'; script-src 'self'; "
           "object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'")

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        async def wrapped(message):
            if message["type"] == "http.response.start":
                h = message.setdefault("headers", [])
                h.append((b"content-security-policy", self.CSP.encode()))
                h.append((b"referrer-policy", b"same-origin"))
                h.append((b"x-frame-options", b"DENY"))
                if not scope["path"].startswith(("/static/", "/media/")):
                    h.append((b"cache-control", b"no-store"))
            await send(message)
        await self.app(scope, receive, wrapped)


def create_app():
    store.init()
    return Starlette(routes=routes, exception_handlers={HTTPException: not_found},
                     middleware=[Middleware(SecurityHeaders)])


app = create_app()
