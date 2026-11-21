#!/usr/bin/env bash
# Check that every video of a course will play well in browsers. Read-only.
#   bash tools/check-videos.sh /srv/drive/data/Training_Opcode/linux_udemy
# Per file: OK, or why not (broken/unfinished upload, codec, index at the end = slow start).
set -uo pipefail
dir=${1:?usage: check-videos.sh COURSE_FOLDER}
bad=0
while IFS= read -r -d '' f; do
    rel=${f#"$dir"/}
    v=$(ffprobe -v error -select_streams v:0 -show_entries stream=codec_name -of csv=p=0 "$f" 2>/dev/null)
    if [[ -z $v ]]; then
        echo "BROKEN    $rel  (not readable: upload unfinished or file damaged)"; bad=$((bad + 1)); continue
    fi
    a=$(ffprobe -v error -select_streams a:0 -show_entries stream=codec_name -of csv=p=0 "$f" 2>/dev/null)
    first=$(ffprobe -v trace "$f" 2>&1 | grep -m1 -oE "type:'(moov|mdat)'")
    br=$(ffprobe -v error -show_entries format=bit_rate -of csv=p=0 "$f" 2>/dev/null)
    issues=()
    [[ $v == h264 ]] || issues+=("video $v, browsers need h264")
    [[ -z $a || $a == aac || $a == mp3 ]] || issues+=("audio $a, browsers need aac")
    [[ $first == "type:'moov'" ]] || issues+=("index at the end: slow start, fix with tools/web-mp4.sh")
    [[ ${br:-0} =~ ^[0-9]+$ && ${br:-0} -gt 6000000 ]] && issues+=("$((br / 1000000)) Mbit/s: heavy for the home uplink")
    if ((${#issues[@]})); then
        printf 'FIX       %s  (%s)\n' "$rel" "$(IFS=';'; echo "${issues[*]}")"; bad=$((bad + 1))
    else
        printf 'OK        %s  (%s Mbit/s)\n' "$rel" "$(awk -v b="${br:-0}" 'BEGIN{printf "%.1f", b/1e6}')"
    fi
done < <(find "$dir" -type f \( -iname '*.mp4' -o -iname '*.m4v' -o -iname '*.webm' \) -print0 | sort -z)
echo "---- $bad file(s) need attention"
