#!/usr/bin/env python3
"""Manim (Community Edition) CLI Tool - Render scenes and stitch videos.

Uses Cairo for CPU-based rendering (no GPU required).

Usage:
    # Render scenes
    python manim_tool.py render script.py Scene1 Scene2 --quality l --project-id abc123

    # Stitch videos
    python manim_tool.py stitch video1.mp4 video2.mp4 --output final.mp4 --project-id abc123
"""

import argparse
import json
import subprocess
import sys
import tempfile
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

# ManimCE quality flags: -ql (480p15), -qm (720p30), -qh (1080p60)
QUALITY_FLAGS = {"l": "-ql", "m": "-qm", "h": "-qh"}
# ManimCE quality directory names that appear in output path
QUALITY_DIRS = {"l": "480p15", "m": "720p30", "h": "1080p60"}
OUTPUT_BASE = Path("/tmp/manim-outputs")


def _render_single_scene(
    script_path: str, scene_name: str, output_dir: str, quality_flag: str, quality_dir: str
) -> dict[str, Any]:
    """Render a single scene. Returns per-scene result dict."""
    start_time = time.time()

    # ManimCE command structure:
    # manim [OPTIONS] FILE [SCENES]
    cmd = [
        "manim",
        quality_flag,
        "--media_dir", output_dir,
        script_path,
        scene_name,
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        output = result.stderr.strip()
        render_time = time.time() - start_time

        # ManimCE output structure: media_dir/videos/<script_name>/<quality>/<SceneName>.mp4
        script_name = Path(script_path).stem
        video_path = Path(output_dir) / "videos" / script_name / quality_dir / f"{scene_name}.mp4"

        if result.returncode == 0 and video_path.exists():
            return {
                "name": scene_name,
                "status": "success",
                "video": str(video_path),
                "output": output,
                "render_time": render_time,
            }

        return {
            "name": scene_name,
            "status": "error",
            "output": output,
            "render_time": render_time,
        }
    except subprocess.TimeoutExpired:
        return {
            "name": scene_name,
            "status": "error",
            "output": "Render timeout (600s exceeded)",
            "render_time": 600.0,
        }
    except Exception as e:
        return {
            "name": scene_name,
            "status": "error",
            "output": str(e),
            "render_time": time.time() - start_time,
        }


def render_scenes(
    script_path: Path,
    output_dir: Path,
    scenes: list[str],
    quality: str = "l",
) -> list[dict[str, Any]]:
    """Render scenes from script file in parallel. Returns list of per-scene results."""
    quality_flag = QUALITY_FLAGS.get(quality, "-ql")
    quality_dir = QUALITY_DIRS.get(quality, "480p15")

    scene_results: list[dict[str, Any]] = []

    with ThreadPoolExecutor() as executor:
        futures = {
            executor.submit(
                _render_single_scene,
                str(script_path),
                scene,
                str(output_dir),
                quality_flag,
                quality_dir,
            ): scene
            for scene in scenes
        }

        for future in as_completed(futures):
            scene_results.append(future.result())

    # Sort by original scene order
    scene_order = {name: i for i, name in enumerate(scenes)}
    scene_results.sort(key=lambda r: scene_order.get(r["name"], 999))

    return scene_results


def render_manim(
    script_path: str,
    scenes: list[str],
    quality: str = "l",
    project_id: str | None = None,
) -> dict[str, Any]:
    """Render Manim (Community Edition) scenes in parallel and return video paths.

    Uses Cairo for CPU-based rendering - no GPU required.

    Args:
        script_path: Path to Python file containing Manim scene classes
        scenes: List of scene class names to render
        quality: Quality preset - 'l' (480p), 'm' (720p), 'h' (1080p)
        project_id: Optional project identifier for output organization

    Returns:
        Dict with status, scene results, timing, and project_id
    """
    start_time = time.time()
    project_id = project_id or str(uuid.uuid4())
    output_dir = OUTPUT_BASE / project_id
    output_dir.mkdir(parents=True, exist_ok=True)

    script = Path(script_path)
    if not script.exists():
        return {
            "status": "error",
            "error": f"Script file not found: {script_path}",
            "project_id": project_id,
        }

    scene_results = render_scenes(script, output_dir, scenes, quality)

    success_count = sum(1 for r in scene_results if r["status"] == "success")
    status = "success" if success_count == len(scenes) else "partial" if success_count else "error"

    return {
        "status": status,
        "scenes": scene_results,
        "total_render_time": time.time() - start_time,
        "project_id": project_id,
    }


def stitch_videos(
    video_paths: list[str],
    output_name: str = "stitched.mp4",
    project_id: str | None = None,
) -> dict[str, Any]:
    """Stitch multiple videos together in order.

    Args:
        video_paths: List of video file paths in the order to stitch
        output_name: Name for the output file (default: stitched.mp4)
        project_id: Optional project ID for output location

    Returns:
        Dict with status, output path, and project_id
    """
    project_id = project_id or str(uuid.uuid4())
    output_dir = OUTPUT_BASE / project_id
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = output_dir / output_name

    # Validate all video paths exist
    missing = [p for p in video_paths if not Path(p).exists()]
    if missing:
        return {
            "status": "error",
            "error": f"Missing video files: {missing}",
            "project_id": project_id,
        }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        for path in video_paths:
            f.write(f"file '{path}'\n")
        concat_file = Path(f.name)

    try:
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_file),
            "-c", "copy",
            str(output_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

        if result.returncode != 0:
            return {
                "status": "error",
                "error": result.stderr.strip(),
                "project_id": project_id,
            }

        return {"status": "success", "output": str(output_path), "project_id": project_id}
    except subprocess.TimeoutExpired:
        return {
            "status": "error",
            "error": "Stitch timeout (300s exceeded)",
            "project_id": project_id,
        }
    except Exception as e:
        return {"status": "error", "error": str(e), "project_id": project_id}
    finally:
        concat_file.unlink(missing_ok=True)


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Manim (Community Edition) rendering tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Render scenes
    python manim_tool.py render script.py Scene1 Scene2 --quality l

    # Stitch videos
    python manim_tool.py stitch video1.mp4 video2.mp4 --output final.mp4
        """
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Render command
    render_parser = subparsers.add_parser("render", help="Render Manim scenes")
    render_parser.add_argument("script", help="Path to Python script with Scene classes")
    render_parser.add_argument("scenes", nargs="+", help="Scene class names to render")
    render_parser.add_argument(
        "--quality", "-q",
        choices=["l", "m", "h"],
        default="l",
        help="Quality preset: l=480p15, m=720p30, h=1080p60 (default: l)"
    )
    render_parser.add_argument(
        "--project-id", "-p",
        help="Project ID for output organization (auto-generated if not provided)"
    )

    # Stitch command
    stitch_parser = subparsers.add_parser("stitch", help="Stitch videos together")
    stitch_parser.add_argument("videos", nargs="+", help="Video files to stitch in order")
    stitch_parser.add_argument(
        "--output", "-o",
        default="stitched.mp4",
        help="Output filename (default: stitched.mp4)"
    )
    stitch_parser.add_argument(
        "--project-id", "-p",
        help="Project ID for output location (auto-generated if not provided)"
    )

    args = parser.parse_args()

    if args.command == "render":
        result = render_manim(
            script_path=args.script,
            scenes=args.scenes,
            quality=args.quality,
            project_id=args.project_id,
        )
    elif args.command == "stitch":
        result = stitch_videos(
            video_paths=args.videos,
            output_name=args.output,
            project_id=args.project_id,
        )
    else:
        parser.print_help()
        return 1

    # Output JSON result
    print(json.dumps(result, indent=2))

    # Return exit code based on status
    return 0 if result.get("status") == "success" else 1


if __name__ == "__main__":
    sys.exit(main())
