# Moving the course site to the OVH VPS (courses on its own disk)

**From:** Hostinger VPS 187.126.22.239 (site) + Pi disk (videos, through WireGuard)
**To:** OVH VPS 178.32.39.41 (`vps-ee7630e4`): site, database and videos on one server.

Only learn.opcode-labs.com moves. The lab (lab.opcode-labs.com), files.opcode-labs.com and
WireGuard stay on Hostinger, untouched. Students keep their accounts, access and progress, and
the Android app keeps working (same address).

```
student ──HTTPS──> OVH 178.32.39.41  nginx: learn.opcode-labs.com
                     ├─ opcode-learn.service        127.0.0.1:8095  (pages, logins, progress; SQLite)
                     ├─ opcode-learn-files.service  127.0.0.1:8096  (lists the course folders)
                     └─ /_media/ (internal) ── files straight from /srv/learn/courses (NVMe)
```

## 1. Copy the code to OVH and install (site runs, no HTTPS yet)
From the PC (PowerShell):
```powershell
wsl -e bash -c "cd /mnt/d/opcode_learn && tar czf - app vps pi | ssh ubuntu@178.32.39.41 'rm -rf ~/opcode_learn && mkdir ~/opcode_learn && tar xzf - -C ~/opcode_learn'"
```
On OVH (`ssh ubuntu@178.32.39.41`):
```bash
sudo bash ~/opcode_learn/vps/install.sh
```
It installs nginx, certbot and the rest, opens ports 80/443 in the firewall, creates
`/srv/learn/courses`, and stops with "Everything is installed and running, except HTTPS".

## 2. Upload the courses from the PC
Course folder name on the server = `linux_udemy` (keep it: progress is saved under that name).
```powershell
wsl bash /mnt/d/opcode_learn/tools/upload-course.sh "/mnt/d/Training/linux/udemy" linux_udemy
```
About 6 GB: the time depends on your upload speed. If it stops, run it again: it resumes.
Before: keep only one lesson 18 in `Section 4` (there are `S4_L18_...recap.mp4` and
`S4_L18_...recap_tobeupdated.mp4`); otherwise both show as lesson 18.

## 3. Switch (about 15 minutes, at a quiet time)
Progress students save on the old server after step 3a is not carried over, so do 3a to 3d together.

a. On **Hostinger**, a consistent copy of the database:
```bash
sudo python3 -c "import sqlite3; s = sqlite3.connect('/var/lib/opcode-learn/learn.sqlite'); d = sqlite3.connect('/tmp/learn-move.sqlite'); s.backup(d); d.close(); print('copy ok')"
sudo chown mehdi /tmp/learn-move.sqlite && chmod 600 /tmp/learn-move.sqlite
```
b. From the **PC**, copy it across, then delete the copy on Hostinger (it holds password hashes):
```powershell
wsl bash -c "scp -3 mehdi@187.126.22.239:/tmp/learn-move.sqlite ubuntu@178.32.39.41:/tmp/learn-move.sqlite && ssh mehdi@187.126.22.239 rm /tmp/learn-move.sqlite"
```
c. On **OVH**:
```bash
sudo bash ~/opcode_learn/vps/import-db.sh /tmp/learn-move.sqlite
```
d. **DNS**, where opcode-labs.com is managed: set the `A` record of `learn` to `178.32.39.41`.
   If there is an `AAAA` record for `learn`, set it to `2001:41d0:305:2100::1:a048` (or delete it).
   Wait until `nslookup learn.opcode-labs.com` on the PC shows 178.32.39.41.

e. On **OVH**, again (now it gets the certificate; the first time certbot asks for your email
   and the Let's Encrypt terms):
```bash
sudo bash ~/opcode_learn/vps/install.sh
```
Check: https://learn.opcode-labs.com, sign in, play a video, open the app on the phone.

## 4. Retire the old copy (a day later, when all is fine)
On **Hostinger** (only the course site's own files; the lab and files.opcode-labs.com stay):
```bash
sudo systemctl disable --now opcode-learn.service
sudo rm /etc/nginx/sites-enabled/learn.opcode-labs.com && sudo nginx -t && sudo systemctl reload nginx
sudo rm -rf /var/cache/nginx/learn_media
```
On the **Pi** (the course video server is no longer used):
```bash
sudo systemctl disable --now learn-media.service learn-media-firewall.service
```
Keep `/var/lib/opcode-learn` on Hostinger for a while as a backup, then delete it.

## Later: updating the site
```powershell
wsl -e bash -c "cd /mnt/d/opcode_learn && tar czf - app vps pi | ssh ubuntu@178.32.39.41 'rm -rf ~/opcode_learn && mkdir ~/opcode_learn && tar xzf - -C ~/opcode_learn'"
```
then on OVH `sudo bash ~/opcode_learn/vps/install.sh`.
