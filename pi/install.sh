#!/usr/bin/env bash
# OpCode Learn, Pi side: read-only media server for the VPS.
# Run as: sudo bash ~/opcode_learn/pi/install.sh   (idempotent)
# Touches only: /opt/learn-media, /etc/learn-media, user learnmedia, its two units.
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
step() { printf '\n==> %s\n' "$*"; }
die()  { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
[[ $EUID -eq 0 ]] || die "run with sudo"

getent group drive >/dev/null || die "group 'drive' missing: install pi_drive first"
[[ -d /srv/drive/data/Training_Opcode ]] || die "/srv/drive/data/Training_Opcode not found (DATA mounted?)"

step "Service account 'learnmedia' (group drive: read access to the disk)"
id learnmedia &>/dev/null || useradd --system --gid drive --no-create-home \
    --home-dir /nonexistent --shell /usr/sbin/nologin learnmedia

step "Files"
install -d -m 755 /opt/learn-media /etc/learn-media
install -m 644 "$HERE/media_server.py" /opt/learn-media/media_server.py
install -m 644 "$HERE/learn-media.nft" /etc/learn-media/learn-media.nft
install -m 644 "$HERE/systemd/learn-media.service" "$HERE/systemd/learn-media-firewall.service" /etc/systemd/system/

step "Firewall table inet learn_media and the service"
systemctl daemon-reload
systemctl enable learn-media-firewall.service learn-media.service
systemctl restart learn-media-firewall.service
systemctl restart learn-media.service

for _ in $(seq 20); do
    ss -ltn 'sport = :8092' | grep -q 10.8.3.3:8092 && break
    sleep 1
done
ss -ltn 'sport = :8092' | grep -q 10.8.3.3:8092 || die "not listening; see: journalctl -u learn-media -n 30"
echo "learn-media listening on 10.8.3.3:8092"
curl -s --max-time 5 http://10.8.3.3:8092/list; echo
