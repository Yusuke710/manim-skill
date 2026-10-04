"""Regression checks; run with Python + numpy and ffmpeg/ffprobe installed."""

import array
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest


TOOLS = Path(__file__).resolve().parents[1] / "skills/manim-skill/tools"
spec = importlib.util.spec_from_file_location("tts", TOOLS / "tts-generate.py")
tts = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tts)


class SubtitleChecks(unittest.TestCase):
    def check_scene(self, body, expected):
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "script.py"
            script.write_text("from manim import *\nclass Example(Scene):\n"
                              "    def construct(self):\n" + textwrap.indent(body, "        "))
            result = subprocess.run([sys.executable, str(TOOLS / "lint-subtitles.py"),
                                     str(script)], capture_output=True, text=True)
            self.assertEqual(result.returncode, expected, result.stdout + result.stderr)

    def test_valid_timing_with_scene_clock(self):
        self.check_scene('self.add_subcaption("hello", duration=0.5)\n'
                         'self.play(FadeIn(Dot()), run_time=0.2)\n'
                         'self.wait(0.5 - self.time)\n', 0)

    def test_subtitle_past_scene_end(self):
        self.check_scene('self.add_subcaption("hello", duration=2)\nself.wait(1)\n', 1)

    def test_overlap(self):
        self.check_scene('self.add_subcaption("first", duration=2)\nself.wait(1)\n'
                         'self.add_subcaption("second", duration=2)\nself.wait(2)\n', 1)

    def test_overflow(self):
        self.check_scene('self.add_subcaption("hello", duration=1)\nself.wait(2)\n', 1)

    def test_offset(self):
        self.check_scene('self.add_subcaption("hello", duration=1, offset=1)\n'
                         'self.wait(2)\n', 0)

    def test_incomplete_simulation_cannot_pass(self):
        self.check_scene('self.add_subcaption("hello", duration=1)\n'
                         'raise RuntimeError("unsupported scene")\n', 2)

    def test_silent_scene_cannot_pass(self):
        self.check_scene('self.wait(1)\n', 2)

    def test_invalid_timing(self):
        for value in ('-1', 'float("nan")', 'float("inf")'):
            with self.subTest(value=value):
                self.check_scene(f'self.add_subcaption("hello", duration={value})\n', 2)


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "requires FFmpeg")
class NarrationChecks(unittest.TestCase):
    def test_cached_narration_cli_and_join_timing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            lines = [f"Line {i}." for i in range(8)]
            narration = root / "narration.txt"
            narration.write_text("subtitles:\n" + "".join(f"- {line}\n" for line in lines))
            self.assertEqual(tts.parse_subtitles(str(narration)), lines)
            cache = root / ".tts-cache"
            cache.mkdir()
            first = tts.cache_path(lines[0], tts.DEFAULT_VOICE, cache)
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                            "sine=frequency=440:sample_rate=24000:duration=0.2",
                            "-c:a", "libmp3lame", str(first)], check=True)
            for line in lines[1:]:
                shutil.copyfile(first, tts.cache_path(line, tts.DEFAULT_VOICE, cache))
            for flags in ([], ["--narration", "narration.txt"], ["--plan", "narration.txt"]):
                result = subprocess.run([sys.executable, str(TOOLS / "tts-generate.py"), *flags],
                                        cwd=root, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("8 cached, 0 generated", result.stdout)
            timing = json.loads((root / "timestamps.json").read_text())
            self.assertEqual([s["text"] for s in timing["subtitles"]], lines)
            decoded = subprocess.run(["ffmpeg", "-v", "error", "-i", str(root / "voiceover.mp3"),
                                      "-f", "f32le", "-ac", "1", "-ar", "24000", "-"],
                                     check=True, capture_output=True).stdout
            samples = array.array("f")
            samples.frombytes(decoded)
            self.assertAlmostEqual(len(samples) / 24000, timing["total_duration_s"], delta=0.002)
            # Every clip starts on its measured subtitle boundary, including late joins.
            for subtitle in timing["subtitles"]:
                start = int((subtitle["start_s"] + 0.02) * 24000)
                window = samples[start:start + 1200]
                self.assertGreater(sum(x * x for x in window) / len(window), 0.001)


if __name__ == "__main__":
    unittest.main()
