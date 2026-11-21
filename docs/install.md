# First install

Shorthand:
- **Pi$** `wsl -e ssh -t -J mehdi@187.126.22.239 ubuntu@10.8.3.3 "<cmd>"`
- **VPS$** `wsl -e ssh -t mehdi@187.126.22.239 "<cmd>"`

## 1. DNS
At your DNS provider (where `files` was added), add an **A record**: `learn` → `187.126.22.239`.
Check it from the PC:
```bash
nslookup learn.opcode-labs.com
```

## 2. Copy the repo to the Pi and the VPS
From `D:\opcode_learn`. Each command replaces only the `~/opcode_learn` copy of the
install files, nothing else.

To the Pi:
```bash
wsl -e bash -c "cd /mnt/d/opcode_learn && tar czf - pi | ssh -J mehdi@187.126.22.239 ubuntu@10.8.3.3 'rm -rf ~/opcode_learn && mkdir ~/opcode_learn && tar xzf - -C ~/opcode_learn'"
```
To the VPS:
```bash
wsl -e bash -c "cd /mnt/d/opcode_learn && tar czf - app vps | ssh mehdi@187.126.22.239 'rm -rf ~/opcode_learn && mkdir ~/opcode_learn && tar xzf - -C ~/opcode_learn'"
```

## 3. Pi: media server
Pi$ `sudo bash ~/opcode_learn/pi/install.sh`

It ends with the JSON list of the folders in `Training_Opcode`.

## 4. VPS: app, nginx and certificate
VPS$ `sudo bash ~/opcode_learn/vps/install.sh`

It checks DNS and the Pi, installs the app and its pinned Python packages, gets the
Let's Encrypt certificate (webroot, like the other sites), and ends with
`https://learn.opcode-labs.com/login -> HTTP 200`.

## 5. Your admin account
VPS$ `sudo opcode-learn create-admin you@example.com`

It asks for a password twice (hidden, min 14 characters) and prints a **setup key**. In your
authenticator app choose *Add account → Enter a setup key*, time-based. Then sign in at
https://learn.opcode-labs.com: email, password, 6-digit code.

## 6. First course and checks
1. In files.opcode-labs.com, add `course.yaml` to `DATA/Training_Opcode/linux_udemy` (see
   [content.md](content.md)) and upload one or two videos into section folders.
2. In the course site, open **Courses**: the course shows its sections and lessons, with no warnings.
3. Play a lesson as admin. The second time a part is played, the VPS serves it from its cache:
   VPS$ `tail -n 5 /var/log/nginx/learn.opcode-labs.com.access.log`
4. **Students → New student**: use a second email of yours, tick the course, copy the invite link,
   open it in a private window, set a password and watch. Check that only that course is visible.
5. Set that student's end date to yesterday: the course disappears for them at once.
