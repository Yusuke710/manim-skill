#!/usr/bin/env python3
"""
Subtitle linter for Manim scripts: simulates scene timelines without rendering.

Scenes run against a stub `manim` module that only tracks time, so a full
video's script checks in well under a second. Reports:
- overlapping subtitles (next one starts before the previous ends)
- overflows (play/wait extends past the active subtitle's end)

Usage: python lint-subtitles.py script.py
Exit codes: 0 = clean, 1 = issues found, 2 = could not read/parse the script.
"""

import ast
import builtins
import keyword
import os
import sys
import types
from pathlib import Path

import numpy as np

TOL = 0.01  # seconds of slack before a timing mismatch counts
STUBBED_MODULES = ("manim", "manim.constants", "manim.mobject",
                   "manim.animation", "manim.scene", "manim.utils")
SCENE_TYPES = ("Scene", "ThreeDScene", "MovingCameraScene", "ZoomedScene")
VECTORS = {
    "UP": (0, 1, 0), "DOWN": (0, -1, 0), "LEFT": (-1, 0, 0), "RIGHT": (1, 0, 0),
    "OUT": (0, 0, 1), "IN": (0, 0, -1), "ORIGIN": (0, 0, 0),
    "UL": (-1, 1, 0), "UR": (1, 1, 0), "DL": (-1, -1, 0), "DR": (1, -1, 0),
}
# getters whose return type script math depends on; every other get_* stays a dummy
POINT_GETTERS = {
    "get_center", "get_top", "get_bottom", "get_left", "get_right", "get_corner",
    "get_edge_center", "get_start", "get_end", "get_center_of_mass",
    "get_critical_point", "get_arc_center",
}
SCALAR_GETTERS = {"get_x", "get_y", "get_z", "get_width", "get_height", "get_value"}
SCALAR_ATTRS = {"width", "height", "depth", "radius"}


