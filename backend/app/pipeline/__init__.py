"""Analysis pipeline: extract -> dedup -> recognize -> flow -> diagnose."""
import shutil
from pathlib import Path

from ..models import AnalysisResult
from . import dedup, diagnose, extract, flow, vision


def run(video: Path, work_dir: Path, progress_cb=None) -> AnalysisResult:
    """Run the full pipeline. progress_cb(stage:str, pct:int) reports progress."""
    def report(stage: str, pct: int):
        if progress_cb:
            progress_cb(stage, pct)

    duration = extract.probe_duration(video)

    report("extracting", 5)
    frames = extract.extract_frames(video, work_dir / "frames")

    report("deduping", 25)
    keyframes = dedup.select_keyframes(frames)

    # persist keyframes under stable names so the API can serve them by index
    kf_dir = work_dir / "keyframes"
    kf_dir.mkdir(parents=True, exist_ok=True)
    for f in keyframes:
        dest = kf_dir / f"kf_{f.index:05d}.png"
        shutil.copyfile(f.path, dest)
        f.path = str(dest)

    report("recognizing", 35)
    screens, events = vision.recognize(
        keyframes,
        progress_cb=lambda done, total: report("recognizing", 35 + int(45 * done / max(total, 1))),
    )

    report("analyzing", 85)
    transitions = flow.build_transitions(events)
    mermaid = flow.to_mermaid(screens, transitions)
    findings = diagnose.heuristics(screens, events, transitions, duration)

    report("done", 100)
    return AnalysisResult(
        video_name=video.name, duration=duration, screens=screens, events=events,
        transitions=transitions, findings=findings, mermaid=mermaid,
        summary=f"{len(screens)} unique screens, {len(transitions)} transitions, "
                f"{len(findings)} findings over {duration:.0f}s.",
    )
