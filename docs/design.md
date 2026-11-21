# Design

## Requirements (from you, 2026-11-21)
- Udemy/Coursera-like but light, at its own subdomain on the existing VPS.
- Video courses stream from the Pi's disk (`DATA/Training_Opcode`), managed through files.opcode-labs.com.
- Paying students get a personal account. **You** create it (payment happens outside the site).
- Per student: which courses, until when (expiry). Progress tracking, lesson attachments, several courses.

## Why this shape
| Option | Verdict |
|---|---|
| Moodle / Open edX | **Rejected.** Heavy (PHP/MySQL or a dozen services) for 1 CPU / 4 GB, large attack surface, and they want the videos on their own storage. |
| Stream through FileBrowser Quantum | **Rejected.** No courses, progress or expiry, and every student would be a file-manager user. |
| **Small custom app + nginx** | **Chosen.** About 1000 lines of Python. nginx does the heavy lifting (TLS, video bytes, cache), and the app only decides who may see what. |

**Analogy:** the app is the ticket desk, nginx is the projectionist, and the Pi is the film archive. The desk checks
every ticket (every request, including each seek), and the projectionist keeps copies of the reels it has already shown.

## Components
- **Pi: `learn-media.service`** (`pi/media_server.py`, Python stdlib only)
  - **Read-only:** runs as `learnmedia` (group `drive`) under `ProtectSystem=strict`, so it can't write anywhere, the disk included.
  - **Bound to `10.8.3.3:8092`:** the nftables table `inet learn_media` accepts only the VPS (10.8.3.1).
    It's a separate table, so the lab's and pi_drive's rules aren't touched.
  - **Contents served:** `/list` (folders), `/tree/<course>` (files) and `/raw/<path>` (bytes, with Range for seeking).
  - **Path safety:** `..`, hidden names (`$…`, `.…`) and symlinks leaving the folder are refused.
  - **Disk unplugged:** it answers 503 if `/srv/drive/data` isn't mounted, so the site says "offline" instead of "empty".
- **VPS: `opcode-learn.service`** (`app/learn/`, Starlette + Jinja + SQLite)
  - **Sandbox:** runs as `learn` on 127.0.0.1:8095 under a systemd sandbox. Only `/var/lib/opcode-learn` is writable.
  - **Catalog:** the course list and structure come from the Pi and are cached for 60 s.
  - **Video requests:** for `/media/<course>/<file>` it checks the session and the enrollment, then answers
    `X-Accel-Redirect: /_pi/raw/<path>?v=<mtime>-<size>`. nginx then serves the bytes.
- **VPS: nginx** (`vps/nginx/learn.opcode-labs.com.conf`)
  - `/_pi/` is `internal`: a browser can't reach it, only the app's redirect can.
  - `slice 2m` plus `proxy_cache`: videos are fetched from the Pi in 2 MB pieces and kept on the
    VPS disk (max 25 GB, 60 days unused → evicted). `proxy_cache_lock` makes 10 students starting
    the same lesson cause one fetch per piece, not ten.
  - The `?v=mtime-size` in the cache key means a replaced video is a new cache entry.

## Bandwidth
The first viewer of each part of a video pulls it over your **home upload**. Every later viewer is
served from the VPS. Rule of thumb: concurrent "first viewers" ≈ upload Mbit/s ÷ video bitrate.
`tools/web-mp4.sh` keeps bitrates around 1–3 Mbit/s. To warm the cache for a new course, play each
video once yourself, or skip through it.

## Accounts and security
- **Students:** you create them in *Students → New student* (email, courses, end date). The site
  gives a **single-use invite link** (valid 14 days) that you send yourself, and the student picks
  their password with it (min 10 characters). There's no self-signup and no email server.
  A forgotten password is handled with a new link from the student's page.
- **Admin:** created with `sudo opcode-learn create-admin` on the VPS. Login is a password (min 14) plus TOTP;
  a code can't be reused. The admin session lasts 8 h, a student session 14 days.
- **Passwords** are hashed with scrypt (stdlib). Only SHA-256 hashes of session and invite tokens are stored.
- **Brute force:** nginx allows 10 requests/min per IP on `/login`, `/login/code` and `/invite/`. The app
  then locks out for 15 min after 8 failures per email or 10 per IP.
- **CSRF:** every POST must carry our own `Origin`, plus a per-session token. Cookies are `HttpOnly`, `Secure`, `SameSite=Lax`.
- **Strict CSP:** our own scripts and styles only, with no inline code and no third-party requests (no CDN, no fonts, no analytics).
- **Expiry:** checked on every request. Expired access stops at once, even mid-video.
  *Disable* also signs the student out everywhere.
- **No DRM:** links work only with a valid session, the download button is hidden, and right-click is off.
  A determined student can still screen-record. Udemy has the same limit.
- `noindex` on everything, so search engines don't list the site.
