#!/usr/bin/env python3
"""
Video Viewer - Local viewer for reviewing Manim videos with chapter navigation.

Usage:
    python video_viewer.py <final_video.mp4> <scene1.mp4> <scene2.mp4> ...
"""

import argparse
import http.server
import json
import os
import re
import shutil
import socketserver
import subprocess
import sys
import tempfile
import threading
import webbrowser
from pathlib import Path
from urllib.parse import unquote


def get_video_duration(video_path: str) -> float:
    """Get video duration in seconds using ffprobe."""
    cmd = [
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_format", str(video_path)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Warning: Could not get duration for {video_path}")
        return 0.0
    data = json.loads(result.stdout)
    return float(data.get("format", {}).get("duration", 0))


def extract_thumbnail(video_path: str, output_path: str, time_offset: float = 1.0) -> bool:
    """Extract a thumbnail from video at given time offset."""
    cmd = [
        "ffmpeg", "-y", "-ss", str(time_offset), "-i", str(video_path),
        "-vframes", "1", "-q:v", "2", str(output_path)
    ]
    result = subprocess.run(cmd, capture_output=True)
    return result.returncode == 0


def extract_scene_name(video_path: str) -> str:
    """Extract scene name from video filename."""
    name = Path(video_path).stem
    name = re.sub(r"_\d{4}x\d{4}$", "", name)
    return name


def build_chapters(scene_videos: list[str], temp_dir: str) -> list[dict]:
    """Build chapter metadata from scene video paths."""
    chapters = []
    current_time = 0.0

    for i, video_path in enumerate(scene_videos):
        if not os.path.exists(video_path):
            print(f"Warning: Video not found: {video_path}")
            continue

        scene_name = extract_scene_name(video_path)
        duration = get_video_duration(video_path)

        thumb_name = f"thumb_{i}.jpg"
        thumb_path = os.path.join(temp_dir, thumb_name)
        thumb_time = min(1.0, duration / 2)
        extract_thumbnail(video_path, thumb_path, thumb_time)

        chapters.append({
            "index": i,
            "name": scene_name,
            "start": current_time,
            "duration": duration,
            "thumbnail": thumb_name
        })

        current_time += duration

    return chapters


class ViewerHandler(http.server.SimpleHTTPRequestHandler):
    """Custom handler for serving viewer files."""

    def __init__(self, *args, video_path: str, chapters: list, temp_dir: str, **kwargs):
        self.video_path = video_path
        self.chapters = chapters
        self.temp_dir = temp_dir
        super().__init__(*args, **kwargs)

    def do_GET(self):
        path = unquote(self.path)

        if path == "/" or path == "/index.html":
            self.serve_viewer_html()
        elif path == "/video.mp4":
            self.serve_file(self.video_path, "video/mp4")
        elif path == "/chapters.json":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(self.chapters).encode())
        elif path.startswith("/thumb_"):
            thumb_path = os.path.join(self.temp_dir, path[1:])
            if os.path.exists(thumb_path):
                self.serve_file(thumb_path, "image/jpeg")
            else:
                self.send_error(404)
        else:
            self.send_error(404)

    def serve_file(self, file_path: str, content_type: str):
        """Serve a file with proper headers for video streaming."""
        try:
            file_size = os.path.getsize(file_path)

            range_header = self.headers.get("Range")
            if range_header:
                range_match = re.match(r"bytes=(\d+)-(\d*)", range_header)
                if range_match:
                    start = int(range_match.group(1))
                    end = int(range_match.group(2)) if range_match.group(2) else file_size - 1

                    self.send_response(206)
                    self.send_header("Content-Type", content_type)
                    self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
                    self.send_header("Content-Length", str(end - start + 1))
                    self.send_header("Accept-Ranges", "bytes")
                    self.end_headers()

                    with open(file_path, "rb") as f:
                        f.seek(start)
                        self.wfile.write(f.read(end - start + 1))
                    return

            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(file_size))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()

            with open(file_path, "rb") as f:
                shutil.copyfileobj(f, self.wfile)

        except (BrokenPipeError, ConnectionResetError):
            pass  # Browser canceled request (normal during seeking)
        except Exception as e:
            print(f"Error serving file: {e}")

    def serve_viewer_html(self):
        """Serve the viewer HTML page."""
        html = get_viewer_html()
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(html)))
        self.end_headers()
        self.wfile.write(html.encode())

    def log_message(self, format, *args):
        pass


