# Video Tools

## concat_srt.py

Concatenate SRT files with time offsets based on video order.

```bash
python3 concat_srt.py <order.txt> [output.srt]
```

- Reads `concat.txt` (same file used by ffmpeg)
- Finds `.srt` next to each `.mp4`
- Outputs `final.srt` in same directory (or explicit path)

## video_viewer.py

Browser-based viewer for Manim animations with chapter navigation.

```bash
python3 video_viewer.py <video.mp4> --order <concat.txt> [--srt <subtitles.srt>] [--script <script.py>]
```

**Options:**
- `--order` - Video order file (required)
- `--srt` - Subtitles file
- `--script` - Manim script (enables HQ download)
- `--port` - Server port (default: auto)

**Shortcuts:** `Space` play/pause, `←→` frame step, `C` copy timestamp

## Requirements

- Python 3.10+
- ffmpeg/ffprobe
