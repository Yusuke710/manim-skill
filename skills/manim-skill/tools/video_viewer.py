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
    """Load and return the viewer HTML from the separate file."""
    html_path = Path(__file__).parent / "ui.html"
    return html_path.read_text()


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
