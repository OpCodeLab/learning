#!/usr/bin/env bash
# OpCode Learn, server side (OVH VPS, courses on the server's own disk).
# Run as: sudo bash ~/opcode_learn/vps/install.sh   (idempotent: run again to update)
#
# Touches only: packages nginx/certbot/python3-venv/sqlite3/rsync, user learn, /opt/opcode-learn,
# /etc/opcode-learn, /var/lib/opcode-learn, /srv/learn/courses, opcode-learn(.service, -files.service),
# /usr/local/bin/opcode-learn, the nginx site learn.opcode-labs.com (+ its certificate) and, if ufw
# is on, the web ports 80/443.
#
# Certificate: obtained only once learn.opcode-labs.com points to this server. Before the DNS
# switch the script installs everything, then stops with a message; run it again after the switch.
set -euo pipefail

DOMAIN=learn.opcode-labs.com
COURSES=/srv/learn/courses
FILES_PORT=8096
HERE=$(cd "$(dirname "$0")" && pwd)
SRC=$(dirname "$HERE")
OWNER=${SUDO_USER:-ubuntu}          # the account that uploads courses (rsync from the PC)
step() { printf '\n==> %s\n' "$*"; }
die()  { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
[[ $EUID -eq 0 ]] || die "run with sudo"
[[ -f $SRC/pi/media_server.py ]] || die "copy the pi/ folder too (see docs/install.md)"

step "Packages"
need=()
for p in nginx certbot python3-venv sqlite3 rsync; do
    dpkg -s "$p" &>/dev/null || need+=("$p")
done
if (( ${#need[@]} )); then
    apt-get update -q
    DEBIAN_FRONTEND=noninteractive apt-get install -y -q "${need[@]}"
fi
echo "ok: nginx certbot python3-venv sqlite3 rsync"

step "Service account 'learn' and course folder"
id learn &>/dev/null || useradd --system --user-group --no-create-home --home-dir /var/lib/opcode-learn \
    --shell /usr/sbin/nologin learn
# nginx (www-data) reads the course files to send them: group learn, read-only.
id -nG www-data | grep -qw learn || usermod -aG learn www-data
install -d -m 755 /srv/learn
# Owner = the uploading account; group learn can read; setgid keeps new files in group learn.
install -d -m 2750 -o "$OWNER" -g learn "$COURSES"
echo "$COURSES  (upload as $OWNER, read by the site)"

step "App files"
install -d -m 755 /opt/opcode-learn
rm -rf /opt/opcode-learn/app.new
cp -r "$SRC/app" /opt/opcode-learn/app.new
find /opt/opcode-learn/app.new -name __pycache__ -prune -exec rm -rf {} +
chown -R root:root /opt/opcode-learn/app.new
chmod -R u=rwX,go=rX /opt/opcode-learn/app.new
rm -rf /opt/opcode-learn/app.old
[[ -d /opt/opcode-learn/app ]] && mv /opt/opcode-learn/app /opt/opcode-learn/app.old
mv /opt/opcode-learn/app.new /opt/opcode-learn/app
install -m 644 "$SRC/pi/media_server.py" /opt/opcode-learn/media_server.py

step "Python environment (pinned packages)"
[[ -x /opt/opcode-learn/venv/bin/python ]] || python3 -m venv /opt/opcode-learn/venv
/opt/opcode-learn/venv/bin/pip install --quiet --disable-pip-version-check -r /opt/opcode-learn/app/requirements.txt
/opt/opcode-learn/venv/bin/python -c "import starlette, uvicorn, jinja2, yaml; print('starlette', starlette.__version__)"

step "Config (/etc/opcode-learn/learn.env)"
install -d -m 750 -g learn /etc/opcode-learn
if [[ ! -s /etc/opcode-learn/learn.env ]]; then
    cat > /etc/opcode-learn/learn.env <<EOF
LEARN_DB=/var/lib/opcode-learn/learn.sqlite
LEARN_MEDIA_URL=http://127.0.0.1:$FILES_PORT
LEARN_BASE_URL=https://$DOMAIN
LEARN_SITE_NAME=OpCode Learn
EOF
fi
# Older installs pointed at the Pi: the courses are on this server now.
sed -i "s|^LEARN_MEDIA_URL=.*|LEARN_MEDIA_URL=http://127.0.0.1:$FILES_PORT|" /etc/opcode-learn/learn.env
chown root:learn /etc/opcode-learn/learn.env
chmod 640 /etc/opcode-learn/learn.env
install -m 755 "$HERE/opcode-learn" /usr/local/bin/opcode-learn

step "Services"
install -m 644 "$HERE/systemd/opcode-learn.service" "$HERE/systemd/opcode-learn-files.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --quiet opcode-learn-files.service opcode-learn.service
systemctl restart opcode-learn-files.service opcode-learn.service
for _ in $(seq 20); do
    curl -s --max-time 2 http://127.0.0.1:8095/healthz | grep -q ok && break
    sleep 1
done
curl -s --max-time 2 http://127.0.0.1:8095/healthz | grep -q ok || die "app not answering; see: journalctl -u opcode-learn -n 50"
curl -s --max-time 2 http://127.0.0.1:$FILES_PORT/list >/dev/null \
    || die "file lister not answering; see: journalctl -u opcode-learn-files -n 50"
echo "app on 127.0.0.1:8095, file lister on 127.0.0.1:$FILES_PORT"
echo "courses found: $(curl -s http://127.0.0.1:$FILES_PORT/list)"

step "Firewall"
if command -v ufw >/dev/null && ufw status | grep -q "Status: active"; then
    ufw allow 80/tcp >/dev/null
    ufw allow 443/tcp >/dev/null
    echo "ufw: ports 80 and 443 open (SSH rules unchanged)"
else
    echo "ufw not active: nothing to open"
fi

step "nginx site"
install -d -m 755 /var/www/letsencrypt
rm -rf /var/cache/nginx/learn_media        # the old Pi video cache is not used any more
apply_site() {
    install -m 644 "$1" /etc/nginx/sites-available/$DOMAIN
    ln -sf /etc/nginx/sites-available/$DOMAIN /etc/nginx/sites-enabled/$DOMAIN
    if ! nginx -t; then
        rm -f /etc/nginx/sites-enabled/$DOMAIN
        die "nginx -t failed; site disabled again, other sites unaffected"
    fi
    systemctl reload nginx
}
systemctl enable --quiet --now nginx

if [[ ! -s /etc/letsencrypt/live/$DOMAIN/fullchain.pem ]]; then
    me=$(ip -4 route get 1.1.1.1 | awk '{for (i = 1; i < NF; i++) if ($i == "src") print $(i + 1)}')
    dns=$(getent ahostsv4 "$DOMAIN" | awk '{print $1}' | head -1 || true)
    apply_site "$HERE/nginx/$DOMAIN.acme.conf"
    if [[ $dns != "$me" ]]; then
        cat <<EOF

Everything is installed and running, except HTTPS:
$DOMAIN still points to ${dns:-nothing}, this server is $me.
Next: copy the database and the courses (docs/move-to-ovh.md), change the DNS A record
of learn to $me, wait until 'getent hosts $DOMAIN' shows it here, then run this script again.
EOF
        exit 0
    fi
    if [[ -d /etc/letsencrypt/accounts ]]; then
        certbot certonly --webroot -w /var/www/letsencrypt -d $DOMAIN --non-interactive --keep-until-expiring
    else
        # First certificate on this server: certbot asks for your email and the Let's Encrypt terms.
        certbot certonly --webroot -w /var/www/letsencrypt -d $DOMAIN --keep-until-expiring
    fi
fi
apply_site "$HERE/nginx/$DOMAIN.conf"

for i in $(seq 10); do
    code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 --resolve $DOMAIN:443:127.0.0.1 https://$DOMAIN/login || true)
    [[ $code == 200 ]] && break
    sleep 1
done
echo "https://$DOMAIN/login -> HTTP $code"
[[ $code == 200 ]] || die "site not answering 200"
rm -rf /opt/opcode-learn/app.old

cat <<EOF

Done. If this server has no admin account yet (new database), create one:
  sudo opcode-learn create-admin you@example.com
EOF
