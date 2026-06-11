"""In-process job manager (no external queue — keeps the MVP easy to run)."""
import json
import threading
import traceback
import uuid
from pathlib import Path

from . import config
from .models import AnalysisResult, Job
from .pipeline import run as run_pipeline

_jobs: dict[str, Job] = {}
_lock = threading.Lock()


def create(video: Path) -> Job:
    job = Job(id=uuid.uuid4().hex[:12], video_name=video.name)
    with _lock:
        _jobs[job.id] = job
    t = threading.Thread(target=_work, args=(job.id, video), daemon=True)
    t.start()
    return job


def get(job_id: str) -> Job | None:
    with _lock:
        job = _jobs.get(job_id)
    if job is None:
        # fall back to persisted result (survives restarts)
        f = config.JOBS_DIR / f"{job_id}.json"
        if f.exists():
            job = Job.model_validate_json(f.read_text(encoding="utf-8"))
            with _lock:
                _jobs[job_id] = job
    return job


def _work(job_id: str, video: Path) -> None:
    job = _jobs[job_id]

    def progress(stage: str, pct: int):
        job.status = stage  # type: ignore[assignment]
        job.progress = pct

    try:
        work_dir = config.JOBS_DIR / job_id
        result: AnalysisResult = run_pipeline(video, work_dir, progress_cb=progress)
        job.result = result
        job.status = "done"
        job.progress = 100
        (config.JOBS_DIR / f"{job_id}.json").write_text(
            job.model_dump_json(), encoding="utf-8")
    except Exception as exc:  # noqa: BLE001 — surface any pipeline error to the client
        job.status = "error"
        job.error = f"{exc}"
        traceback.print_exc()
