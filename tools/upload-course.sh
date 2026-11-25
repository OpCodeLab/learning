#!/usr/bin/env bash
# Upload (or update) one course folder from the PC to the course server.
#
#   bash tools/upload-course.sh "/mnt/d/Training/linux/udemy" linux_udemy
#   bash tools/upload-course.sh "/mnt/d/Training/linux/udemy" linux_udemy --dry-run   # show, change nothing
#
# - Sends only new or changed files (rsync); an interrupted upload resumes where it stopped.
# - Files being uploaded stay hidden from students until complete (rsync writes hidden temp files).
# - Never deletes anything on the server. To remove a lesson: delete it there by hand (docs/content.md).
# - Leaves out notes and system files: *.md, desktop.ini, Thumbs.db, .*, *.tmp, *.part.
# - Server: $LEARN_SERVER, default ubuntu@178.32.39.41 (the OVH VPS).
set -euo pipefail
SERVER=${LEARN_SERVER:-ubuntu@178.32.39.41}
SRC=${1:-}; NAME=${2:-}
shift 2 2>/dev/null || true
[[ -d $SRC && -n $NAME ]] || { sed -n '2,12p' "$0"; exit 1; }
[[ $NAME =~ ^[A-Za-z0-9_.-]+$ ]] || { echo "course name: letters, digits, _ . - only (it is the folder name on the server)"; exit 1; }
[[ -f $SRC/course.yaml ]] || echo "note: no course.yaml in $SRC: the site will not list it as a course until you add one"

echo "Uploading $SRC -> $SERVER:/srv/learn/courses/$NAME/"
rsync -rt --partial-dir=.rsync-partial --info=progress2,stats1 \
      --chmod=D2750,F640 \
      --exclude='*.md' --exclude='desktop.ini' --exclude='Thumbs.db' --exclude='.*' \
      --exclude='*.tmp' --exclude='*.part' \
      "$@" "$SRC/" "$SERVER:/srv/learn/courses/$NAME/"
# rsync doesn't keep the folder's group (learn) on new sub-folders: give everything to the site.
ssh "$SERVER" "chgrp -R learn '/srv/learn/courses/$NAME' && find '/srv/learn/courses/$NAME' -type d -exec chmod 2750 {} + && find '/srv/learn/courses/$NAME' -type f -exec chmod 640 {} +" \
    || echo "WARNING: could not set the group 'learn': run on the server: sudo bash ~/opcode_learn/vps/install.sh"
echo "Done. The site picks up the changes within a minute (Courses page: 'Re-read the disk' to see them now)."
