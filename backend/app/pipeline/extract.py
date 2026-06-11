"""Step 1 — frame extraction with ffmpeg (scene detection + uniform sampling)."""
import re
import subprocess
from pathlib import Path

from .. import config
from ..models import Frame

PTS_RE = re.compile(r"pts_time:(\d+\.?\d*)")


def probe_duration(video: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(video)],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def extract_frames(video: Path, out_dir: Path) -> list[Frame]:
    """Extract scene-change frames and uniformly sampled frames, merged and sorted."""
    out_dir.mkdir(parents=True, exist_ok=True)
    scale = f"scale={config.FRAME_WIDTH}:-1"

    # 1) scene-change frames (timestamps parsed from showinfo)
    scene_dir = out_dir / "scene"
    scene_dir.mkdir(exist_ok=True)
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", str(video),
         "-vf", f"select='gt(scene,{config.SCENE_THRESHOLD})',showinfo,{scale}",
         "-vsync", "vfr", str(scene_dir / "s%04d.png")],
        capture_output=True, text=True,
    )
    scene_ts = [float(m) for m in PTS_RE.findall(proc.stderr)]

    # 2) uniform samples
    samp_dir = out_dir / "samp"
    samp_dir.mkdir(exist_ok=True)
    fps = 1.0 / config.SAMPLE_INTERVAL_SEC
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(video),
         "-vf", f"fps={fps},{scale}", str(samp_dir / "t%04d.png")],
        check=True, capture_output=True,
    )

    frames: list[tuple[float, Path]] = []
    for i, p in enumerate(sorted(scene_dir.glob("*.png"))):
        if i < len(scene_ts):
            frames.append((scene_ts[i], p))
    for i, p in enumerate(sorted(samp_dir.glob("*.png"))):
        frames.append((i * config.SAMPLE_INTERVAL_SEC, p))

    frames.sort(key=lambda x: x[0])
    return [Frame(index=i, timestamp=round(ts, 3), path=str(p)) for i, (ts, p) in enumerate(frames)]
