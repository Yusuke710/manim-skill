# Manim Skill for Claude Code

**Create mathematical animations using Manim Community Edition**

Claude autonomously generates 3b1b like video following a structured workflow: Plan → Code → Render → Iterate.

## Dependencies

Before using this skill, install the following dependencies:

```bash
# Install System Dependencies
brew install brew install cairo pkg-config ffmpeg

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

### Understanding the Structure

This repository uses the plugin format with a nested structure:

```
manim-skill/                  # Plugin root
├── .claude-plugin/           # Plugin metadata
└── skills/
    └── manim-skill/          # The actual skill
        └── SKILL.md
```

## How It Works

1. **Plan** - Claude designs the video structure with scenes
2. **Code** - Claude writes Manim Community Edition Python code
3. **Render** - The `render_manim.py` tool renders scenes in parallel
4. **Iterate** - Claude fixes any render errors and refines based on your feedback

## License

MIT License - see [LICENSE](LICENSE) file for details.
