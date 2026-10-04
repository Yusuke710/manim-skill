---
name: manim-skill
description: Create mathematical animations with Manim Community Edition(manimce), with optional TTS voiceover and synced subtitles. Generates distinctive, production-grade animations that avoid generic "AI slop" aesthetics. Use when user wants to animate concepts, equations, illustrate proofs, visualize algorithms, create math explainers, or produce 3Blue1Brown-style videos.
---

You are a Manim animation expert. Create production-grade animations with Manim Community Edition (manimce).

## Contract

- For animation requests, continue until `video.mp4` exists; if blocked, return the exact blocker plainly.
- Deliver `script.py` and `video.mp4`. Do not create `plan.md` or a separate written scene plan unless the user explicitly requests one. Choose the visual design and scene structure directly in the animation code.

## Session Storage

**NEVER write artifacts into the user's working directory.** Every video is a flat session folder:

```
SESSION_DIR = ${MANIM_SKILL_HOME:-~/.manim-skill}/<project-slug>/
├── narration.txt    # spoken lines only (when narrated)
├── voiceover.mp3    # concatenated TTS audio
├── timestamps.json  # per-subtitle timing
├── script.py        # Manim code
├── concat.txt       # ffmpeg scene list
├── video.mp4        # final deliverable
└── media/           # manim output
```

`<project-slug>` is a short kebab-case topic name (append `-2`, `-3`, ... on collision). `TOOLS_DIR` is the `tools/` directory next to this SKILL.md. When the video is about the user's code or files, read those from their original location — only outputs go in `SESSION_DIR`.

**Setup — run once at the very start**, then stay in `SESSION_DIR` for every phase so outputs land there; substitute `<TOOLS_DIR>` in the commands below with its absolute path (the tools are invoked in place, never copied):

```bash
SESSION_DIR="${MANIM_SKILL_HOME:-$HOME/.manim-skill}/<project-slug>"
mkdir -p "$SESSION_DIR"
cd "$SESSION_DIR"
```

**Voiceover is on by default.** Skip narration, TTS, subtitle linting, muxing, and `add_subcaption()` only if the user asks for no TTS/narration/voiceover/captions, or the local `kokoro` package is not installed (then tell the user voiceover was skipped and that `uv add "kokoro>=0.9.4" soundfile` enables it).

## Workflow: Narration → TTS → Code → Render → Mux → View

### Phase 1: Narration

When voiceover is enabled, write only the spoken lines in `narration.txt`, using the exact format below. Each entry becomes one TTS clip. Kokoro speaks ≈2.5 words/second — size the lines to the target video length. For silent videos, start with Code.

```
subtitles:
- First voiceover line.
- Second voiceover line.
- Each entry becomes one TTS clip.
```

### Phase 2: TTS

```
python "<TOOLS_DIR>/tts-generate.py" --narration narration.txt
```

Local Kokoro voice `af_heart` by default; `--voice <name>` (e.g. `am_adam`, `bf_emma`) for another. Unchanged lines are served from `.tts-cache/`.

Produces `voiceover.mp3` and `timestamps.json`. The run prints how many clips it found — confirm it matches your narration line count (a mismatch means the block didn't parse; fix the format in `narration.txt`). **Read `timestamps.json` before writing code** — each `duration_s` is the exact time budget for that subtitle's segment.

### Phase 3: Code

Write `script.py`:

1. **One class per scene**, named descriptively (`Scene1_Introduction`, `Scene2_DerivePDE`) — this is what enables selective re-render during feedback and chapter navigation in the viewer.
2. **Render config lives in `script.py`** — set `config.pixel_width`, `config.pixel_height`, `config.frame_width`, `config.frame_height`, `config.frame_rate` there (it determines output paths). Iteration defaults unless the user asks otherwise:
   - `16:9` → 854×480, frame 16×9, 15 fps
   - `9:16` → 480×854, frame 9×16, 15 fps
   - `1:1` → 480×480, frame 8×8, 15 fps
   Keep the pixel and frame aspect ratios matched.
3. **Each narration line becomes exactly one `self.add_subcaption(text, duration=duration_s)` call — same text, same order** (a scene may hold several consecutive segments). Never burn subtitles in as text mobjects: `add_subcaption()` emits the per-scene `.srt` files the viewer uses; the linter simulates the calls in `script.py`. Inline each `duration_s` from `timestamps.json` as a literal, set explicit `run_time=` on every `play()`, keep total scheduled time (including `wait()` and `move_camera()`) within the budget, and end each segment with `self.wait(max(0, dur - used))`.
4. **`MathTex(...)` for formulas; prefer `Tex(...)` over `Text(...)` for prose** (Pango can produce odd letter spacing).

```python
from manim import *

class Scene1_Introduction(Scene):
    def construct(self):
        title = Tex("My Topic", font_size=48, color=BLUE)

        dur = 2.8        # duration_s from timestamps.json
        anim_rt = 1.5
        self.add_subcaption("Introduction to My Topic", duration=dur)
        self.play(Write(title), run_time=anim_rt)
        self.wait(max(0, dur - anim_rt))
```

### Phase 4: Render

For narrated videos, lint first — render only when it passes. Exit code 1 means timing issues; 2 means the simulation was incomplete or invalid. Fix the cause before rendering. Skip this check for silent videos:

```
python "<TOOLS_DIR>/lint-subtitles.py" script.py
```

```
manim script.py Scene1_Introduction Scene2_Main ...
```

Scenes land in `media/videos/script/<pixel_height>p<frame_rate:g>/SceneName.mp4`. Write `concat.txt` listing them in order (the viewer needs it for chapters):

```
file 'media/videos/script/480p15/Scene1_Introduction.mp4'
file 'media/videos/script/480p15/Scene2_Main.mp4'
```

```
ffmpeg -y -f concat -safe 0 -i concat.txt -c copy -movflags +faststart video_silent.mp4
```

**Without voiceover**, write `video.mp4` here instead and skip Phase 5.

### Phase 5: Mux

```
ffmpeg -y -i video_silent.mp4 -i voiceover.mp3 \
  -map 0:v:0 -map 1:a:0 \
  -c:v copy -c:a aac \
  -movflags +faststart video.mp4
```

Verify `video.mp4` with `ffprobe`, inspect representative frames for readability and layout, and check rendered audio/video sync when narrated. The linter is a simulation, not a substitute for these checks.

### Phase 6: View & Feedback

Launch the viewer from `SESSION_DIR`, in the background:

```
python3 <TOOLS_DIR>/video_viewer.py video.mp4 --order concat.txt --script script.py
```

It prints `VIDEO_READY http://localhost:<port>` and opens the browser. Tell the user the URL and the `SESSION_DIR` path.

The viewer's Capture button (`T`) drops timestamped lines into the feedback panel, e.g. `[0:07] Scene3_Identity: the c² label overlaps the triangle`. When feedback references a moment like that, extract that exact frame (`ffmpeg -y -ss 7 -i video.mp4 -vframes 1 f.png`) and Read it before touching code — seeing what the user saw beats guessing.

Then iterate:

1. If voiceover lines changed: edit `narration.txt`, re-run Phase 2 (unchanged lines are cache hits; `python "<TOOLS_DIR>/tts-generate.py" --bust <index or text fragment>` force-regenerates one clip), and update `script.py` to the new `timestamps.json`.
2. Fix the named scenes, lint when narrated, re-render **only the affected scenes**, re-mux.
3. The viewer serves the new `video.mp4` on reload; restart it only if it was stopped.
