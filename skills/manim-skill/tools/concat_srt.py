#!/usr/bin/env python3
"""Concatenate SRT files based on concat.txt video order."""

import json, re, subprocess, sys
from pathlib import Path

def get_duration(path):
    r = subprocess.run(["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", path], capture_output=True, text=True)
    return float(json.loads(r.stdout).get("format", {}).get("duration", 0)) if r.returncode == 0 else 0.0

def srt_time(s):
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{int(h):02}:{int(m):02}:{int(sec):02},{int((sec % 1) * 1000):03}"

def main():
    # order.txt contains .mp4 paths (for ffmpeg concat). We can find corresponding .srt files
    # because Manim saves SRT files in the same location as videos with matching names.
    if len(sys.argv) < 2:
        sys.exit("Usage: concat_srt.py <order.txt> [output.srt]")

    order_file = Path(sys.argv[1])
    base_dir = order_file.parent
    output = Path(sys.argv[2]) if len(sys.argv) > 2 else base_dir / "final.srt"

    videos = []
    for line in order_file.read_text().splitlines():
        if m := re.match(r"file '(.+)'", line.strip()):
            videos.append(base_dir / m[1])

    entries, offset = [], 0.0
    for video in videos:
        srt = video.with_suffix(".srt")
        if srt.exists():
            for block in srt.read_text().strip().split("\n\n"):
                lines = block.split("\n")
                if len(lines) < 3: continue
                m = re.match(r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)", lines[1])
                if not m: continue
                start = int(m[1])*3600 + int(m[2])*60 + int(m[3]) + int(m[4])/1000 + offset
                end = int(m[5])*3600 + int(m[6])*60 + int(m[7]) + int(m[8])/1000 + offset
                text = "\n".join(lines[2:])
                entries.append(f"{len(entries)+1}\n{srt_time(start)} --> {srt_time(end)}\n{text}")
        offset += get_duration(video)

    output.write_text("\n\n".join(entries) + "\n" if entries else "")

if __name__ == "__main__":
    main()
