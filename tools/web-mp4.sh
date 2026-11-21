#!/usr/bin/env bash
# Make videos play in every browser: MP4 with H.264 video + AAC audio, "faststart"
# (the index at the start, so playback and seeking begin immediately).
#   bash tools/web-mp4.sh "01 Intro.mkv" "02 Shell.mov" ...   -> "01 Intro.mp4", ...
# Already H.264/AAC: just remuxed (seconds, no quality loss). Otherwise re-encoded (slow).
# Runs anywhere ffmpeg is installed (the Pi has it, WSL: sudo apt install ffmpeg).
set -euo pipefail
command -v ffmpeg >/dev/null || { echo "ffmpeg not installed" >&2; exit 1; }

for in in "$@"; do
    out="${in%.*}.mp4"
    [[ $in == "$out" ]] && out="${in%.*}.web.mp4"
    v=$(ffprobe -v error -select_streams v:0 -show_entries stream=codec_name -of csv=p=0 "$in" || true)
    a=$(ffprobe -v error -select_streams a:0 -show_entries stream=codec_name -of csv=p=0 "$in" || true)
    if [[ $v == h264 && ( $a == aac || -z $a ) ]]; then
        echo "remux  $in -> $out"
        ffmpeg -nostdin -loglevel error -y -i "$in" -map 0:v:0 -map '0:a:0?' -c copy -movflags +faststart "$out"
    else
        echo "encode $in ($v/$a) -> $out"
        # CRF 23 + max 1080p: a good screencast at ~1-3 Mbit/s, kind to the home uplink.
        ffmpeg -nostdin -loglevel error -stats -y -i "$in" -map 0:v:0 -map '0:a:0?' \
            -vf "scale='min(1920,iw)':-2" -c:v libx264 -preset medium -crf 23 -pix_fmt yuv420p \
            -c:a aac -b:a 128k -movflags +faststart "$out"
    fi
done
