#!/usr/bin/env python3
"""Video Viewer - Local viewer for Manim videos with chapter navigation."""

import argparse, http.server, json, os, re, shutil, socketserver, subprocess, sys, threading, webbrowser
from pathlib import Path
from urllib.parse import unquote, urlparse, parse_qs

def get_duration(path):
    result = subprocess.run(["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", path], capture_output=True, text=True)
    return float(json.loads(result.stdout).get("format", {}).get("duration", 0)) if result.returncode == 0 else 0.0

def scene_name(path):
    return re.sub(r"_\d{4}x\d{4}$", "", Path(path).stem)

def build_chapters(scenes):
    chapters, t = [], 0.0
    for i, path in enumerate(scenes):
        dur = get_duration(path)
        chapters.append({"index": i, "name": scene_name(path), "start": t, "duration": dur})
        t += dur
    return chapters

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, ctx=None, **kw):
        self.ctx = ctx
        super().__init__(*a, **kw)

    def do_GET(self):
        parsed = urlparse(unquote(self.path))
        path, query = parsed.path, parse_qs(parsed.query)

        routes = {
            "/": lambda: self.send_bytes(self.ctx["ui_html"], "text/html"),
            "/index.html": lambda: self.send_bytes(self.ctx["ui_html"], "text/html"),
            "/video.mp4": lambda: self.send_file(self.ctx["video"], "video/mp4"),
            "/chapters.json": lambda: self.send_bytes(json.dumps(self.ctx["chapters"]).encode(), "application/json"),
            "/subtitles.srt": lambda: self.send_bytes(self.ctx.get("srt"), "text/plain"),
            "/download": lambda: self.handle_download(),
            "/cscript.py": lambda: self.send_bytes(self.ctx.get("script_content"), "text/x-python"),
        }

        if path in routes:
            routes[path]()
        else:
            self.send_error(404)

    def send_bytes(self, data, ctype):
        if data is None:
            self.send_error(404)
            return
        body = data.encode() if isinstance(data, str) else data
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, path, ctype):
        try:
            size = os.path.getsize(path)
            range_hdr = self.headers.get("Range")

            if range_hdr and (m := re.match(r"bytes=(\d+)-(\d*)", range_hdr)):
                start, end = int(m[1]), int(m[2]) if m[2] else size - 1
                self.send_response(206)
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
                self.send_header("Content-Length", end - start + 1)
            else:
                start, end = 0, size - 1
                self.send_response(200)
                self.send_header("Content-Length", size)

            self.send_header("Content-Type", ctype)
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()

            with open(path, "rb") as f:
                f.seek(start)
                self.wfile.write(f.read(end - start + 1))
        except (BrokenPipeError, ConnectionResetError):
            pass

    def handle_download(self):
        video = self.ctx["video"]
        name = Path(video).stem
        try:
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Disposition", f'attachment; filename="{name}.mp4"')
            self.send_header("X-Filename", f"{name}.mp4")
            self.send_header("Content-Length", os.path.getsize(video))
            self.end_headers()
            with open(video, "rb") as f:
                shutil.copyfileobj(f, self.wfile)
        except Exception as e:
            print(f"Download error: {e}")
            self.send_error(500, str(e))

    def log_message(self, *_): pass

def find_port(start=8000, end=9000):
    import socket
    for p in range(start, end):
        try:
            with socket.socket() as s:
                s.bind(("127.0.0.1", p))
                return p
        except OSError:
            pass
    return None

def parse_order_file(path):
    base_dir = Path(path).parent
    videos = []
    for line in Path(path).read_text().splitlines():
        if m := re.match(r"file '(.+)'", line.strip()):
            videos.append(str(base_dir / m[1]))
    return videos

def srt_time(s):
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{int(h):02}:{int(m):02}:{int(sec):02},{int((sec % 1) * 1000):03}"

def concatenate_srts(scenes):
    """Concatenate SRT files from scene videos with time offset adjustments."""
    entries, offset = [], 0.0
    for video in scenes:
        srt_path = Path(video).with_suffix(".srt")
        if srt_path.exists():
            for block in srt_path.read_text().strip().split("\n\n"):
                lines = block.split("\n")
                if len(lines) < 3: continue
                m = re.match(r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)", lines[1])
                if not m: continue
                start = int(m[1])*3600 + int(m[2])*60 + int(m[3]) + int(m[4])/1000 + offset
                end = int(m[5])*3600 + int(m[6])*60 + int(m[7]) + int(m[8])/1000 + offset
                text = "\n".join(lines[2:])
                entries.append(f"{len(entries)+1}\n{srt_time(start)} --> {srt_time(end)}\n{text}")
        offset += get_duration(video)
    return "\n\n".join(entries) + "\n" if entries else ""

def main():
    p = argparse.ArgumentParser()
    p.add_argument("video")
    p.add_argument("--order", required=True, help="concat.txt with video file list")
    p.add_argument("--port", type=int, default=0)
    p.add_argument("--host", default="127.0.0.1", help="Host to bind (default: 127.0.0.1)")
    p.add_argument("--srt")
    p.add_argument("--script")
    args = p.parse_args()

    if not os.path.exists(args.video):
        sys.exit(f"Error: {args.video} not found")
    if not os.path.exists(args.order):
        sys.exit(f"Error: {args.order} not found")

    scenes = [s for s in parse_order_file(args.order) if os.path.exists(s)]
    if not scenes:
        sys.exit("Error: No videos found in order file")

    port = args.port or find_port()
    if not port:
        sys.exit("Error: No port available")

    print("Building chapters...")
    chapters = build_chapters(scenes)
    print(f"Found {len(chapters)} chapters")

    ctx = {
        "video": os.path.abspath(args.video),
        "chapters": chapters,
        "ui_html": Path(__file__).with_name("ui.html").read_text().encode(),
        "srt": (Path(args.srt).read_bytes() if args.srt else concatenate_srts(scenes).encode()) or None,
        "script_content": Path(args.script).read_text().encode() if args.script and os.path.exists(args.script) else None,
    }

    handler = lambda *a, **kw: Handler(*a, ctx=ctx, **kw)

    try:
        with socketserver.TCPServer((args.host, port), handler) as srv:
            url = f"http://localhost:{port}"
            print(f"Viewer: {url}")
            threading.Timer(0.5, lambda: webbrowser.open(url)).start()
            print(f"VIDEO_READY http://localhost:{port}", flush=True)
            srv.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped")

if __name__ == "__main__":
    main()
