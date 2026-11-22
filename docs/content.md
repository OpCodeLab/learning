# Publishing a course

You manage content with **files.opcode-labs.com**, the way you already do. The course site
reads the folders and updates itself within a minute (or at once: Courses → *Re-read the disk*).

## Folder layout
Courses live in `DATA/Training_Opcode`. A folder becomes a course **only when it contains a
`course.yaml`**, so other folders there (slides, archives) stay private.

```
DATA/Training_Opcode/
  linux_udemy/
    course.yaml                  title and description
    cover.jpg                    optional, 16:9 image for the course card
    01 Getting started/          a section
      01 Welcome.mp4             lesson 1
      01 Welcome.pdf             attachment of lesson 1 (same leading number)
      02 Install Ubuntu.mp4      lesson 2
      install-notes.pdf          section resource (no number)
    02 Shell basics/
      01 Navigating.mp4
      02 Pipes and redirection.mp4
      02 pipes-lab.zip           attachment of lesson 2
```

- **Order** comes from the leading numbers (`01`, `02`, … `10` sorts after `9`). The numbers
  and separators (`01 `, `01 - `, `01_`, `01.`) are hidden in titles.
- The Udemy-style names `S1_L01_fork-and-wait.mp4` work too: the lesson number is 1, and the
  title becomes "fork and wait". In names without spaces, `-` and `_` become spaces and `-s` becomes `'s`.
- Hidden too: unfinished uploads (`.tmp`, `.part`), which appear once the upload completes.
- **Sections** are the sub-folders. Videos directly in the course folder form one section, "Lessons".
- **Attachments**: any non-video file whose number matches a lesson in the same folder
  (`02 pipes-lab.zip` → lesson `02 …`). Files without a matching number are section resources.
- Hidden: names starting with `.` or `$`, `System Volume Information`, `Thumbs.db`, `desktop.ini`.
- Renaming a video file is fine, but students lose that lesson's progress, because progress is tied to the file path.

## course.yaml
```yaml
title: Linux from scratch
description: |
  Shell, files, permissions and processes, step by step.
  For beginners; no Linux experience needed.
```
Both keys are optional (without `title`, the folder name is used). Create the file in
files.opcode-labs.com with *New file*, or upload it.

To set a nicer title for some lessons, add `titles:` with the file name (with or without `.mp4`):
```yaml
titles:
  S1_L01_fork-and-wait-parent-and-child-processes: "fork() and wait(): parent and child processes"
  S4_L27_I-O-buffering-stdio-vs-kernel-buffer-cache: "I/O buffering: stdio vs the kernel buffer cache"
```
Put titles containing `:` in quotes.

## Check the videos
On the Pi (read-only, takes a minute for a big course):
```bash
bash ~/opcode_learn/tools/check-videos.sh /srv/drive/data/Training_Opcode/linux_udemy
```
For each video it prints `OK`, or why not: `BROKEN` (an unfinished or damaged upload: upload it again), the
wrong codec, an index at the end of the file (slow start), or a bitrate too high for the home uplink.

## Lesson lengths
The site shows each lesson's length ("▶ 9 min") and each section's total, like Udemy. It reads them
from the video file's header (a few KB per file, over the Pi link) the first time it sees a file, and
again only if the file changes. New uploads get their length within a minute. A video whose header
can't be read (usually an upload cut short) gets a warning on **Courses** (admin): re-upload it.

## Video format
Browsers play **MP4 with H.264 video and AAC audio**. Most screen recorders (OBS, Camtasia,
Udemy exports) already produce that. `.mkv`, `.avi`, `.mov`, … are hidden from students
and listed as a warning on the admin *Courses* page.

To convert, or to fix a slow start (the index at the end of the file), use:
```bash
bash tools/web-mp4.sh "03 Permissions.mkv"
```
On the Pi the course folder is `/srv/drive/data/Training_Opcode`.

**Size vs your home uplink.** Each viewer of a video that isn't cached on the VPS yet
uses roughly the video's bitrate of your upload. 1080p screencasts at CRF 23 are typically
1–3 Mbit/s, so they're fine. Avoid 20+ Mbit/s camera originals: convert them first.

## Replacing a video
Upload the new file under the same name. The site sees a new size and date, so the VPS
cache treats it as a new file; the old cached copy expires by itself.
