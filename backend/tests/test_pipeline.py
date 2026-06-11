"""Unit tests for the deterministic pipeline stages (no API key, no LLM calls)."""
import subprocess
from pathlib import Path

import pytest
from PIL import Image

from app.models import Event, Screen
from app.pipeline import dedup, diagnose, extract, flow


@pytest.fixture(scope="session")
def synthetic_video(tmp_path_factory) -> Path:
    """3 solid-color 'screens' (2s each) + 1s black 'secure' section."""
    d = tmp_path_factory.mktemp("vid")
    out = d / "synthetic.mp4"
    parts = []
    for i, color in enumerate(["red", "green", "blue", "black"]):
        seg = d / f"{i}.mp4"
        dur = 1 if color == "black" else 2
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
             "-i", f"color=c={color}:s=360x780:d={dur}:r=10", str(seg)],
            check=True)
        parts.append(seg)
    concat = d / "list.txt"
    concat.write_text("".join(f"file '{p}'\n" for p in parts))
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
                    "-i", str(concat), "-c", "copy", str(out)], check=True)
    return out


def test_probe_duration(synthetic_video):
    assert 6.5 < extract.probe_duration(synthetic_video) < 7.5


def test_extract_and_dedup(synthetic_video, tmp_path):
    frames = extract.extract_frames(synthetic_video, tmp_path)
    assert len(frames) >= 3
    keyframes = dedup.select_keyframes(frames)
    # 4 distinct sections -> at least 3 kept keyframes, far fewer than raw frames
    assert 3 <= len(keyframes) <= len(frames)
    assert any(f.is_blank for f in keyframes), "black secure section should be labeled"
    # contiguous blank frames collapse to one
    blanks = [f for f in keyframes if f.is_blank]
    assert len(blanks) == 1


def test_blank_detection(tmp_path):
    p = tmp_path / "black.png"
    Image.new("RGB", (100, 100), "black").save(p)
    with Image.open(p) as img:
        assert dedup._is_blank(img)


def _sample_session():
    screens = [
        Screen(id="S01", name="Home", type="hub", representative_frame=0),
        Screen(id="S02", name="Detail", type="detail", representative_frame=1),
        Screen(id="S03", name="Search", type="list", representative_frame=2),
    ]
    events = [
        Event(timestamp=0, screen_id="S01", action="start"),
        Event(timestamp=2, screen_id="S02", action="tap"),
        Event(timestamp=4, screen_id="S03", action="tap"),
        Event(timestamp=6, screen_id="S02", action="back"),
        Event(timestamp=30, screen_id="S01", action="back"),
    ]
    return screens, events


def test_transitions_and_backtracks():
    screens, events = _sample_session()
    transitions = flow.build_transitions(events)
    assert [(t.from_screen, t.to_screen) for t in transitions] == [
        ("S01", "S02"), ("S02", "S03"), ("S03", "S02"), ("S02", "S01")]
    assert flow.detect_backtracks(transitions) == [("S01", "S02"), ("S02", "S03")]


def test_mermaid_output():
    screens, events = _sample_session()
    transitions = flow.build_transitions(events)
    m = flow.to_mermaid(screens, transitions)
    assert m.startswith("flowchart TD")
    assert 'S01["Home"]' in m
    assert "-.->" in m  # backtrack edges dashed


def test_heuristics_flags_long_dwell_and_backtrack():
    screens, events = _sample_session()
    transitions = flow.build_transitions(events)
    findings = diagnose.heuristics(screens, events, transitions, duration=32)
    titles = " | ".join(f.title for f in findings)
    assert "Long dwell" in titles
    assert "Backtracking" in titles