class DummyMeta(type):
    """Class-level access (Tex.set_default, rate_functions.ease_out) returns dummies."""

    def __getattr__(cls, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return DummyMobject()


class DummyMobject(metaclass=DummyMeta):
    """Stands in for any manim object: absorbs attribute access, calls, and math."""

    run_time = 1.0

    def __init__(self, *args, **kwargs):
        if "run_time" in kwargs:
            self.run_time = kwargs["run_time"]
        self._items = []  # keep children so loops over groups run the real number of times
        for arg in args:
            if isinstance(arg, DummyMobject):
                self._items.append(arg)
            elif isinstance(arg, (list, tuple)):
                self._items.extend(arg)
            else:
                self._items.append(DummyMobject())

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        if name in SCALAR_ATTRS:
            return 1.0
        if name in SCALAR_GETTERS:
            return lambda *a, **k: 0.0
        if name in POINT_GETTERS:
            return lambda *a, **k: np.zeros(3)
        return DummyMobject()

    def __call__(self, *args, **kwargs):
        return DummyMobject(*args, **kwargs)

    def __iter__(self):
        return iter(self._items)

    def __len__(self):
        return len(self._items)

    def __getitem__(self, key):
        if isinstance(key, int) and 0 <= key < len(self._items):
            item = self._items[key]
            if isinstance(item, DummyMobject):  # raw values (floats, strings) stay inside
                return item
        return DummyMobject()

    def __bool__(self):  # empty groups must still be truthy
        return True

    def __array__(self, dtype=None, copy=None):
        return np.zeros(3, dtype=dtype)

    def _op(self, other):
        return other if isinstance(other, (np.ndarray, list, tuple)) else DummyMobject()

    __add__ = __radd__ = __sub__ = __rsub__ = lambda self, other: self._op(other)
    __mul__ = __rmul__ = __truediv__ = __rtruediv__ = lambda self, other: self._op(other)
    __neg__ = __pos__ = __abs__ = lambda self: DummyMobject()
    __lt__ = __le__ = __gt__ = __ge__ = lambda self, other: False  # False ends while-loops
    __float__ = lambda self: 1.0
    __int__ = __index__ = lambda self: 1


def caller_line():
    try:
        return sys._getframe(2).f_lineno
    except ValueError:
        return 0


def resolve_duration(run_time, animations=()):
    if isinstance(run_time, (int, float)):
        return max(0.0, float(run_time))
    duration = 1.0
    for anim in animations or ():
        candidate = getattr(anim, "run_time", None)
        if isinstance(candidate, (int, float)):
            duration = max(duration, float(candidate))
    return max(0.0, duration)


class Timeline:
    """Per-scene clock; records subtitles and flags overlaps/overflows as they happen."""

    def __init__(self, scene_name):
        self.scene = scene_name
        self.now = 0.0
        self.subs = []       # {start, end, text, line}
        self.overlaps = []   # (previous sub, offending sub)
        self.overflows = []  # {sub, line, event, end}
        self._active = None  # subtitle currently covering the clock, if any

    def subtitle(self, text, duration, line):
        try:
            dur = max(0.0, float(duration))
        except (TypeError, ValueError):
            dur = 1.0
        sub = {"start": self.now, "end": self.now + dur,
               "text": str(text)[:50] if text else "<empty>", "line": line}
        if self.subs and self.subs[-1]["end"] > sub["start"] + TOL:
            self.overlaps.append((self.subs[-1], sub))
        self.subs.append(sub)
        self._active = sub

    def advance(self, duration, line, event):
        try:
            step = max(0.0, float(duration))
        except (TypeError, ValueError):
            step = 0.0
        end = self.now + step
        active = self._active
        if active and self.now <= active["end"] + TOL < end:
            self.overflows.append({"sub": active, "line": line, "event": event, "end": end})
        self.now = end
        if active and self.now > active["end"] + TOL:
            self._active = None


class InstrumentedScene:
    """Replaces every manim Scene type; only the time-related methods do anything."""

    timeline = None  # swapped in per scene by simulate()

    def __init__(self, *args, **kwargs):
        self._mobjects = []

    def add_subcaption(self, content, duration=1.0, offset=0.0):
        self.timeline.subtitle(content, duration, caller_line())

    def play(self, *anims, subcaption=None, subcaption_duration=None,
             run_time=None, **kwargs):
        line = caller_line()
        duration = resolve_duration(run_time, anims)
        if subcaption:
            self.timeline.subtitle(
                subcaption,
                duration if subcaption_duration is None else subcaption_duration,
                line,
            )
        self.timeline.advance(duration, line, "play")

    def wait(self, duration=1.0, **kwargs):
        self.timeline.advance(duration, caller_line(), "wait")

    def move_camera(self, *args, run_time=None, **kwargs):
        line = caller_line()
        duration = resolve_duration(run_time, kwargs.get("added_anims", ()))
        if kwargs.get("subcaption"):
            sub_dur = kwargs.get("subcaption_duration")
            self.timeline.subtitle(kwargs["subcaption"],
                                   duration if sub_dur is None else sub_dur, line)
        self.timeline.advance(duration, line, "move_camera")

    def add(self, *mobjects):
        self._mobjects.extend(mobjects)

    @property
    def mobjects(self):
        return self._mobjects

    @property
    def camera(self):
        return DummyMobject()

    def __getattr__(self, name):
        return lambda *args, **kwargs: DummyMobject()


class ConfigStub:
    frame_width = 14.222
    frame_height = 8.0
    pixel_width = 1920
    pixel_height = 1080
    frame_rate = 60
    background_color = "#000000"

    def __getattr__(self, name):
        return None


class StubModule(types.ModuleType):
    def __getattr__(self, name):
        if name.startswith("_"):  # keep import machinery (__all__, __path__) honest
            raise AttributeError(name)
        return 1.0 if name.isupper() else DummyMobject


def collect_used_names(tree):
    """Names the script reads, so the stub can export them for `from manim import *`.

    Names bound by the script's own non-manim imports (json, numpy, ...) are excluded,
    so the stub never shadows a real module regardless of import order.
    """
    real_imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                real_imports.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            module_name = node.module or ""
            if module_name != "manim" and not module_name.startswith("manim."):
                for alias in node.names:
                    if alias.name != "*":
                        real_imports.add(alias.asname or alias.name)

    builtin_names = set(dir(builtins))
    return {
        node.id for node in ast.walk(tree)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
        and not node.id.startswith("_")
        and not keyword.iskeyword(node.id)
        and node.id not in builtin_names
        and node.id not in real_imports
    }


def make_stub(exported_names):
    stub = StubModule("manim")
    for name in SCENE_TYPES:
        setattr(stub, name, InstrumentedScene)
    for name, vec in VECTORS.items():
        setattr(stub, name, np.array(vec, dtype=float))
    stub.PI = np.pi
    stub.TAU = 2 * np.pi
    stub.DEGREES = np.pi / 180
    stub.config = ConfigStub()
    stub.np = np
    stub.interpolate = lambda a, b, t: a + (b - a) * t  # scripts mutate the result
    for name in exported_names:
        if name not in stub.__dict__:
            setattr(stub, name, 1.0 if name.isupper() else DummyMobject)
    return stub


def simulate(filepath):
    """Exec the script once against the stub, then run each scene's construct()."""
    tree = ast.parse(Path(filepath).read_text(), filename=filepath)
    code = compile(tree, filepath, "exec")

    stub = make_stub(collect_used_names(tree))
    sys.modules.update({name: stub for name in STUBBED_MODULES})
    sys.path.insert(0, os.path.dirname(filepath))

    module_globals = {
        "__name__": Path(filepath).stem,
        "__file__": filepath,
        "__builtins__": builtins,
    }
    timelines, warnings = [], []
    try:
        exec(code, module_globals)
    except Exception as exc:
        return timelines, [f"Error executing script: {exc}"]

    scene_classes = []
    for name, value in module_globals.items():
        if (isinstance(value, type) and issubclass(value, InstrumentedScene)
                and value is not InstrumentedScene
                and all(value is not cls for _, cls in scene_classes)):
            scene_classes.append((name, value))
    if not scene_classes:
        warnings.append("No Scene subclasses found")

    for name, cls in scene_classes:
        timeline = Timeline(name)
        InstrumentedScene.timeline = timeline
        try:
            cls().construct()
        except Exception as exc:
            warnings.append(f"Error in {name}.construct(): {exc}")
        timelines.append(timeline)

    return timelines, warnings


def report(timelines, warnings):
    for warning in warnings:
        print(f"Warning: {warning}", file=sys.stderr)

    overlaps = [(tl.scene, prev, sub) for tl in timelines for prev, sub in tl.overlaps]
    overflows = [(tl.scene, o) for tl in timelines for o in tl.overflows]

    if not overlaps and not overflows:
        total = sum(len(tl.subs) for tl in timelines)
        print(f"No issues found ({total} subtitles in {len(timelines)} scenes)")
        return 0

    if overlaps:
        print(f"Found {len(overlaps)} overlapping subtitle(s):\n")
        for scene, prev, sub in overlaps:
            print(f"  Scene: {scene}")
            print(f'  Line {prev["line"]}: ends at {prev["end"]:.2f}s - "{prev["text"]}"')
            print(f'  Line {sub["line"]}: starts at {sub["start"]:.2f}s - "{sub["text"]}"')
            print(f"  Overlap: {prev['end'] - sub['start']:.2f}s\n")

    if overflows:
        print(f"Found {len(overflows)} subtitle timeline overflow(s):\n")
        for scene, o in overflows:
            print(f"  Scene: {scene}")
            print(f"  Line {o['sub']['line']}: subtitle ends at {o['sub']['end']:.2f}s")
            print(f"  Line {o['line']}: {o['event']} ends at {o['end']:.2f}s")
            print(f"  Overflow: {o['end'] - o['sub']['end']:.2f}s\n")

    print("Fix: adjust subtitle durations, play run_times, or waits so each segment stays covered.")
    return 1


def main():
    if len(sys.argv) != 2:
        print("usage: python lint-subtitles.py <script.py>", file=sys.stderr)
        return 2
    print(f"Checking subtitles in: {sys.argv[1]}\n")
    try:
        timelines, warnings = simulate(os.path.abspath(sys.argv[1]))
    except (OSError, SyntaxError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    return report(timelines, warnings)


if __name__ == "__main__":
    sys.exit(main())
