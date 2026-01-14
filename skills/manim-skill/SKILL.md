# manim

Create mathematical animations using Manim Community Edition.

## Requirements

Install before using this skill:

```bash
# Install Manim Community Edition
uv add manim

# Install FFmpeg for video stitching
brew install ffmpeg
```

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

**If the user has already planned or provided detailed requirements, skip to Phase 2.**

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
python tools/render_manim.py render <script.py> <Scene1> <Scene2> ... --quality <l|m|h> --project-id <id>
```

**Parameters:**
- `script`: Path to Python file with Scene classes
- `scenes`: Scene class names to render (space-separated)
- `--quality`: `l` (480p15), `m` (720p30), `h` (1080p60) - default: `l`
- `--project-id`: Optional UUID for organizing outputs

**Returns JSON:**
```json
{
  "status": "success|partial|error",
  "scenes": [
    {
      "name": "Scene1_Introduction",
      "status": "success",
      "video": "/tmp/manim-outputs/<project_id>/videos/<script>/480p15/Scene1_Introduction.mp4",
      "output": "manim stderr",
      "render_time": 5.2
    }
  ],
  "total_render_time": 15.3,
  "project_id": "uuid-string"
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
python tools/render_manim.py stitch <video1.mp4> <video2.mp4> ... --output <output.mp4> --project-id <id>
```

**Parameters:**
- `videos`: Video file paths in order (space-separated)
- `--output`: Output filename (default: `stitched.mp4`)
- `--project-id`: Optional UUID for output location

**Returns JSON:**
```json
{
  "status": "success|error",
  "output": "/tmp/manim-outputs/<project_id>/final.mp4",
  "project_id": "uuid-string"
}
```

### Phase 4: Iterate

After rendering:

1. **Check render results** - If any scene failed:
   - Read the error output
   - Fix the Manim code
   - Re-render only the failed scenes with the same `--project-id`

2. **After successful render** - Stitch all scene videos in order:
   ```bash
   python tools/render_manim.py stitch \
     /tmp/manim-outputs/<id>/videos/.../Scene1.mp4 \
     /tmp/manim-outputs/<id>/videos/.../Scene2.mp4 \
     --output final.mp4 --project-id <id>
   ```

3. **User feedback loop** - If user provides feedback on the video:
   - Identify which scenes need changes
   - Modify the code
   - Re-render affected scenes
   - Re-stitch the final video

## Complete Example

```python
import os
os.environ['PATH'] = '/Library/TeX/texbin:' + os.environ.get('PATH', '')

from manim import *
import numpy as np

# Colors
BACKGROUND = "#0D1117"
BLUE = "#1E88E5"
YELLOW = "#FFC107"
GREEN = "#43A047"

config.background_color = BACKGROUND

class Scene1_Introduction(Scene):
    def construct(self):
        # Title
        title = Text("The Pythagorean Theorem", font_size=48, color=BLUE)
        subtitle = Text("a² + b² = c²", font_size=36, color=YELLOW)
        subtitle.next_to(title, DOWN, buff=0.5)

        self.play(Write(title), run_time=1.5)
        self.play(FadeIn(subtitle), run_time=1)
        self.wait(2)

        self.play(FadeOut(title), FadeOut(subtitle))

class Scene2_Triangle(Scene):
    def construct(self):
        # Right triangle
        triangle = Polygon(
            [-2, -1, 0], [2, -1, 0], [-2, 2, 0],
            stroke_color=BLUE, stroke_width=3
        )

        # Labels
        a_label = Tex("a", color=GREEN).next_to(triangle, LEFT)
        b_label = Tex("b", color=GREEN).next_to(triangle, DOWN)
        c_label = Tex("c", color=YELLOW).move_to([0.5, 0.8, 0])

        self.play(Create(triangle), run_time=2)
        self.play(Write(a_label), Write(b_label), Write(c_label))
        self.wait(2)

        self.play(*[FadeOut(mob) for mob in self.mobjects])
```

**Render:**
```bash
python tools/render_manim.py render pythagorean.py Scene1_Introduction Scene2_Triangle --quality l
```

**Stitch:**
```bash
python tools/render_manim.py stitch \
  /tmp/manim-outputs/<id>/videos/pythagorean/480p15/Scene1_Introduction.mp4 \
  /tmp/manim-outputs/<id>/videos/pythagorean/480p15/Scene2_Triangle.mp4 \
  --output pythagorean_final.mp4 --project-id <id>
```

## Common Manim CE Patterns

### Text and Math

```python
# Regular text
text = Text("Hello World", font_size=48, color=WHITE)

# LaTeX math
equation = Tex(r"$E = mc^2$", font_size=36, color=YELLOW)
math = MathTex(r"\int_0^1 x^2 \, dx = \frac{1}{3}")

# Positioning
text.to_edge(UP)
equation.next_to(text, DOWN, buff=0.5)
```

### Shapes

```python
# Basic shapes
circle = Circle(radius=1, color=BLUE)
square = Square(side_length=2, color=GREEN)
line = Line(start=[-2, 0, 0], end=[2, 0, 0], color=RED)
dot = Dot(point=[0, 0, 0], color=YELLOW, radius=0.08)

# Polygon
triangle = Polygon([0, 1, 0], [-1, -1, 0], [1, -1, 0], color=PURPLE)
```

### Animations

```python
# Create/Write
self.play(Create(circle))
self.play(Write(text))

# Transform
self.play(Transform(square, circle))
self.play(ReplacementTransform(old, new))

# Fade
self.play(FadeIn(obj))
self.play(FadeOut(obj))

# Move
self.play(obj.animate.shift(RIGHT * 2))
self.play(obj.animate.move_to([1, 1, 0]))

# Wait
self.wait(1)  # 1 second pause
```

### Groups

```python
group = VGroup(circle, square, text)
group.arrange(DOWN, buff=0.5)  # Stack vertically
group.arrange(RIGHT, buff=1)   # Stack horizontally
```

## Troubleshooting

### LaTeX Not Rendering

Add at the top of your script:
```python
import os
os.environ['PATH'] = '/Library/TeX/texbin:' + os.environ.get('PATH', '')
```

### Scene Name Errors

Scene class names must:
- Start with capital letter
- Match exactly when passed to render command
- Be valid Python class names (no spaces, hyphens)

### Video Path Issues

Output videos are at:
```
/tmp/manim-outputs/<project_id>/videos/<script_name>/<quality>/<SceneName>.mp4
```

Quality directories: `480p15`, `720p30`, `1080p60`
