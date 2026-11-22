# opcode_learn: OpCode Learn

A light Udemy-style course site at **https://learn.opcode-labs.com**. Video courses
stream from the USB disk on the lab Raspberry Pi 5. Students get personal accounts that
you create; each sees only the courses you open for them, until an end date you choose.

```
student ──HTTPS──> VPS 187.126.22.239  nginx: learn.opcode-labs.com (own site file + cert)
                     ├─ opcode-learn.service  127.0.0.1:8095  (pages, logins, progress, admin; SQLite)
                     └─ /_pi/ (internal) ── video cache on the VPS disk (max 25 GB)
                            │ WireGuard wg0 (existing tunnel)
                            └──> Pi 10.8.3.3:8092  learn-media.service (read-only files)
                                   /srv/drive/data/Training_Opcode/<course>/...
```

| Path | What |
|---|---|
| [docs/design.md](docs/design.md) | How it works and why (streaming, cache, security) |
| [docs/install.md](docs/install.md) | First install: DNS, Pi, VPS, admin account, checks |
| [docs/content.md](docs/content.md) | **How to publish a course** (folders, course.yaml, video format) |
| [docs/operations.md](docs/operations.md) | Students, logs, updates, backup, lost phone, uninstall |
| `app/` | The web app (Python, Starlette, SQLite) |
| `pi/` | Read-only media server for the Pi (`sudo bash pi/install.sh`) |
| `vps/` | nginx site, service and installer for the VPS (`sudo bash vps/install.sh`) |
| [android/README.md](android/README.md) | **Android app**: features, build, signing key, publishing updates |
| `app/learn/api.py` | JSON API used by the Android app |
| `tools/web-mp4.sh` | Convert videos to browser-friendly MP4 |
| `tests/test_e2e.py` | End-to-end test (media server + app) |

Nothing here edits the WordPress site, the lab (lab-agent, opcode-portal, `lab.opcode-labs.com`,
wg0 peers) or `files.opcode-labs.com`.
