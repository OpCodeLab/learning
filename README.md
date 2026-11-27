# opcode_learn: OpCode Learn

A light Udemy-style course site at **https://learn.opcode-labs.com**. Video courses
are stored on the server's own NVMe disk (OVH VPS). Students get personal accounts that
you create; each sees only the courses you open for them, until an end date you choose.
Students can ask questions under any video; you answer on the site and the answer is emailed to them.

```
student ──HTTPS──> OVH VPS 178.32.39.41  nginx: learn.opcode-labs.com
                     ├─ opcode-learn.service        127.0.0.1:8095  (pages, logins, progress; SQLite)
                     ├─ opcode-learn-files.service  127.0.0.1:8096  (lists the course folders)
                     └─ /_media/ (internal) ── files straight from /srv/learn/courses (NVMe disk)
```

| Path | What |
|---|---|
| [docs/design.md](docs/design.md) | How it works and why (streaming, cache, security) |
| [docs/move-to-ovh.md](docs/move-to-ovh.md) | **Install on the OVH VPS / move from Hostinger** (steps, DNS, database) |
| [docs/install.md](docs/install.md) | Original install (Hostinger VPS + Pi disk), for reference |
| [docs/content.md](docs/content.md) | **How to publish a course** (folders, course.yaml, video format) |
| [docs/operations.md](docs/operations.md) | Students, **questions and email setup**, logs, updates, backup, lost phone, uninstall |
| `app/` | The web app (Python, Starlette, SQLite) |
| `pi/media_server.py` | Read-only file lister (runs on the VPS as opcode-learn-files.service) |
| `tools/upload-course.sh` | Upload a course folder from the PC to the server |
| `vps/` | nginx site, services, installer (`sudo bash vps/install.sh`), `import-db.sh` |
| [android/README.md](android/README.md) | **Android app**: features, build, signing key, publishing updates |
| `app/learn/api.py` | JSON API used by the Android app |
| `tools/web-mp4.sh` | Convert videos to browser-friendly MP4 |
| `tests/test_e2e.py` | End-to-end test (media server + app) |

Nothing here edits the WordPress site, the lab (lab-agent, opcode-portal, `lab.opcode-labs.com`,
wg0 peers) or `files.opcode-labs.com`.