def get_viewer_html() -> str:
    """Return the viewer HTML with embedded CSS and JS."""
    return '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Manim Video Viewer</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: "Roboto", Arial, sans-serif; background: #0f0f0f; color: #fff; height: 100vh; overflow: hidden; }
        .container { display: flex; height: 100vh; gap: 24px; padding: 24px; }
        .video-section { flex: 1; min-width: 0; }
        .video-wrapper { height: 100%; background: #000; border-radius: 12px; overflow: hidden; display: flex; flex-direction: column; position: relative; }
        video { flex: 1; width: 100%; object-fit: contain; cursor: pointer; }

        /* Progress bar */
        .progress-bar { position: absolute; bottom: 40px; left: 12px; right: 12px; height: 20px; cursor: pointer; z-index: 10; display: flex; align-items: center; }
        .progress-track { width: 100%; height: 3px; background: #0f0f0f; display: flex; gap: 3px; border-radius: 2px; overflow: hidden; transition: height 0.1s; }
        .progress-bar:hover .progress-track { height: 5px; }
        .chapter-segment { height: 100%; background: rgba(255,255,255,0.3); }
        .chapter-segment-fill { height: 100%; background: #f00; width: 0; }
        .progress-dot { position: absolute; top: 50%; width: 13px; height: 13px; background: #f00; border-radius: 50%; transform: translateY(-50%) scale(0); transition: transform 0.1s; pointer-events: none; }
        .progress-bar:hover .progress-dot, .progress-bar.dragging .progress-dot { transform: translateY(-50%) scale(1); }

        /* Controls */
        .controls { display: flex; align-items: center; gap: 8px; padding: 8px 12px; background: linear-gradient(transparent, rgba(0,0,0,0.9)); position: absolute; bottom: 0; left: 0; right: 0; }
        .play-btn { background: transparent; border: none; color: #fff; width: 40px; height: 40px; cursor: pointer; display: flex; align-items: center; justify-content: center; border-radius: 50%; }
        .play-btn:hover { background: rgba(255,255,255,0.1); }
        .play-btn svg { width: 24px; height: 24px; fill: #fff; }
        .time { font-size: 13px; margin-left: 4px; }
        .time .sep { color: #aaa; margin: 0 4px; }
        .copy-btn { background: #238636; border: none; color: #fff; padding: 4px 10px; border-radius: 4px; cursor: pointer; font-size: 12px; margin: 0 8px; }
        .copy-btn:hover { background: #2ea043; }
        .copy-btn.copied { background: #1f6feb; }
        .scene-name { font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 300px; }
        .spacer { flex: 1; }

        /* Speed menu */
        .speed-wrap { position: relative; }
        .speed-btn { background: transparent; border: none; color: #fff; padding: 6px 12px; cursor: pointer; font-size: 13px; }
        .speed-btn:hover { background: rgba(255,255,255,0.1); }
        .speed-menu { position: absolute; bottom: 100%; right: 0; background: #212121; border-radius: 8px; padding: 8px 0; min-width: 120px; display: none; box-shadow: 0 4px 16px rgba(0,0,0,0.5); margin-bottom: 8px; }
        .speed-menu.open { display: block; }
        .speed-opt { padding: 8px 16px; cursor: pointer; font-size: 14px; }
        .speed-opt:hover { background: rgba(255,255,255,0.1); }
        .speed-opt::before { content: ''; display: inline-block; width: 20px; }
        .speed-opt.active::before { content: '✓'; margin-right: 4px; width: auto; }

        /* Chapters sidebar */
        .chapters { width: 360px; display: flex; flex-direction: column; overflow: hidden; }
        .chapters h3 { font-size: 16px; font-weight: 500; padding: 12px 0; border-bottom: 1px solid #3f3f3f; margin-bottom: 12px; }
        .chapter-list { flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 8px; }
        .chapter-list::-webkit-scrollbar { width: 8px; }
        .chapter-list::-webkit-scrollbar-thumb { background: #3f3f3f; border-radius: 4px; }
        .chapter { display: flex; gap: 12px; padding: 8px; border-radius: 8px; cursor: pointer; }
        .chapter:hover, .chapter.active { background: #272727; }
        .chapter.active img { border: 2px solid #fff; }
        .chapter img { width: 120px; height: 68px; background: #272727; border-radius: 8px; object-fit: cover; border: 2px solid transparent; }
        .chapter-info { flex: 1; min-width: 0; display: flex; flex-direction: column; justify-content: center; gap: 4px; }
        .chapter-info .name { font-size: 14px; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .chapter-info .time { font-size: 12px; color: #aaa; }
        .shortcuts { font-size: 12px; color: #aaa; padding: 12px 0; border-top: 1px solid #3f3f3f; margin-top: 12px; line-height: 1.8; }
        .shortcuts kbd { background: #272727; padding: 3px 8px; border-radius: 4px; font-family: inherit; font-size: 11px; margin-right: 4px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="video-section">
            <div class="video-wrapper">
                <video id="video" src="/video.mp4"></video>
                <div class="progress-bar" id="progressBar">
                    <div class="progress-track" id="progressTrack"></div>
                    <div class="progress-dot" id="progressDot"></div>
                </div>
                <div class="controls">
                    <button class="play-btn" id="playBtn">
                        <svg id="iconPlay" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
                        <svg id="iconPause" viewBox="0 0 24 24" style="display:none"><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/></svg>
                        <svg id="iconReplay" viewBox="0 0 24 24" style="display:none"><path d="M12 5V1L7 6l5 5V7c3.31 0 6 2.69 6 6s-2.69 6-6 6-6-2.69-6-6H4c0 4.42 3.58 8 8 8s8-3.58 8-8-3.58-8-8-8z"/></svg>
                    </button>
                    <div class="time"><span id="curTime">0:00</span><span class="sep">/</span><span id="durTime">0:00</span></div>
                    <button class="copy-btn" id="copyBtn">Copy</button>
                    <div class="scene-name" id="sceneName">-</div>
                    <div class="spacer"></div>
                    <div class="speed-wrap">
                        <button class="speed-btn" id="speedBtn">1x</button>
                        <div class="speed-menu" id="speedMenu"></div>
                    </div>
                </div>
            </div>
        </div>
        <div class="chapters">
            <h3>Chapters</h3>
            <div class="chapter-list" id="chapterList"></div>
            <div class="shortcuts"><kbd>Space</kbd> Play/Pause <kbd>←</kbd><kbd>→</kbd> 5 sec <kbd>C</kbd> Copy timestamp</div>
        </div>
    </div>
<script>
const $ = id => document.getElementById(id);
const video = $('video'), progressBar = $('progressBar'), progressTrack = $('progressTrack'), progressDot = $('progressDot');
const playBtn = $('playBtn'), iconPlay = $('iconPlay'), iconPause = $('iconPause'), iconReplay = $('iconReplay');
const curTime = $('curTime'), durTime = $('durTime'), sceneName = $('sceneName');
const copyBtn = $('copyBtn'), speedBtn = $('speedBtn'), speedMenu = $('speedMenu'), chapterList = $('chapterList');

let chapters = [], ended = false, dragging = false;
const SPEEDS = [0.25, 0.5, 0.75, 1, 1.25, 1.5, 1.75, 2];

const fmt = s => `${Math.floor(s/60)}:${String(Math.floor(s%60)).padStart(2,'0')}`;
const fmtPrecise = s => `${Math.floor(s/60)}:${(s%60).toFixed(3).padStart(6,'0')}`;
const getChapter = t => chapters.findLast(c => t >= c.start) || chapters[0];
const clamp = (v, min, max) => Math.max(min, Math.min(max, v));

function updateUI() {
    const t = video.currentTime, d = video.duration || 1;
    curTime.textContent = fmt(t);
    durTime.textContent = fmt(d);

    const ch = getChapter(t);
    if (ch) {
        sceneName.textContent = ch.name;
        document.querySelectorAll('.chapter').forEach((el, i) => el.classList.toggle('active', i === ch.index));
    }

    // Play button icon
    iconPlay.style.display = iconPause.style.display = iconReplay.style.display = 'none';
    (ended ? iconReplay : video.paused ? iconPlay : iconPause).style.display = 'block';

    // Progress bar segments
    chapters.forEach((ch, i) => {
        const fill = document.querySelector(`.chapter-segment[data-i="${i}"] .chapter-segment-fill`);
        if (!fill) return;
        const end = ch.start + ch.duration;
        fill.style.width = t >= end ? '100%' : t > ch.start ? `${(t - ch.start) / ch.duration * 100}%` : '0';
    });
    progressDot.style.left = `calc(${t / d * 100}% - 6px)`;
}

function togglePlay() {
    if (ended) { video.currentTime = 0; ended = false; video.play(); }
    else video.paused ? video.play() : video.pause();
}

function seek(e) {
    const pct = clamp((e.clientX - progressBar.getBoundingClientRect().left) / progressBar.offsetWidth, 0, 1);
    video.currentTime = pct * video.duration;
    ended = false;
    updateUI();
}

async function init() {
    // Load chapters
    chapters = await (await fetch('/chapters.json')).json();
    chapterList.innerHTML = chapters.map((c, i) =>
        `<div class="chapter" data-i="${i}" data-t="${c.start}"><img src="/thumb_${i}.jpg"><div class="chapter-info"><div class="name">${c.name}</div><div class="time">${fmt(c.start)}</div></div></div>`
    ).join('');
    progressTrack.innerHTML = chapters.map((c, i) =>
        `<div class="chapter-segment" data-i="${i}" style="flex-grow:${c.duration}"><div class="chapter-segment-fill"></div></div>`
    ).join('');

    // Speed menu
    speedMenu.innerHTML = SPEEDS.map(s =>
        `<div class="speed-opt${s === 1 ? ' active' : ''}" data-s="${s}">${s === 1 ? 'Normal' : s}</div>`
    ).join('');

    // Event listeners
    video.addEventListener('timeupdate', updateUI);
    video.addEventListener('play', () => { ended = false; updateUI(); });
    video.addEventListener('pause', updateUI);
    video.addEventListener('ended', () => { ended = true; updateUI(); });
    video.addEventListener('loadedmetadata', () => durTime.textContent = fmt(video.duration));
    video.addEventListener('click', togglePlay);
    playBtn.addEventListener('click', togglePlay);

    progressBar.addEventListener('mousedown', e => { dragging = true; progressBar.classList.add('dragging'); seek(e); });
    document.addEventListener('mousemove', e => dragging && seek(e));
    document.addEventListener('mouseup', () => { if (dragging) { dragging = false; progressBar.classList.remove('dragging'); } });

    chapterList.addEventListener('click', e => {
        const ch = e.target.closest('.chapter');
        if (ch) { video.currentTime = +ch.dataset.t; ended = false; updateUI(); }
    });

    copyBtn.addEventListener('click', () => {
        const ch = getChapter(video.currentTime);
        navigator.clipboard.writeText(`[${fmtPrecise(video.currentTime)}] ${ch?.name || ''}: `);
        copyBtn.textContent = 'Copied!';
        copyBtn.classList.add('copied');
        setTimeout(() => { copyBtn.textContent = 'Copy'; copyBtn.classList.remove('copied'); }, 1000);
    });

    speedBtn.addEventListener('click', e => { e.stopPropagation(); speedMenu.classList.toggle('open'); });
    document.addEventListener('click', () => speedMenu.classList.remove('open'));
    speedMenu.addEventListener('click', e => {
        const opt = e.target.closest('.speed-opt');
        if (!opt) return;
        e.stopPropagation();
        const s = +opt.dataset.s;
        video.playbackRate = s;
        speedMenu.querySelectorAll('.speed-opt').forEach(el => el.classList.toggle('active', +el.dataset.s === s));
        speedBtn.textContent = s === 1 ? '1x' : s + 'x';
        speedMenu.classList.remove('open');
    });

    document.addEventListener('keydown', e => {
        if (e.target.tagName === 'INPUT') return;
        const handlers = {
            Space: () => { e.preventDefault(); togglePlay(); },
            KeyK: () => { e.preventDefault(); togglePlay(); },
            ArrowLeft: () => { e.preventDefault(); video.currentTime = Math.max(0, video.currentTime - 5); ended = false; updateUI(); },
            KeyJ: () => { e.preventDefault(); video.currentTime = Math.max(0, video.currentTime - 5); ended = false; updateUI(); },
            ArrowRight: () => { e.preventDefault(); video.currentTime = Math.min(video.duration, video.currentTime + 5); ended = false; updateUI(); },
            KeyL: () => { e.preventDefault(); video.currentTime = Math.min(video.duration, video.currentTime + 5); ended = false; updateUI(); },
            KeyC: () => copyBtn.click()
        };
        handlers[e.code]?.();
    });

    updateUI();
}
init();
</script>
</body>
</html>'''


def create_handler(video_path: str, chapters: list, temp_dir: str):
    def handler(*args, **kwargs):
        return ViewerHandler(*args, video_path=video_path, chapters=chapters, temp_dir=temp_dir, **kwargs)
    return handler


def find_available_port(start=8000, end=9000):
    """Find an available port in the given range."""
    import socket
    for port in range(start, end):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("", port))
                return port
        except OSError:
            continue
    return None


def main():
    parser = argparse.ArgumentParser(description="Video viewer for Manim animations")
    parser.add_argument("final_video", help="Path to final stitched video")
    parser.add_argument("scenes", nargs="+", help="Paths to scene videos in order")
    parser.add_argument("--port", type=int, default=0, help="Port (default: auto)")
    args = parser.parse_args()

    if not os.path.exists(args.final_video):
        print(f"Error: Video not found: {args.final_video}")
        sys.exit(1)

    port = args.port if args.port else find_available_port()
    if not port:
        print("Error: No available port found")
        sys.exit(1)

    temp_dir = tempfile.mkdtemp(prefix="manim_viewer_")

    try:
        print("Building chapters...")
        chapters = build_chapters(args.scenes, temp_dir)
        print(f"Found {len(chapters)} chapters")

        handler = create_handler(os.path.abspath(args.final_video), chapters, temp_dir)

        with socketserver.TCPServer(("", port), handler) as httpd:
            url = f"http://localhost:{port}"
            print(f"Viewer: {url}")
            threading.Timer(0.5, lambda: webbrowser.open(url)).start()
            httpd.serve_forever()

    except KeyboardInterrupt:
        print("\nStopped")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
