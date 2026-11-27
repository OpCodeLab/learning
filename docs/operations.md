# Operations

Shorthand:
- **Pi$** `wsl -e ssh -t -J mehdi@187.126.22.239 ubuntu@10.8.3.3 "<cmd>"`
- **VPS$** `wsl -e ssh -t mehdi@187.126.22.239 "<cmd>"`

## Everyday: students
All from the web admin (Students):

| Need | Do |
|---|---|
| New paying student | *+ New student* → email, courses, end date → copy the invite link and send it yourself |
| Give another course | the student's page → *Add course* |
| Extend access | the student's page → change *Access until* → *Save* (empty = no end date) |
| Forgot password | the student's page → *Password reset link* (also signs them out everywhere) |
| Stop access now | *Disable account* (reversible) or *Remove* one course |
| Delete | *Delete this account* (type the email). Progress is deleted too. Files never are. |
| Suspect sharing (⚠ in the list) | the student's page → *Devices and sharing signals*: who, where, when. Then warn them, *Sign out everywhere*, *Password reset link*, or *Disable* |
| Student locked out by the device limit | nothing to do: signing in again works, and the least recently used device is signed out |
| Answer a student's question | **Questions** (the number = waiting) → open it → write the answer → *Send the answer*. It is emailed to the student and shown under the video |

## Questions under the videos
Students write a question in the **Questions** tab under any video. It is saved with the course, the
lesson and the video time (where the student was when they started writing), then:
1. You get an email with the question, a link that opens the video at that time, and a link to answer.
2. You answer on the site (**Questions** in the menu). The answer is emailed to the student and shown
   under the video, below their question. You can edit it later (with or without a new email).

Each student can send 10 questions per hour (spam guard), up to 4000 characters each.
Without email set up, everything still works on the site; only the emails are missing.

## Email
The site sends mail through an existing mailbox of yours (SMTP), for example
`contact@opcode-labs.com`. Take the SMTP settings from your mail provider (for a Hostinger mailbox:
`smtp.hostinger.com`, port 465). On the server:
```bash
sudo nano /etc/opcode-learn/learn.env
```
add these lines (your values; the password as is, no quotes):
```
LEARN_SMTP_HOST=smtp.hostinger.com
LEARN_SMTP_PORT=465
LEARN_SMTP_USER=contact@opcode-labs.com
LEARN_SMTP_PASSWORD=the-mailbox-password
LEARN_TRAINER_EMAIL=you@example.com
```
- `LEARN_SMTP_PORT`: 465 (TLS from the start) or 587 (STARTTLS), as your provider says.
- `LEARN_TRAINER_EMAIL`: where new questions go (several: comma-separated). Without it: your admin account's email.
- Optional `LEARN_MAIL_FROM`: the sender address, if it isn't the login (`LEARN_SMTP_USER`).

Then:
```bash
sudo systemctl restart opcode-learn
sudo opcode-learn test-mail                # sends a test to LEARN_TRAINER_EMAIL, prints "sent" or the error
```
The file is readable only by root and the app (`root:learn`, mode 640); re-running the installer keeps it.
If a mail can't be sent, the question page says why (*email failed*) and has *Send the email again*.

## Status and logs
| What | Where |
|---|---|
| App | VPS$ `systemctl status opcode-learn` · `journalctl -u opcode-learn -f` |
| nginx | VPS$ `tail -f /var/log/nginx/learn.opcode-labs.com.{access,error}.log` |
| Video cache | VPS$ `sudo du -sh /var/cache/nginx/learn_media` (max 25 GB) |
| Media server | Pi$ `systemctl status learn-media` · `journalctl -u learn-media -f` |
| Pi firewall | Pi$ `sudo nft list table inet learn_media` |
| Certificate | VPS$ `sudo certbot certificates -d learn.opcode-labs.com` (auto-renews) |

"Courses are offline for a moment" on the site means the app can't reach the Pi. Check
that wg0 is up, `learn-media` is running and `/srv/drive/data` is mounted (pi_drive's docs cover the disk).

## Update the app
Edit in Git, run the tests (`tests/test_e2e.py`), copy (install.md step 2), then re-run
VPS$ `sudo bash ~/opcode_learn/vps/install.sh`. The database and config are kept.
For the Pi part: copy, then Pi$ `sudo bash ~/opcode_learn/pi/install.sh`.

## Backup
Everything except the videos is in one small file, `/var/lib/opcode-learn/learn.sqlite` (accounts, access, progress, questions):
```bash
sudo sqlite3 /var/lib/opcode-learn/learn.sqlite ".backup /root/learn-$(date +%F).sqlite"
```
It holds the TOTP key and the password hashes, so keep copies private.

## Lost phone / forgotten admin password
```bash
sudo opcode-learn new-totp you@example.com       # prints a new setup key, old one stops working
sudo opcode-learn set-password you@example.com   # hidden prompt
```

## Empty the video cache
VPS$ `sudo find /var/cache/nginx/learn_media -type f -delete`

This is safe at any time. The next viewers re-fetch from the Pi.

## Uninstall (videos and other sites untouched)
VPS:
```bash
sudo rm /etc/nginx/sites-enabled/learn.opcode-labs.com && sudo nginx -t && sudo systemctl reload nginx
sudo systemctl disable --now opcode-learn
sudo rm /etc/systemd/system/opcode-learn.service /usr/local/bin/opcode-learn && sudo systemctl daemon-reload
sudo rm -r /opt/opcode-learn /etc/opcode-learn /var/lib/opcode-learn /var/cache/nginx/learn_media   # deletes accounts
sudo certbot delete --cert-name learn.opcode-labs.com
```
Pi:
```bash
sudo systemctl disable --now learn-media learn-media-firewall
sudo rm /etc/systemd/system/learn-media*.service && sudo systemctl daemon-reload
sudo rm -r /opt/learn-media /etc/learn-media && sudo userdel learnmedia
```
