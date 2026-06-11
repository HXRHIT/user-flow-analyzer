"""FastAPI app — upload a recording, poll job status, fetch results & keyframes."""
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import config, jobs

app = FastAPI(title="User Flow Analyzer", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # vite dev server
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"ok": True, "llm_configured": bool(config.ANTHROPIC_API_KEY)}


@app.post("/api/analyses")
async def create_analysis(file: UploadFile):
    suffix = Path(file.filename or "video.mp4").suffix.lower()
    if suffix not in config.ALLOWED_EXTENSIONS:
        raise HTTPException(415, f"Unsupported format {suffix}. Allowed: {sorted(config.ALLOWED_EXTENSIONS)}")
    if not config.ANTHROPIC_API_KEY:
        raise HTTPException(503, "ANTHROPIC_API_KEY is not configured on the server.")

    dest = config.UPLOAD_DIR / f"{Path(file.filename).stem[:40]}{suffix}"
    size = 0
    with dest.open("wb") as out:
        while chunk := await file.read(1 << 20):
            size += len(chunk)
            if size > config.MAX_UPLOAD_MB << 20:
                dest.unlink(missing_ok=True)
                raise HTTPException(413, f"File exceeds {config.MAX_UPLOAD_MB} MB limit.")
            out.write(chunk)

    job = jobs.create(dest)
    return {"job_id": job.id}


@app.get("/api/analyses/{job_id}")
def get_analysis(job_id: str):
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "Unknown job id")
    return job


@app.get("/api/analyses/{job_id}/frames/{index}")
def get_frame(job_id: str, index: int):
    job = jobs.get(job_id)
    if job is None or job.result is None:
        raise HTTPException(404, "Result not ready")
    frame = config.JOBS_DIR / job_id / "keyframes" / f"kf_{index:05d}.png"
    if not frame.exists():
        raise HTTPException(404, "Frame not found")
    return FileResponse(frame, media_type="image/png")


# Serve the built frontend when present (single-process deployment)
_static = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _static.exists():
    app.mount("/", StaticFiles(directory=_static, html=True), name="frontend")
