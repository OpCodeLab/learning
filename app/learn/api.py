"""JSON API for the Android app (/api/v1/...).

The app signs in once and then sends "Authorization: Bearer <token>" on every request,
media included. Same rules as the website: same sessions table (so the 2-device limit
counts the app as a device), same course access and expiry checks, same play lock
(/api/play, /api/progress), same sharing signals.
"""
import json
import os

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from . import catalog, config, guard, security, store, web

APP_SESSION_DAYS = 30
APK_DIR = os.path.join(os.path.dirname(__file__), "static", "app")


def err(message, status):
    return JSONResponse({"error": message}, status)


def need(request):
    s, u = web.current(request)
    return (s, u) if u else (None, None)


def file_json(f):
    return {"id": f.id, "name": f.name, "size": f.size}


def link_json(k):
    return {"title": k.title, "url": k.url}


async def login(request: Request):
    """{"email", "password", "code"?} -> {"token", "user"}. Admins also send their TOTP code."""
    try:
        data = await request.json()
    except ValueError:
        return err("bad json", 400)
    email = str(data.get("email", "")).strip().lower()
    pw = str(data.get("password", ""))
    ip = web.client_ip(request)
    if web.throttle.blocked(ip, email):
        return err("Too many attempts. Wait 15 minutes and try again.", 429)
    with store.db() as c:
        u = store.user_by_email(c, email)
    ok = security.verify_password(pw, u["pw_hash"] if u and u["pw_hash"] else security.DUMMY_HASH)
    if not (u and ok and not u["disabled"]):
        web.throttle.fail(ip, email)
        return err("Wrong email or password.", 401)
    if u["is_admin"]:
        if not data.get("code"):
            return err("code required", 401)          # the app then asks for the authenticator code
        step = security.totp_check(u["totp_secret"] or "", str(data.get("code")), u["totp_step"])
        if step is None:
            web.throttle.fail(ip, email)
            return err("Wrong or already used code.", 401)
        with store.db() as c:
            c.execute("UPDATE users SET totp_step = ? WHERE id = ?", (step, u["id"]))
    web.throttle.clear(email)
    with store.db() as c:
        c.execute("UPDATE users SET last_login = ? WHERE id = ?", (store.now(), u["id"]))
    token = web.new_session(request, u, "ok", APP_SESSION_DAYS * 86400)
    return JSONResponse({"token": token, "user": {"email": u["email"], "name": u["name"],
                                                  "is_admin": bool(u["is_admin"])}})


async def logout(request: Request):
    s, u = need(request)
    if s:
        with store.db() as c:
            c.execute("DELETE FROM sessions WHERE token_hash = ?", (s["token_hash"],))
            guard.release_playback(c, u["id"], s["token_hash"])
    return JSONResponse({"ok": True})


async def me(request: Request):
    s, u = need(request)
    if not u:
        return err("login", 401)
    return JSONResponse({"email": u["email"], "name": u["name"], "is_admin": bool(u["is_admin"]),
                         "max_devices": config.MAX_DEVICES, "device": s["device"]})


async def courses(request: Request):
    s, u = need(request)
    if not u:
        return err("login", 401)
    try:
        names = catalog.course_names()
        out = []
        with store.db() as c:
            mine = names if u["is_admin"] else [n for n in names if n in store.active_courses(c, u["id"])]
            ens = {e["course"]: e for e in store.enrollments(c, u["id"])}
            for n in mine:
                course = catalog.course(n)
                if not course:
                    continue
                _, done, total, pct = web.course_progress(c, u["id"], course)
                out.append({"slug": n, "title": course.title, "description": course.description,
                            "cover": course.cover.id if course.cover else None,
                            "lessons": total, "done": done, "pct": pct,
                            "expires": ens[n]["expires_at"] if n in ens else None})
    except catalog.Unavailable:
        return err("offline", 503)
    return JSONResponse({"courses": out})


async def course(request: Request):
    s, u = need(request)
    if not u:
        return err("login", 401)
    slug = request.path_params["slug"]
    if not web.allowed(u, slug):
        return err("not found", 404)
    try:
        crs = catalog.course(slug)
    except catalog.Unavailable:
        return err("offline", 503)
    if not crs:
        return err("not found", 404)
    with store.db() as c:
        pm, done, total, pct = web.course_progress(c, u["id"], crs)
        resume = web.resume_lesson(c, u["id"], crs, pm)

    def lesson_json(l):
        p = pm.get(l.file.path)
        return {"id": l.id, "title": l.title, "number": l.num, "index": l.index,
                "length": l.duration,     # seconds, from the video header (None until read)
                "completed": bool(p and p["completed"]),
                "position": (p["position"] if p and not p["completed"] else 0),
                "duration": (p["duration"] if p else 0),
                "attachments": [file_json(f) for f in l.attachments],
                "links": [link_json(k) for k in l.links]}

    return JSONResponse({
        "slug": slug, "title": crs.title, "description": crs.description,
        "cover": crs.cover.id if crs.cover else None, "done": done, "lessons": total, "pct": pct,
        "resume": resume.id if resume else None,
        "length": crs.total_duration or None,
        "watermark": None if u["is_admin"] else u["email"],
        "sections": [{"title": sec.title, "lessons": [lesson_json(l) for l in sec.lessons],
                      "resources": [file_json(f) for f in sec.resources],
                      "links": [link_json(k) for k in sec.links]} for sec in crs.sections],
        "links": [link_json(k) for k in crs.links],
    })


async def app_version(request: Request):
    """Latest APK, so the app can offer an update. Public (no course data)."""
    try:
        with open(os.path.join(APK_DIR, "version.json"), encoding="utf-8") as f:
            v = json.load(f)
    except (OSError, ValueError):
        return err("no app published yet", 404)
    v["url"] = "%s/static/app/%s" % (config.BASE_URL, v.get("file", "opcode-learn.apk"))
    return JSONResponse(v)


routes = [
    Route("/api/v1/login", login, methods=["POST"]),
    Route("/api/v1/logout", logout, methods=["POST"]),
    Route("/api/v1/me", me),
    Route("/api/v1/courses", courses),
    Route("/api/v1/courses/{slug}", course),
    Route("/api/v1/app", app_version),
]
