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
        body {
            font-family: "Roboto", "Arial", sans-serif;
            background: #0f0f0f;
            color: #fff;
            height: 100vh;
            overflow: hidden;
        }
        .container {
            display: flex;
            height: 100vh;
            gap: 24px;
            padding: 24px;
        }
        .video-section {
            flex: 1;
            min-width: 0;
        }
        .video-wrapper {
            height: 100%;
            background: #000;
            border-radius: 12px;
            overflow: hidden;
            display: flex;
            flex-direction: column;
            position: relative;
        }
        video {
            flex: 1;
            width: 100%;
            object-fit: contain;
            cursor: pointer;
        }
        .progress-container {
            position: absolute;
            bottom: 40px;
            left: 12px;
            right: 12px;
            height: 20px;
            cursor: pointer;
            z-index: 10;
            display: flex;
            align-items: center;
        }
        .progress-track {
            width: 100%;
            height: 3px;
            background: #0f0f0f;
            position: relative;
            transition: height 0.1s;
            display: flex;
            gap: 3px;
            border-radius: 2px;
            overflow: hidden;
        }
        .progress-container:hover .progress-track {
            height: 5px;
        }
        .chapter-segment {
            height: 100%;
            background: rgba(255,255,255,0.3);
            position: relative;
            flex-shrink: 0;
        }
        .chapter-segment-fill {
            height: 100%;
            background: #ff0000;
            width: 0%;
        }
        .progress-dot {
            position: absolute;
            top: 50%;
            transform: translateY(-50%) scale(0);
            width: 13px;
            height: 13px;
            background: #ff0000;
            border-radius: 50%;
            transition: transform 0.1s;
            z-index: 5;
            pointer-events: none;
        }
        .progress-container:hover .progress-dot,
        .progress-container.dragging .progress-dot {
            transform: translateY(-50%) scale(1);
        }
        .controls-bar {
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 8px 12px;
            background: linear-gradient(transparent, rgba(0,0,0,0.9));
            position: absolute;
            bottom: 0;
            left: 0;
            right: 0;
        }
        .control-btn {
            background: transparent;
            border: none;
            color: #fff;
            width: 40px;
            height: 40px;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            border-radius: 50%;
            font-size: 18px;
        }
        .control-btn:hover {
            background: rgba(255,255,255,0.1);
        }
        .control-btn svg {
            width: 24px;
            height: 24px;
            fill: #fff;
        }
        .time-display {
            font-size: 13px;
            color: #fff;
            margin-left: 4px;
            display: flex;
            align-items: center;
            gap: 4px;
        }
        .time-display .separator {
            color: #aaa;
        }
        .copy-btn {
            background: #238636;
            border: none;
            color: #fff;
            padding: 4px 10px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 12px;
            margin: 0 8px;
        }
        .copy-btn:hover {
            background: #2ea043;
        }
        .copy-btn.copied {
            background: #1f6feb;
        }
        .current-scene {
            font-size: 13px;
            color: #fff;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
            max-width: 300px;
        }
        .spacer {
            flex: 1;
        }
        .speed-wrapper {
            position: relative;
        }
        .speed-btn {
            background: transparent;
            border: none;
            color: #fff;
            padding: 6px 12px;
            cursor: pointer;
            font-size: 13px;
            border-radius: 2px;
        }
        .speed-btn:hover {
            background: rgba(255,255,255,0.1);
        }
        .speed-menu {
            position: absolute;
            bottom: 100%;
            right: 0;
            background: #212121;
            border-radius: 8px;
            padding: 8px 0;
            min-width: 120px;
            display: none;
            box-shadow: 0 4px 16px rgba(0,0,0,0.5);
            margin-bottom: 8px;
        }
        .speed-menu.open {
            display: block;
        }
        .speed-option {
            display: flex;
            align-items: center;
            padding: 8px 16px;
            cursor: pointer;
            font-size: 14px;
            color: #fff;
        }
        .speed-option:hover {
            background: rgba(255,255,255,0.1);
        }
        .speed-option.active {
            color: #fff;
        }
        .speed-option.active::before {
            content: '✓';
            margin-right: 12px;
            font-size: 12px;
        }
        .speed-option:not(.active)::before {
            content: '';
            margin-right: 24px;
        }
        .chapters-section {
            width: 360px;
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }
        .chapters-header {
            font-size: 16px;
            font-weight: 500;
            padding: 12px 0;
            border-bottom: 1px solid #3f3f3f;
            margin-bottom: 12px;
        }
        .chapters-list {
            flex: 1;
            overflow-y: auto;
            display: flex;
            flex-direction: column;
            gap: 8px;
        }
        .chapters-list::-webkit-scrollbar {
            width: 8px;
        }
        .chapters-list::-webkit-scrollbar-track {
            background: transparent;
        }
        .chapters-list::-webkit-scrollbar-thumb {
            background: #3f3f3f;
            border-radius: 4px;
        }
        .chapter {
            display: flex;
            gap: 12px;
            padding: 8px;
            border-radius: 8px;
            cursor: pointer;
            transition: background 0.2s;
        }
        .chapter:hover {
            background: #272727;
        }
        .chapter.active {
            background: #272727;
        }
        .chapter.active .chapter-thumb {
            border: 2px solid #fff;
        }
        .chapter-thumb {
            width: 120px;
            height: 68px;
            background: #272727;
            border-radius: 8px;
            object-fit: cover;
            flex-shrink: 0;
            border: 2px solid transparent;
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
            font-size: 14px;
            font-weight: 500;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
            line-height: 1.4;
        }
        .chapter-time {
            font-size: 12px;
            color: #aaa;
        }
        .shortcuts {
            font-size: 12px;
            color: #aaa;
            padding: 12px 0;
            border-top: 1px solid #3f3f3f;
            margin-top: 12px;
            line-height: 1.8;
        }
        .shortcuts kbd {
            background: #272727;
            padding: 3px 8px;
            border-radius: 4px;
            font-family: inherit;
            font-size: 11px;
            margin-right: 4px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="video-section">
            <div class="video-wrapper">
                <video id="video" src="/video.mp4"></video>
                <div class="progress-container" id="progress-bar">
                    <div class="progress-track" id="progress-track"></div>
                    <div class="progress-dot" id="progress-dot"></div>
                </div>
                <div class="controls-bar">
                    <button class="control-btn" id="play-pause" title="Play (k)">
                        <svg id="play-icon" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
                        <svg id="pause-icon" viewBox="0 0 24 24" style="display:none"><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/></svg>
                        <svg id="replay-icon" viewBox="0 0 24 24" style="display:none"><path d="M12 5V1L7 6l5 5V7c3.31 0 6 2.69 6 6s-2.69 6-6 6-6-2.69-6-6H4c0 4.42 3.58 8 8 8s8-3.58 8-8-3.58-8-8-8z"/></svg>
                    </button>
                    <div class="time-display">
                        <span id="current-time">0:00</span>
                        <span class="separator">/</span>
                        <span id="duration">0:00</span>
                    </div>
                    <button class="copy-btn" id="copy-btn" title="Copy timestamp (C)">Copy</button>
                    <div class="current-scene" id="current-scene">-</div>
                    <div class="spacer"></div>
                    <div class="speed-wrapper">
                        <button class="speed-btn" id="speed-btn">1x</button>
                        <div class="speed-menu" id="speed-menu">
                            <div class="speed-option" data-speed="0.25">0.25</div>
                            <div class="speed-option" data-speed="0.5">0.5</div>
                            <div class="speed-option" data-speed="0.75">0.75</div>
                            <div class="speed-option active" data-speed="1">Normal</div>
                            <div class="speed-option" data-speed="1.25">1.25</div>
                            <div class="speed-option" data-speed="1.5">1.5</div>
                            <div class="speed-option" data-speed="1.75">1.75</div>
                            <div class="speed-option" data-speed="2">2</div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        <div class="chapters-section">
            <div class="chapters-header">Chapters</div>
            <div class="chapters-list" id="chapters-list"></div>
            <div class="shortcuts">
                <kbd>Space</kbd> Play/Pause
                <kbd>←</kbd><kbd>→</kbd> 5 sec
                <kbd>C</kbd> Copy timestamp
            </div>
        </div>
    </div>
    <script>
        const video = document.getElementById('video');
        const currentTimeEl = document.getElementById('current-time');
        const durationEl = document.getElementById('duration');
        const currentSceneEl = document.getElementById('current-scene');
        const copyBtn = document.getElementById('copy-btn');
        const chaptersList = document.getElementById('chapters-list');
        const playPauseBtn = document.getElementById('play-pause');
        const playIcon = document.getElementById('play-icon');
        const pauseIcon = document.getElementById('pause-icon');
        const replayIcon = document.getElementById('replay-icon');
        const progressBar = document.getElementById('progress-bar');
        const progressTrack = document.getElementById('progress-track');
        const progressDot = document.getElementById('progress-dot');
        const speedBtn = document.getElementById('speed-btn');
        const speedMenu = document.getElementById('speed-menu');
        let chapters = [];
        let isEnded = false;
        let isDragging = false;
        const SEEK_STEP = 5;

        function formatTime(seconds) {
            const mins = Math.floor(seconds / 60);
            const secs = Math.floor(seconds % 60);
            return `${mins}:${secs.toString().padStart(2, '0')}`;
        }

        function formatTimePrecise(seconds) {
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

        function updatePlayButton() {
            if (isEnded) {
                playIcon.style.display = 'none';
                pauseIcon.style.display = 'none';
                replayIcon.style.display = 'block';
                playPauseBtn.title = 'Replay (k)';
            } else if (video.paused) {
                playIcon.style.display = 'block';
                pauseIcon.style.display = 'none';
                replayIcon.style.display = 'none';
                playPauseBtn.title = 'Play (k)';
            } else {
                playIcon.style.display = 'none';
                pauseIcon.style.display = 'block';
                replayIcon.style.display = 'none';
                playPauseBtn.title = 'Pause (k)';
            }
        }

        function updateUI() {
            const time = video.currentTime;
            currentTimeEl.textContent = formatTime(time);
            if (video.duration) {
                durationEl.textContent = formatTime(video.duration);
            }
            const chapter = getCurrentChapter(time);
            if (chapter) {
                currentSceneEl.textContent = chapter.name;
                document.querySelectorAll('.chapter').forEach((el, i) => {
                    el.classList.toggle('active', i === chapter.index);
                });
            }
            updatePlayButton();
            // Update chapter segment fills
            if (video.duration && chapters.length > 0) {
                const totalDuration = video.duration;
                chapters.forEach((ch, i) => {
                    const segmentEl = document.querySelector(`.chapter-segment[data-index="${i}"] .chapter-segment-fill`);
                    if (segmentEl) {
                        const chapterEnd = ch.start + ch.duration;
                        if (time >= chapterEnd) {
                            segmentEl.style.width = '100%';
                        } else if (time > ch.start) {
                            const progress = (time - ch.start) / ch.duration * 100;
                            segmentEl.style.width = progress + '%';
                        } else {
                            segmentEl.style.width = '0%';
                        }
                    }
                });
                // Position the dot
                const percent = time / totalDuration * 100;
                progressDot.style.left = `calc(${percent}% - 6px)`;
            }
        }

        async function loadChapters() {
            const response = await fetch('/chapters.json');
            chapters = await response.json();

            // Render chapter list
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
                    isEnded = false;
                    updateUI();
                });
            });

            // Render chapter segments on progress bar
            progressTrack.innerHTML = chapters.map((ch, i) => {
                return `<div class="chapter-segment" data-index="${i}" style="flex-grow: ${ch.duration}">
                    <div class="chapter-segment-fill"></div>
                </div>`;
            }).join('');
        }

        function copyTimestamp() {
            const chapter = getCurrentChapter(video.currentTime);
            const text = `[${formatTimePrecise(video.currentTime)}] ${chapter ? chapter.name : ''}: `;
            navigator.clipboard.writeText(text);
            copyBtn.textContent = 'Copied!';
            copyBtn.classList.add('copied');
            setTimeout(() => {
                copyBtn.textContent = 'Copy';
                copyBtn.classList.remove('copied');
            }, 1000);
        }

        function togglePlayPause() {
            if (isEnded) {
                video.currentTime = 0;
                isEnded = false;
                video.play();
            } else if (video.paused) {
                video.play();
            } else {
                video.pause();
            }
        }

        video.addEventListener('timeupdate', updateUI);
        video.addEventListener('play', () => { isEnded = false; updateUI(); });
        video.addEventListener('pause', updateUI);
        video.addEventListener('ended', () => { isEnded = true; updateUI(); });
        video.addEventListener('loadedmetadata', () => {
            durationEl.textContent = formatTime(video.duration);
        });
        video.addEventListener('click', togglePlayPause);
        copyBtn.addEventListener('click', copyTimestamp);

        function seekToPosition(e) {
            const rect = progressBar.getBoundingClientRect();
            const percent = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
            video.currentTime = percent * video.duration;
            isEnded = false;
            updateUI();
        }

        progressBar.addEventListener('mousedown', (e) => {
            isDragging = true;
            progressBar.classList.add('dragging');
            seekToPosition(e);
        });

        document.addEventListener('mousemove', (e) => {
            if (isDragging) {
                seekToPosition(e);
            }
        });

        document.addEventListener('mouseup', () => {
            if (isDragging) {
                isDragging = false;
                progressBar.classList.remove('dragging');
            }
        });

        playPauseBtn.addEventListener('click', togglePlayPause);

        speedBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            speedMenu.classList.toggle('open');
        });

        document.addEventListener('click', () => {
            speedMenu.classList.remove('open');
        });

        document.querySelectorAll('.speed-option').forEach(opt => {
            opt.addEventListener('click', (e) => {
                e.stopPropagation();
                const speed = parseFloat(opt.dataset.speed);
                video.playbackRate = speed;
                document.querySelectorAll('.speed-option').forEach(o => o.classList.remove('active'));
                opt.classList.add('active');
                speedBtn.textContent = speed === 1 ? '1x' : speed + 'x';
                speedMenu.classList.remove('open');
            });
        });

        document.addEventListener('keydown', (e) => {
            if (e.target.tagName === 'INPUT') return;
            switch(e.code) {
                case 'Space':
                case 'KeyK':
                    e.preventDefault();
                    togglePlayPause();
                    break;
                case 'ArrowLeft':
                case 'KeyJ':
                    e.preventDefault();
                    video.currentTime = Math.max(0, video.currentTime - SEEK_STEP);
                    isEnded = false;
                    updateUI();
                    break;
                case 'ArrowRight':
                case 'KeyL':
                    e.preventDefault();
                    video.currentTime = Math.min(video.duration, video.currentTime + SEEK_STEP);
                    isEnded = false;
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
