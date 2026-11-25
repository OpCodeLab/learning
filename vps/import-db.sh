#!/usr/bin/env bash
# Put a copy of the OpCode Learn database (accounts, access, progress) in place on this server.
# Run as: sudo bash ~/opcode_learn/vps/import-db.sh /tmp/learn-move.sqlite
# The current database, if any, is kept as learn.sqlite.before-import-<date>.
set -euo pipefail
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
[[ $EUID -eq 0 ]] || die "run with sudo"
NEW=${1:-}
[[ -s $NEW ]] || die "usage: sudo bash import-db.sh /path/to/learn-copy.sqlite"
DB=/var/lib/opcode-learn/learn.sqlite

[[ $(sqlite3 "$NEW" "PRAGMA integrity_check;") == ok ]] || die "$NEW is damaged (integrity check failed)"
users=$(sqlite3 "$NEW" "SELECT COUNT(*) FROM users;") || die "$NEW is not an OpCode Learn database"
echo "copy OK: $users accounts, $(sqlite3 "$NEW" "SELECT COUNT(*) FROM enrollments;") course accesses," \
     "$(sqlite3 "$NEW" "SELECT COUNT(*) FROM progress;") progress rows"

systemctl stop opcode-learn.service
install -d -m 700 -o learn -g learn /var/lib/opcode-learn
if [[ -e $DB ]]; then
    mv "$DB" "$DB.before-import-$(date +%F-%H%M)"
    rm -f "$DB-wal" "$DB-shm"
fi
install -m 600 -o learn -g learn "$NEW" "$DB"
systemctl start opcode-learn.service
for _ in $(seq 20); do
    curl -s --max-time 2 http://127.0.0.1:8095/healthz | grep -q ok && break
    sleep 1
done
curl -s --max-time 2 http://127.0.0.1:8095/healthz | grep -q ok || die "app not answering; see: journalctl -u opcode-learn -n 50"
shred -u "$NEW" 2>/dev/null || rm -f "$NEW"     # the copy holds password hashes: don't leave it in /tmp
echo "database in place, site running; the temporary copy was deleted"
