# Manim Skill

**Create videos like you write code, with your coding agent**

Works with Claude Code and Codex. Your coding agent autonomously generates
3Blue1Brown-style videos following a structured workflow: Plan → TTS → Code →
Render → Mux → View. Voiceover narration and time-synced subtitles are on by
default.

![Manim Skill Demo](manim_skill.gif)

## Installation

```bash
git clone https://github.com/Yusuke710/manim-skill
cd manim-skill

# System libraries (macOS)
brew install cairo pkg-config ffmpeg
brew install --cask mactex-no-gui   # LaTeX — required for Tex/MathTex text rendering

# Python packages — Manim + local Kokoro voiceover(no API key needed), from pyproject.toml
uv sync

# Register the skill (symlink it into each agent's skills dir)
ln -s "$PWD/skills/manim-skill" ~/.claude/skills/manim-skill   # Claude Code
ln -s "$PWD/skills/manim-skill" ~/.codex/skills/manim-skill    # Codex
# Alternatively, ask your coding agent to add this skill, e.g. "Add the skill in this manim-skill folder."
```

## How it works

Manim Skill integrates with your coding agent. Planning, coding, rendering, and
voiceover all happen there.

1. **Plan** - A better plan leads to a better video. Use plan mode just like you
   would before coding. Without it, the agent designs the scene structure
   automatically.
2. **Generate** - The agent writes the narration, generates TTS + subtitles,
   writes Manim code, lints subtitle timing, renders, and muxes until
   `video.mp4` exists.
3. **View & Iterate** - The agent opens a local viewer in your browser with Plan
   / Code / Preview tabs. Capture a timestamp, describe what to change, and the
   agent refines the affected scenes.

## Where files go

Every video is a flat session folder under one consistent home — **never** in
your working directory:

```
~/.manim-skill/<project-slug>/    # plan.md, script.py, video.mp4, media/, ...
```

Override the home with `MANIM_SKILL_HOME`. This means you can point the skill at
your own codebase ("visualize this algorithm") without it leaving artifacts
behind — it reads your files in place and writes only into the session folder.

## License

MIT License - see [LICENSE](LICENSE) file for details.
