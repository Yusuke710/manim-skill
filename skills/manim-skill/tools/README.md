# Video Viewer

Local browser-based viewer for reviewing Manim animations with chapter navigation and timestamped feedback.

## Usage

```bash
python3 video_viewer.py <final_video.mp4> <scene1.mp4> <scene2.mp4> ...
```

Example:
```bash
python3 video_viewer.py fourier_final.mp4 \
  media/videos/480p15/Scene1_Intro.mp4 \
  media/videos/480p15/Scene2_Transform.mp4 \
  media/videos/480p15/Scene3_Conclusion.mp4
```

## Features

- **Chapter navigation** - Click chapters to jump to scenes, thumbnails auto-extracted
- **Copy timestamp** - Copies `[M:SS.mmm] SceneName: ` format for pasting feedback
- **Frame-by-frame** - Step through animations precisely
- **Playback speed** - 0.5x, 1x, 1.5x, 2x

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Space` | Play/Pause |
| `Left Arrow` | Previous frame |
| `Right Arrow` | Next frame |
| `C` | Copy timestamp |

## Options

```
--port PORT    Server port (default: auto-finds available port)
```

## Requirements

- Python 3.10+
- ffmpeg/ffprobe (for thumbnails and duration detection)
