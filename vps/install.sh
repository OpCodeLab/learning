#!/usr/bin/env bash
# OpCode Learn, VPS side. Run as: sudo bash ~/opcode_learn/vps/install.sh   (idempotent)
# Touches only: user learn, /opt/opcode-learn, /etc/opcode-learn, /var/lib/opcode-learn,
# /var/cache/nginx/learn_media, opcode-learn.service, /usr/local/bin/opcode-learn and the
# nginx site learn.opcode-labs.com (+ its certificate). Other sites are not touched.
set -euo pipefail

DOMAIN=learn.opcode-labs.com
HERE=$(cd "$(dirname "$0")" && pwd)
SRC=$(dirname "$HERE")
step() { printf '\n==> %s\n' "$*"; }
die()  { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
[[ $EUID -eq 0 ]] || die "run with sudo"

step "Checks"
# "|| true": with pipefail a failed lookup would end the script silently instead of via die.
ip=$(getent hosts "$DOMAIN" | awk '{print $1}' | head -1 || true)
[[ -n $ip ]] || die "$DOMAIN has no DNS record yet (A record -> this VPS)"
echo "$DOMAIN -> $ip"
curl -s --max-time 5 http://10.8.3.3:8092/list >/dev/null \
    && echo "Pi media server: reachable" \
    || echo "WARNING: Pi media server 10.8.3.3:8092 not reachable (run pi/install.sh); the site will say 'offline'"

step "Service account 'learn' and files"
id learn &>/dev/null || useradd --system --user-group --no-create-home --home-dir /var/lib/opcode-learn \
    --shell /usr/sbin/nologin learn
install -d -m 755 /opt/opcode-learn
rm -rf /opt/opcode-learn/app.new
cp -r "$SRC/app" /opt/opcode-learn/app.new
find /opt/opcode-learn/app.new -name __pycache__ -prune -exec rm -rf {} +
chown -R root:root /opt/opcode-learn/app.new
chmod -R u=rwX,go=rX /opt/opcode-learn/app.new
rm -rf /opt/opcode-learn/app.old
[[ -d /opt/opcode-learn/app ]] && mv /opt/opcode-learn/app /opt/opcode-learn/app.old
mv /opt/opcode-learn/app.new /opt/opcode-learn/app

step "Python environment (pinned packages)"
[[ -x /opt/opcode-learn/venv/bin/python ]] || python3 -m venv /opt/opcode-learn/venv
/opt/opcode-learn/venv/bin/pip install --quiet --disable-pip-version-check -r /opt/opcode-learn/app/requirements.txt
/opt/opcode-learn/venv/bin/python -c "import starlette, uvicorn, jinja2, yaml; print('starlette', starlette.__version__)"

step "Config (/etc/opcode-learn/learn.env)"
install -d -m 750 -g learn /etc/opcode-learn
if [[ ! -s /etc/opcode-learn/learn.env ]]; then
    cat > /etc/opcode-learn/learn.env <<EOF
LEARN_DB=/var/lib/opcode-learn/learn.sqlite
LEARN_MEDIA_URL=http://10.8.3.3:8092
LEARN_BASE_URL=https://$DOMAIN
LEARN_SITE_NAME=OpCode Learn
EOF
fi
chown root:learn /etc/opcode-learn/learn.env
chmod 640 /etc/opcode-learn/learn.env
install -m 755 "$HERE/opcode-learn" /usr/local/bin/opcode-learn

step "Service"
install -m 644 "$HERE/systemd/opcode-learn.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable opcode-learn.service
systemctl restart opcode-learn.service
for _ in $(seq 20); do
    curl -s --max-time 2 http://127.0.0.1:8095/healthz | grep -q ok && break
    sleep 1
done
curl -s --max-time 2 http://127.0.0.1:8095/healthz | grep -q ok || die "app not answering; see: journalctl -u opcode-learn -n 50"
echo "app answering on 127.0.0.1:8095"

step "nginx site and certificate"
install -d -m 755 /var/www/letsencrypt
install -d -m 755 /var/cache/nginx
install -d -m 700 -o www-data -g www-data /var/cache/nginx/learn_media
apply_site() {
    install -m 644 "$1" /etc/nginx/sites-available/$DOMAIN
    ln -sf /etc/nginx/sites-available/$DOMAIN /etc/nginx/sites-enabled/$DOMAIN
    if ! nginx -t; then
        rm -f /etc/nginx/sites-enabled/$DOMAIN
        die "nginx -t failed; site disabled again, other sites unaffected"
    fi
    systemctl reload nginx
}
if [[ ! -s /etc/letsencrypt/live/$DOMAIN/fullchain.pem ]]; then
    apply_site "$HERE/nginx/$DOMAIN.acme.conf"
    certbot certonly --webroot -w /var/www/letsencrypt -d $DOMAIN --non-interactive --keep-until-expiring
fi
apply_site "$HERE/nginx/$DOMAIN.conf"

for i in $(seq 10); do
    code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 https://$DOMAIN/login || true)
    [[ $code == 200 ]] && break
    sleep 1
done
echo "https://$DOMAIN/login -> HTTP $code"
[[ $code == 200 ]] || die "site not answering 200"
rm -rf /opt/opcode-learn/app.old

cat <<EOF

Done. First time only, create your admin account (password prompt + TOTP key):
  sudo opcode-learn create-admin you@example.com
EOF
