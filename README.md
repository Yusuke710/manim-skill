# Manim Skill for Claude Code

**Create videos like you write code with Claude Code**

![Manim Skill Demo](manim_skill.gif)

Claude autonomously generates 3Blue1Brown-style video following a structured workflow: Plan → Code → Render → Iterate.

## Dependencies

Before using this skill, install the following dependencies:

```bash
# Install System Dependencies
brew install cairo pkg-config ffmpeg

# Install Manim Community Edition
uv tool install manim
```

## Installation

```bash
# Add this repository as a marketplace
/plugin marketplace add Yusuke710/manim-skill

# Install the plugin
/plugin install manim-skill/manim-skill
```

## How to use
Manim Skill is designed to integrate seamlessly with Claude Code. Planning, coding and rendering all happen on claude code.

1. **Plan** - A better plan leads to a better video. You can use claude code's "plan mode" just like you would plan before coding. Without plan mode, Claude will design the video structure with scenes automatically.
2. **Code and Render** - Claude writes Manim code in Python and runs Manim until all scenes render successfully. 
3. **Iterate** - Claude opens [video viewers](https://github.com/Yusuke710/manim-skill/blob/main/skills/manim-skill/tools/video_viewer.png) in your browser and you can provide feedback and paste it into Claude Code. Then it will refine the video based on your feedback. 

## License

MIT License - see [LICENSE](LICENSE) file for details.
