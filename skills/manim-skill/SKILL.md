---
name: manim-skill
description: Create mathematical animations with Manim Community Edition. Generates publication-quality animations for math concepts, graphs, geometric transformations, 3D scenes, and educational visualizations. Use when user wants to animate equations, illustrate proofs, visualize algorithms, create math explainers, or produce 3Blue1Brown-style videos.
---

# manim

Create mathematical animations using Manim Community Edition.

## When to Use

Use this skill when users want to:
- Create mathematical animations or visualizations
- Explain concepts with animated graphics (3Blue1Brown style)
- Render video content programmatically
- Build educational math/science videos

## Workflow Overview

```
Plan → Code → Render → Iterate
```

### Phase 1: Plan

**If the user has already used plan mode in claude code or provided detailed requirements, skip to Phase 2.**

Before writing any Manim code, plan the video structure:

1. **Identify the concept** - What are you explaining? What's the key insight?
2. **Break into chapters/scenes** - Each scene should focus on ONE concept
3. **Plan visual progression** - How does each scene build on the previous?
4. **Identify key moments** - What are the "aha" moments to emphasize?

Create a scene outline:
```
Scene1_Introduction - Set up the problem/concept
Scene2_StepOne - First key visualization
Scene3_StepTwo - Build complexity
...
SceneN_Summary - Recap key insights
```

**If the user did not go through a planning phase, you MUST carefully plan the video structure before writing code.**

### Phase 2: Code

Write Manim Community Edition code following these guidelines:

#### Critical: Use Manim CE, NOT ManimGL

```python
# CORRECT - Manim Community Edition imports
from manim import *
import numpy as np

# Configure background
config.background_color = "#0D1117"

class MyScene(Scene):
    def construct(self):
        # Your animation code
        pass
```

**DO NOT use ManimGL patterns:**
- No `from manimlib import *`
- No `self.embed()` or interactive features
- No `self.camera.frame` manipulations (use `self.camera` differently in CE)

#### Code Structure

1. **Shared helpers at top** - Colors, utility functions
2. **One class per scene** - Name scenes descriptively: `Scene1_Introduction`, `Scene2_DerivePDE`
3. **Use sections within scenes** - Comment blocks for organization

```python
import os
os.environ['PATH'] = '/Library/TeX/texbin:' + os.environ.get('PATH', '')

from manim import *
import numpy as np

# 3Blue1Brown-inspired palette
BACKGROUND = "#0D1117"
BLUE = "#1E88E5"
YELLOW = "#FFC107"
GREEN = "#43A047"
RED = "#E53935"
PURPLE = "#8E44AD"
WHITE = "#FFFFFF"
GREY = "#CCCCCC"

config.background_color = BACKGROUND

## Scene1_Introduction
class Scene1_Introduction(Scene):
    def construct(self):
        ## Scene1_Introduction.title
        title = Text("My Topic", font_size=48, color=BLUE)
        self.play(Write(title))
        self.wait(1)

        ## Scene1_Introduction.fadeout
        self.play(FadeOut(title))
```

#### Best Practices

- **Stay consistent** with any plans, links, or texts already provided to the user
- Use `self.play()` for animations, `self.wait()` for pauses
- Prefer `Write()` for text, `Create()` for shapes
- Use `VGroup()` to organize related objects
- End scenes with `FadeOut()` for smooth transitions
- Add `self.wait()` after key moments for viewer comprehension

### Phase 3: Render

Use the `render_manim.py` script to render scenes:

#### render_manim

Renders Manim scenes in parallel and returns video paths.

```bash
python tools/render_manim.py render <script.py> <Scene1> <Scene2> ... --quality <l|m|h> --output-dir <dir>
```

**Parameters:**
- `script`: Path to Python file with Scene classes
- `scenes`: Scene class names to render (space-separated)
- `--quality`: `l` (480p15), `m` (720p30), `h` (1080p60) - default: `l`
- `--output-dir`: Directory for outputs. Defaults to `/tmp/manim-outputs/<uuid>`

**Returns JSON:**
```json
{
  "status": "success|partial|error",
  "scenes": [
    {
      "name": "Scene1_Introduction",
      "status": "success",
      "video": "<output_dir>/media/videos/<script>/480p15/Scene1_Introduction.mp4",
      "output": "manim stderr",
      "render_time": 5.2
    }
  ],
  "total_render_time": 15.3,
  "output_dir": "/path/to/output"
}
```

**Workflow:**
1. Render ALL scenes with one command
2. Check the result JSON
3. If any scene has `"status": "error"`, fix the code and re-render ONLY failed scenes
4. Iterate until all scenes render successfully

#### stitch_videos

Stitches multiple videos together in order.

```bash
python tools/render_manim.py stitch <video1.mp4> <video2.mp4> ... --output-dir <dir>
```

**Parameters:**
- `videos`: Video file paths in order (space-separated)
- `--output-dir`: Directory for output. Defaults to `/tmp/manim-outputs/<uuid>`

**Returns JSON:**
```json
{
  "status": "success|error",
  "output": "<output_dir>/stitched_video.mp4",
  "output_dir": "/path/to/output"
}
```

### Phase 4: Iterate

After rendering:

1. **Check render results** - If any scene failed:
   - Read the error output
   - Fix the Manim code
   - Re-render only the failed scenes with the same `--output-dir`

2. **After successful render** - Stitch all scene videos in order:
   ```bash
   python tools/render_manim.py stitch \
     <output_dir>/media/videos/.../Scene1.mp4 \
     <output_dir>/media/videos/.../Scene2.mp4 \
     --output-dir <output_dir>
   ```

3. **User feedback loop** - If user provides feedback on the video:
   - Identify which scenes need changes
   - Modify the code
   - Re-render affected scenes
   - Re-stitch the final video
