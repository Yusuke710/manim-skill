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

        except Exception as e:
            print(f"Error serving file: {e}")
            self.send_error(500)

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
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: #0d1117;
            color: #e6edf3;
            height: 100vh;
            overflow: hidden;
        }
        .container {
            display: flex;
            height: 100vh;
            gap: 16px;
            padding: 16px;
        }
        .video-section {
            flex: 1;
            display: flex;
            flex-direction: column;
            min-width: 0;
        }
        .video-wrapper {
            flex: 1;
            background: #000;
            border-radius: 8px;
            overflow: hidden;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        video {
            max-width: 100%;
            max-height: 100%;
        }
        .controls {
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 12px 0;
            flex-wrap: wrap;
        }
        .time-display {
            font-family: monospace;
            font-size: 14px;
            background: #161b22;
            padding: 6px 10px;
            border-radius: 4px;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .copy-btn {
            background: #238636;
            border: none;
            color: white;
            padding: 4px 8px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 12px;
        }
        .copy-btn:hover { background: #2ea043; }
        .copy-btn.copied { background: #1f6feb; }
        .speed-control {
            display: flex;
            align-items: center;
            gap: 4px;
        }
        .speed-btn {
            background: #21262d;
            border: 1px solid #30363d;
            color: #e6edf3;
            padding: 4px 8px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 12px;
        }
        .speed-btn:hover { background: #30363d; }
        .speed-btn.active { background: #1f6feb; border-color: #1f6feb; }
        .frame-controls {
            display: flex;
            gap: 4px;
        }
        .frame-btn {
            background: #21262d;
            border: 1px solid #30363d;
            color: #e6edf3;
            padding: 4px 10px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 14px;
        }
        .frame-btn:hover { background: #30363d; }
        .current-scene {
            background: #1f6feb;
            padding: 4px 10px;
            border-radius: 4px;
            font-size: 12px;
            max-width: 300px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        .chapters-section {
            width: 320px;
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }
        .chapters-header {
            font-size: 14px;
            font-weight: 600;
            padding: 8px 0;
            border-bottom: 1px solid #30363d;
            margin-bottom: 8px;
        }
        .chapters-list {
            flex: 1;
            overflow-y: auto;
            display: flex;
            flex-direction: column;
            gap: 8px;
        }
        .chapter {
            display: flex;
            gap: 10px;
            padding: 8px;
            background: #161b22;
            border-radius: 6px;
            cursor: pointer;
            border: 2px solid transparent;
            transition: border-color 0.15s;
        }
        .chapter:hover { border-color: #30363d; }
        .chapter.active { border-color: #1f6feb; }
        .chapter-thumb {
            width: 120px;
            height: 68px;
            background: #21262d;
            border-radius: 4px;
            object-fit: cover;
            flex-shrink: 0;
        }
        .chapter-info {
            flex: 1;
            min-width: 0;
            display: flex;
            flex-direction: column;
            justify-content: center;
            gap: 4px;
        }
        .chapter-name {
            font-size: 13px;
            font-weight: 500;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        .chapter-time {
            font-size: 12px;
            color: #8b949e;
            font-family: monospace;
        }
        .shortcuts {
            font-size: 11px;
            color: #8b949e;
            padding: 8px 0;
            border-top: 1px solid #30363d;
            margin-top: 8px;
        }
        .shortcuts kbd {
            background: #21262d;
            padding: 2px 5px;
            border-radius: 3px;
            font-family: monospace;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="video-section">
            <div class="video-wrapper">
                <video id="video" src="/video.mp4"></video>
            </div>
            <div class="controls">
                <div class="time-display">
                    <span id="current-time">0:00.000</span>
                    <button class="copy-btn" id="copy-btn" title="Copy timestamp (C)">Copy</button>
                </div>
                <div class="current-scene" id="current-scene">-</div>
                <div class="speed-control">
                    <button class="speed-btn" data-speed="0.5">0.5x</button>
                    <button class="speed-btn active" data-speed="1">1x</button>
                    <button class="speed-btn" data-speed="1.5">1.5x</button>
                    <button class="speed-btn" data-speed="2">2x</button>
                </div>
                <div class="frame-controls">
                    <button class="frame-btn" id="prev-frame" title="Previous frame">&#9664;</button>
                    <button class="frame-btn" id="play-pause" title="Play/Pause">&#9654;</button>
                    <button class="frame-btn" id="next-frame" title="Next frame">&#9654;</button>
                </div>
            </div>
        </div>
        <div class="chapters-section">
            <div class="chapters-header">Chapters</div>
            <div class="chapters-list" id="chapters-list"></div>
            <div class="shortcuts">
                <kbd>Space</kbd> Play/Pause
                <kbd>&larr;</kbd><kbd>&rarr;</kbd> Frame
                <kbd>C</kbd> Copy
            </div>
        </div>
    </div>
    <script>
        const video = document.getElementById('video');
        const currentTimeEl = document.getElementById('current-time');
        const currentSceneEl = document.getElementById('current-scene');
        const copyBtn = document.getElementById('copy-btn');
        const chaptersList = document.getElementById('chapters-list');
        const playPauseBtn = document.getElementById('play-pause');
        let chapters = [];
        const FRAME_STEP = 1/30;

        function formatTime(seconds) {
            const mins = Math.floor(seconds / 60);
            const secs = seconds % 60;
            return `${mins}:${secs.toFixed(3).padStart(6, '0')}`;
        }

        function getCurrentChapter(time) {
            for (let i = chapters.length - 1; i >= 0; i--) {
                if (time >= chapters[i].start) return chapters[i];
            }
            return chapters[0];
        }

        function updateUI() {
            const time = video.currentTime;
            currentTimeEl.textContent = formatTime(time);
            const chapter = getCurrentChapter(time);
            if (chapter) {
                currentSceneEl.textContent = chapter.name;
                document.querySelectorAll('.chapter').forEach((el, i) => {
                    el.classList.toggle('active', i === chapter.index);
                });
            }
            playPauseBtn.innerHTML = video.paused ? '&#9654;' : '&#10074;&#10074;';
        }

        async function loadChapters() {
            const response = await fetch('/chapters.json');
            chapters = await response.json();
            chaptersList.innerHTML = chapters.map((ch, i) => `
                <div class="chapter" data-index="${i}" data-start="${ch.start}">
                    <img class="chapter-thumb" src="/thumb_${i}.jpg" alt="${ch.name}">
                    <div class="chapter-info">
                        <div class="chapter-name">${ch.name}</div>
                        <div class="chapter-time">${formatTime(ch.start)}</div>
                    </div>
                </div>
            `).join('');
            document.querySelectorAll('.chapter').forEach(el => {
                el.addEventListener('click', () => {
                    video.currentTime = parseFloat(el.dataset.start);
                    updateUI();
                });
            });
        }

        function copyTimestamp() {
            const chapter = getCurrentChapter(video.currentTime);
            const text = `[${formatTime(video.currentTime)}] ${chapter ? chapter.name : ''}: `;
            navigator.clipboard.writeText(text);
            copyBtn.textContent = 'Copied!';
            copyBtn.classList.add('copied');
            setTimeout(() => {
                copyBtn.textContent = 'Copy';
                copyBtn.classList.remove('copied');
            }, 1000);
        }

        video.addEventListener('timeupdate', updateUI);
        video.addEventListener('play', updateUI);
        video.addEventListener('pause', updateUI);
        copyBtn.addEventListener('click', copyTimestamp);

        document.getElementById('prev-frame').addEventListener('click', () => {
            video.pause();
            video.currentTime = Math.max(0, video.currentTime - FRAME_STEP);
            updateUI();
        });

        document.getElementById('next-frame').addEventListener('click', () => {
            video.pause();
            video.currentTime = Math.min(video.duration, video.currentTime + FRAME_STEP);
            updateUI();
        });

        playPauseBtn.addEventListener('click', () => {
            video.paused ? video.play() : video.pause();
        });

        document.querySelectorAll('.speed-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                video.playbackRate = parseFloat(btn.dataset.speed);
                document.querySelectorAll('.speed-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
            });
        });

        document.addEventListener('keydown', (e) => {
            if (e.target.tagName === 'INPUT') return;
            switch(e.code) {
                case 'Space':
                    e.preventDefault();
                    video.paused ? video.play() : video.pause();
                    break;
                case 'ArrowLeft':
                    e.preventDefault();
                    video.pause();
                    video.currentTime = Math.max(0, video.currentTime - FRAME_STEP);
                    updateUI();
                    break;
                case 'ArrowRight':
                    e.preventDefault();
                    video.pause();
                    video.currentTime = Math.min(video.duration, video.currentTime + FRAME_STEP);
                    updateUI();
                    break;
                case 'KeyC':
                    copyTimestamp();
                    break;
            }
        });

        loadChapters();
        updateUI();
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
