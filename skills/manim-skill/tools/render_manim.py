"""Manim (Community Edition) rendering tool.

Uses Cairo for CPU-based rendering (no GPU required).
"""

import subprocess
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
    output_dir: str | None = None,
) -> dict[str, Any]:
    """Render Manim (Community Edition) scenes in parallel and return video paths.

    Uses Cairo for CPU-based rendering - no GPU required.

    Args:
        script_path: Path to Python file containing Manim scene classes
        scenes: List of scene class names to render
        quality: Quality preset - 'l' (480p), 'm' (720p), 'h' (1080p)
        output_dir: Directory for outputs. Defaults to /tmp/manim-outputs/<uuid>

    Returns:
        Dict with status, scene results, timing, and output_dir
    """
    start_time = time.time()
    output_dir_path = Path(output_dir) if output_dir else OUTPUT_BASE / str(uuid.uuid4())
    media_dir = output_dir_path / "media"

    script = Path(script_path)
    if not script.exists():
        return {
            "status": "error",
            "error": f"Script file not found: {script_path}",
            "output_dir": str(output_dir_path),
        }

    # Manim creates media_dir/videos/<script>/<quality>/ structure automatically
    scene_results = render_scenes(script, media_dir, scenes, quality)

    success_count = sum(1 for r in scene_results if r["status"] == "success")
    status = "success" if success_count == len(scenes) else "partial" if success_count else "error"

    return {
        "status": status,
        "scenes": scene_results,
        "total_render_time": time.time() - start_time,
        "output_dir": str(output_dir_path),
    }


def stitch_videos(
    video_paths: list[str],
    output_dir: str | None = None,
) -> dict[str, Any]:
    """Stitch multiple videos together in order.

    Args:
        video_paths: List of video file paths in the order to stitch
        output_dir: Directory for output. Defaults to /tmp/manim-outputs/<uuid>

    Returns:
        Dict with status, output path, and output_dir
    """
    output_dir_path = Path(output_dir) if output_dir else OUTPUT_BASE / str(uuid.uuid4())
    output_dir_path.mkdir(parents=True, exist_ok=True)

    output_path = output_dir_path / "stitched_video.mp4"

    # Validate all video paths exist
    missing = [p for p in video_paths if not Path(p).exists()]
    if missing:
        return {
            "status": "error",
            "error": f"Missing video files: {missing}",
            "output_dir": str(output_dir_path),
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
                "output_dir": str(output_dir_path),
            }

        return {"status": "success", "output": str(output_path), "output_dir": str(output_dir_path)}
    except Exception as e:
        return {"status": "error", "error": str(e), "output_dir": str(output_dir_path)}
    finally:
        concat_file.unlink(missing_ok=True)
