#!/usr/bin/env python3
"""
TTS generator for the Manim voiceover pipeline (Kokoro, local).

Reads the SubtitleSpec from narration.txt, synthesizes one MP3 per subtitle with
Kokoro, measures exact durations with ffprobe, concatenates them into
voiceover.mp3, and writes per-subtitle timings to timestamps.json.

    python tts-generate.py --narration narration.txt            # default voice af_heart
    python tts-generate.py --narration narration.txt --voice am_adam
    python tts-generate.py --narration narration.txt --bust 2   # drop one cached clip, then exit

Per-line audio is cached in .tts-cache/, so re-runs only regenerate changed
lines. The Kokoro model is loaded once per run (in-process); if every line is a
cache hit it is not loaded at all. Requires ffmpeg/ffprobe and:
    uv add "kokoro>=0.9.4" soundfile
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

DEFAULT_VOICE = "af_heart"
KOKORO_MODEL_ID = "hexgrad/Kokoro-82M"
KOKORO_LANG_CODES = {"a", "b", "e", "f", "h", "i", "j", "p", "z"}
CACHE_DIR = Path(".tts-cache")
_PIPELINES = {}


def cache_path(text: str, voice_id: str, cache_dir: Path = CACHE_DIR) -> Path:
    obj = {"model_id": KOKORO_MODEL_ID, "text": text, "voice_id": voice_id,
           "speed": os.environ.get("KOKORO_SPEED", "1")}
    key = hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return cache_dir / f"{key}.mp3"


def parse_subtitles(narration_path: str) -> list[str]:
    """
    Parse the SubtitleSpec from narration.txt: lines prefixed with `- ` under a
    `subtitles:` heading (inside or outside a fenced code block).
    """
    text = Path(narration_path).read_text()
    stripped = re.sub(r"```[^\n]*\n", "", text).replace("```", "")
    match = re.search(r"^subtitles:\s*\n(.*?)(?=\n[^\s\-\n]|\Z)", stripped, re.MULTILINE | re.DOTALL)
    if not match:
        sys.exit(f"Error: No 'subtitles:' block found in {narration_path}")
    items = [re.sub(r"^[ \t]*-\s*", "", line).strip()
             for line in match.group(1).splitlines()
             if re.match(r"^[ \t]*-", line)]
    if not items:
        sys.exit("Error: Empty subtitles list in narration.txt")
    return items


def get_pipeline(voice_id: str):
    lang_code = voice_id[:1].lower()
    if lang_code not in KOKORO_LANG_CODES:
        lang_code = "a"
    pipeline = _PIPELINES.get(lang_code)
    if pipeline is not None:
        return pipeline
    try:
        from kokoro import KPipeline
    except ImportError as e:
        raise RuntimeError(
            'Kokoro is not installed. Install it with: uv add "kokoro>=0.9.4" soundfile'
        ) from e
    pipeline = KPipeline(lang_code=lang_code, repo_id=KOKORO_MODEL_ID, device="cpu")
    _PIPELINES[lang_code] = pipeline
    return pipeline


def write_mp3(audio_chunks, out_path: Path) -> None:
    import numpy as np
    import soundfile as sf

    if not audio_chunks:
        raise RuntimeError("Kokoro returned no audio")
    chunks = []
    for audio in audio_chunks:
        if hasattr(audio, "detach"):
            audio = audio.detach().cpu().numpy()
        chunks.append(np.asarray(audio, dtype=np.float32))
    audio_out = chunks[0] if len(chunks) == 1 else np.concatenate(chunks)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        wav_path = f.name
    try:
        sf.write(wav_path, audio_out, 24000)
        subprocess.run(
            ["ffmpeg", "-y", "-i", wav_path, "-codec:a", "libmp3lame", "-q:a", "2", str(out_path)],
            check=True, capture_output=True,
        )
    finally:
        if os.path.exists(wav_path):
            os.unlink(wav_path)


def synthesize(items: list[tuple[int, str, Path]], voice_id: str) -> dict[int, str]:
    """Synthesize each (index, text, out_path) with a single shared pipeline pass."""
    if not items:
        return {}
    pipeline = get_pipeline(voice_id)
    speed = float(os.environ.get("KOKORO_SPEED", "1"))
    joined = "\n".join(text for _, text, _ in items)
    audio_by_pos: dict[int, list] = {i: [] for i in range(len(items))}
    for result in pipeline(joined, voice=voice_id, speed=speed, split_pattern=r"\n+"):
        audio_by_pos[result.text_index].append(result.audio)

    paths = {}
    for pos, (index, _, out_path) in enumerate(items):
        write_mp3(audio_by_pos[pos], out_path)
        paths[index] = str(out_path)
    return paths


def ffprobe_duration(mp3_path: str) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", mp3_path],
        capture_output=True, text=True, check=True,
    )
    return float(result.stdout.strip())


def concat_mp3s(parts: list[str], out_path: str) -> None:
    # Stream-copying MP3 packets accumulates encoder padding at every join.
    # Decode first, preserve each measured timing budget, and encode only once.
    inputs = [arg for part in parts for arg in ("-i", part)]
    filters = [
        f"[{i}:a]apad,atrim=duration={ffprobe_duration(part):.9f},"
        f"asetpts=PTS-STARTPTS[a{i}]"
        for i, part in enumerate(parts)
    ]
    filters.append("".join(f"[a{i}]" for i in range(len(parts)))
                   + f"concat=n={len(parts)}:v=0:a=1[audio]")
    subprocess.run(
        ["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(filters),
         "-map", "[audio]", "-codec:a", "libmp3lame", "-q:a", "2", out_path],
        check=True, capture_output=True,
    )


def bust_cache(subtitles: list[str], target_arg: str, voice_id: str) -> None:
    try:
        target = subtitles[int(target_arg)]
    except (ValueError, IndexError):
        matches = [s for s in subtitles if target_arg.lower() in s.lower()]
        if not matches:
            sys.exit(f"Error: no subtitle matching {target_arg!r}")
        target = matches[0]
    cp = cache_path(target, voice_id)
    if cp.exists():
        cp.unlink()
        print(f"Busted cache for: {target!r}")
    else:
        print(f"No cache entry for: {target!r}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Kokoro TTS voiceover from narration.txt SubtitleSpec")
    parser.add_argument("--narration", "--plan", dest="narration", default="narration.txt",
                        help="Spoken-line input (default: narration.txt; --plan is a compatibility alias)")
    parser.add_argument("--voice", default=DEFAULT_VOICE, help="Kokoro voice name (default: af_heart)")
    parser.add_argument("--out-audio", default="voiceover.mp3")
    parser.add_argument("--out-timestamps", default="timestamps.json")
    parser.add_argument("--bust", metavar="INDEX_OR_TEXT",
                        help="Drop the cached clip for a subtitle by 0-based index or text match, then exit")
    args = parser.parse_args()

    voice_id = args.voice
    subtitles = parse_subtitles(args.narration)

    if args.bust is not None:
        bust_cache(subtitles, args.bust, voice_id)
        return

    print(f"Found {len(subtitles)} subtitle(s). Voice: {voice_id}. Generating TTS...")
    parts = [""] * len(subtitles)
    missing: list[tuple[int, str, Path]] = []
    hits = 0
    for i, text in enumerate(subtitles):
        cached = cache_path(text, voice_id)
        if cached.exists():
            parts[i] = str(cached)
            hits += 1
            print(f"  [{i}] cached")
        else:
            missing.append((i, text, cached))

    started = time.perf_counter()
    for idx, path in synthesize(missing, voice_id).items():
        parts[idx] = path
        print(f"  [{idx}] done")
    print(f"  {hits} cached, {len(missing)} generated in {time.perf_counter() - started:.1f}s")

    print("Measuring durations...")
    durations = [ffprobe_duration(p) for p in parts]

    print(f"Concatenating {len(parts)} clips → {args.out_audio}")
    concat_mp3s(parts, args.out_audio)

    start = 0.0
    entries = []
    for i, (text, dur) in enumerate(zip(subtitles, durations)):
        entries.append({"index": i, "text": text,
                        "start_s": round(start, 3), "end_s": round(start + dur, 3),
                        "duration_s": round(dur, 3)})
        start += dur
    Path(args.out_timestamps).write_text(
        json.dumps({"total_duration_s": round(start, 3), "subtitles": entries}, indent=2))
    print(f"Done. {args.out_audio} + {args.out_timestamps} written. Total: {start:.1f}s audio.")


if __name__ == "__main__":
    main()
