#!/usr/bin/env python3
"""Video Viewer - Local viewer for Manim videos with chapter navigation."""

import argparse, http.server, json, os, re, shutil, socketserver, subprocess, sys, tempfile, threading, webbrowser
from pathlib import Path
from urllib.parse import unquote, parse_qs

def get_duration(path):
    result = subprocess.run(["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", path], capture_output=True, text=True)
    return float(json.loads(result.stdout).get("format", {}).get("duration", 0)) if result.returncode == 0 else 0.0

def extract_thumb(video, output, time=1.0):
    subprocess.run(["ffmpeg", "-y", "-ss", str(time), "-i", video, "-vframes", "1", "-q:v", "2", output], capture_output=True)

def scene_name(path):
    return re.sub(r"_\d{4}x\d{4}$", "", Path(path).stem)

def build_chapters(scenes, temp_dir):
    chapters, t = [], 0.0
    for i, path in enumerate(scenes):
        if not os.path.exists(path): continue
        dur = get_duration(path)
        extract_thumb(path, f"{temp_dir}/thumb_{i}.jpg", dur * 0.25)
        chapters.append({"index": i, "name": scene_name(path), "start": t, "duration": dur})
        t += dur
    return chapters

class Handler(http.server.SimpleHTTPRequestHandler):
    progress = {"progress": 0, "message": ""}

    def __init__(self, *a, ctx=None, **kw):
        self.ctx = ctx
        super().__init__(*a, **kw)

    def do_GET(self):
        path, query = unquote(self.path.split('?')[0]), parse_qs(self.path.split('?')[1]) if '?' in self.path else {}

        routes = {
            "/": lambda: self.send_html(Path(__file__).with_name("ui.html").read_text()),
            "/index.html": lambda: self.send_html(Path(__file__).with_name("ui.html").read_text()),
            "/video.mp4": lambda: self.send_file(self.ctx["video"], "video/mp4"),
            "/chapters.json": lambda: self.send_json(self.ctx["chapters"]),
            "/subtitles.srt": lambda: self.serve_subtitles(),
            "/download": lambda: self.handle_download(query),
            "/download/status": lambda: self.send_json(Handler.progress),
            "/plan.md": lambda: self.serve_text_file(self.ctx.get("plan"), "text/markdown"),
            "/cscript.py": lambda: self.serve_text_file(self.ctx.get("script_content"), "text/x-python"),
        }

        if path in routes:
            routes[path]()
        elif path.startswith("/thumb_"):
            thumb = f"{self.ctx['temp']}/{path[1:]}"
            self.send_file(thumb, "image/jpeg") if os.path.exists(thumb) else self.send_error(404)
        else:
            self.send_error(404)

    def send_json(self, data):
        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def send_html(self, html):
        body = html.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
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

    def serve_subtitles(self):
        if srt := self.ctx.get("srt"):
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", len(srt))
            self.end_headers()
            self.wfile.write(srt)
        else:
            self.send_error(404)

    def serve_text_file(self, content, ctype):
        if content:
            body = content.encode() if isinstance(content, str) else content
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", len(body))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_error(404)

    def handle_download(self, query):
        quality = query.get("quality", ["low"])[0]
        video, name = self.ctx["video"], Path(self.ctx["video"]).stem

        try:
            if quality == "high" and self.ctx.get("script") and self.ctx.get("scenes"):
                video = self.render_hq()
                if not video: raise Exception("Render failed")
                name = name.replace("_final", "_hq_final")

            Handler.progress = {"progress": 95, "message": "Preparing..."}
            size = os.path.getsize(video)

            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Disposition", f'attachment; filename="{name}.mp4"')
            self.send_header("X-Filename", f"{name}.mp4")
            self.send_header("Content-Length", size)
            self.end_headers()

            with open(video, "rb") as f:
                shutil.copyfileobj(f, self.wfile)
            Handler.progress = {"progress": 100, "message": "Done!"}
        except Exception as e:
            print(f"Download error: {e}")
            self.send_error(500, str(e))

    def render_hq(self):
        hq_dir = f"{self.ctx['temp']}/hq"
        os.makedirs(hq_dir, exist_ok=True)
        script_name = Path(self.ctx["script"]).stem
        videos = []

        for i, scene in enumerate(self.ctx["scenes"]):
            Handler.progress = {"progress": 10 + i * 60 // len(self.ctx["scenes"]), "message": f"Rendering {scene}..."}
            result = subprocess.run(["manim", "-qh", "--media_dir", hq_dir, self.ctx["script"], scene], capture_output=True)
            if result.returncode != 0: return None
            vpath = f"{hq_dir}/videos/{script_name}/1080p60/{scene}.mp4"
            if not os.path.exists(vpath): return None
            videos.append(vpath)

        Handler.progress = {"progress": 75, "message": "Stitching..."}
        concat = f"{self.ctx['temp']}/concat.txt"
        with open(concat, "w") as f:
            f.writelines(f"file '{v}'\n" for v in videos)

        out = f"{self.ctx['temp']}/hq_final.mp4"
        if subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat, "-c", "copy", out], capture_output=True).returncode != 0:
            return None
        return out

    def log_message(self, *_): pass

def find_port(start=8000, end=9000):
    import socket
    for p in range(start, end):
        try:
            with socket.socket() as s:
                s.bind(("", p))
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
    p.add_argument("--srt")
    p.add_argument("--script")
    p.add_argument("--plan", help="plan.md file path")
    args = p.parse_args()

    if not os.path.exists(args.video):
        sys.exit(f"Error: {args.video} not found")
    if not os.path.exists(args.order):
        sys.exit(f"Error: {args.order} not found")

    scenes = parse_order_file(args.order)
    if not scenes:
        sys.exit("Error: No videos found in order file")

    port = args.port or find_port()
    if not port:
        sys.exit("Error: No port available")

    temp = tempfile.mkdtemp(prefix="viewer_")

    try:
        print("Building chapters...")
        chapters = build_chapters(scenes, temp)
        print(f"Found {len(chapters)} chapters")

        # Load explicit SRT or auto-generate from scene SRTs
        srt_content = Path(args.srt).read_bytes() if args.srt else concatenate_srts(scenes).encode()

        # Load plan.md content
        plan_content = None
        if args.plan and os.path.exists(args.plan):
            plan_content = Path(args.plan).read_text()

        # Load script content
        script_content = None
        if args.script and os.path.exists(args.script):
            script_content = Path(args.script).read_text()

        ctx = {
            "video": os.path.abspath(args.video),
            "chapters": chapters,
            "temp": temp,
            "srt": srt_content or None,
            "script": os.path.abspath(args.script) if args.script else None,
            "script_content": script_content,
            "plan": plan_content,
            "scenes": [scene_name(s) for s in scenes if os.path.exists(s)]
        }

        handler = lambda *a, **kw: Handler(*a, ctx=ctx, **kw)

        with socketserver.TCPServer(("", port), handler) as srv:
            url = f"http://localhost:{port}"
            print(f"Viewer: {url}")
            threading.Timer(0.5, lambda: webbrowser.open(url)).start()
            print(f"VIDEO_READY http://localhost:{port}", flush=True)
            srv.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped")
    finally:
        shutil.rmtree(temp, ignore_errors=True)

if __name__ == "__main__":
    main()
