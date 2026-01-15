---
name: manim-skill
description: Create mathematical animations with Manim Community Edition. Generates distinctive, production-grade  animations for math concepts, graphs, geometric transformations, 3D scenes, and educational visualizations. Use when user wants to animate equations, illustrate proofs, visualize algorithms, create math explainers, or produce 3Blue1Brown-style videos.
---

This skill guides creation of distinctive, publication-quality mathematical animations that avoid generic "AI slop" aesthetics. Implement real working Manim code with exceptional attention to timing, composition, and visual storytelling and render it into a video.

The user provides a concept to visualize: theorem or algorithm from paper, blog post, social media post, conversation with ChatGPT etc. They may include context about the audience, style preferences, or specific moments to emphasize.

## Workflow Overview

```
Plan → Code → Render → Iterate
```

### Phase 1: Plan

**If the user has already used plan mode in claude code or provided detailed requirements, skip to Phase 2. Otherwise, you MUST carefully plan the video structure before writing code.**

Before writing any Manim code, plan the video structure:

1. **Break into chapters/scenes** - Each scene should focus on ONE concept
2. **Plan visual design** - Make intentional choices for unique, engaging visuals:

   **Composition:**
   - Reveal order: Build complexity gradually (simple → detailed)
   - Spatial hierarchy: Use positioning to show relationships (above = builds on, side-by-side = comparison, center = focus)
   - Eye flow: Guide attention left→right, top→bottom, or radially outward

   **Animation timing:**
   - Reveals (Write, Create): 0.5-1s for simple, 1.5-2s for complex
   - Transforms (morph, move): 0.3-0.5s for snappy, 1-1.5s for contemplative
   - Emphasis (highlight, scale): 0.2-0.3s quick pulse
   - Pauses: 0.5s between related items, 1-2s after key insights
   - Vary the rhythm to maintain interest

   **Emphasis techniques:**
   - Color shift: Flash or transition to accent color
   - Scale pulse: Briefly grow/shrink to draw attention
   - Isolation: Fade/dim everything except the focus
   - Zoom: Move + scale for detail examination
   - Surround: Temporary highlight ring, box, or arrow

   **Memorability check:**
   - What is the ONE visual viewers will remember?
   - Where is the "aha moment"? How will you visually punctuate it?
   - What makes this distinct from a textbook diagram?

   **Color palette:**
   - The default palette is a starting point—customize for your topic
   - Consider: warm tones for organic, cool for technical, earth tones for natural
   - Use one or two accent colors prominently, not all equally
   - Adjust background slightly for different moods

   **Avoid:**
   - Everything appearing at once (reveal sequentially)
   - Same duration for every animation (vary timing)
   - All objects centered (use spatial hierarchy)
   - No pauses after insights (let concepts land)

### Phase 2: Code

Write Manim Community Edition code in the current directory or path specified by the user. Follow these guidelines:

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

# example palette
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

Use `manim` CLI directly to render scenes. It supports parallel rendering of multiple scenes in one command.

#### Rendering Scenes

```bash
manim -q<quality> [--media_dir <output_dir>] <script.py> Scene1 Scene2 Scene3 ...
```

**Quality flags:**
- `-ql` - Low quality (480p15, fastest for testing. Use this by default for fast iterative rendering)
- `-qh` - High quality (1080p60, for final output. Do not generate with high quality unless the user explicitely asks you)

**Output location:**
Videos are saved to `<media_dir>/videos/<script_name>/<quality>/SceneName.mp4`

Default media_dir is `~/media` or current directory's `media` folder.

**Examples:**
```bash
manim -ql --media_dir /path/to/output animation.py Scene1 Scene2
```

#### Stitching Videos with ffmpeg

After rendering all scenes, stitch them together using ffmpeg:

```bash
# Create concat list file
cat > /tmp/concat_list.txt << 'EOF'
file '/path/to/Scene1_Intro.mp4'
file '/path/to/Scene2_Main.mp4'
file '/path/to/Scene3_Conclusion.mp4'
EOF

# Stitch videos - name as <theme>_final.mp4 (e.g., fourier_transform_final.mp4)
# Use the animation's topic/theme for the name unless user specifies otherwise
ffmpeg -y -f concat -safe 0 -i /tmp/concat_list.txt -c copy <theme>_final.mp4
```

### Phase 4: Iterate

After rendering:

1. **Check render results** - If any scene failed:
   - Read the error output from manim
   - Fix the Manim code
   - Re-render only the failed scenes

2. **After successful render** - Stitch all scene videos in order using ffmpeg

3. **User feedback loop** - If user provides feedback on the video:
   - Identify which scenes need changes
   - Modify the code
   - Re-render affected scenes
   - Re-stitch the final video
