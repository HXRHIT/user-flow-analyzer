"""Pydantic schemas shared by the API and the pipeline."""
from typing import Literal, Optional
from pydantic import BaseModel, Field

JobStatus = Literal["queued", "extracting", "deduping", "recognizing", "analyzing", "done", "error"]


class Frame(BaseModel):
    index: int
    timestamp: float
    path: str
    phash: str = ""
    is_blank: bool = False  # black/secure screen (OS capture blocking)


class Screen(BaseModel):
    id: str
    name: str
    type: str = "unknown"  # hub | list | detail | form | sheet | confirm | survey | secure | ...
    elements: list[str] = []
    representative_frame: int
    appearances: list[float] = []  # timestamps


class Event(BaseModel):
    timestamp: float
    screen_id: str
    action: str  # tap | input | scroll | back | wait | transition | secure
    target: str = ""
    note: str = ""
    confidence: Literal["high", "estimated"] = "estimated"


class Transition(BaseModel):
    from_screen: str
    to_screen: str
    timestamp: float


class Finding(BaseModel):
    severity: Literal["high", "mid", "low", "info"]
    title: str
    evidence: str
    timestamps: list[float] = []
    suggestion: str = ""


class AnalysisResult(BaseModel):
    video_name: str
    duration: float
    screens: list[Screen] = []
    events: list[Event] = []
    transitions: list[Transition] = []
    findings: list[Finding] = []
    mermaid: str = ""
    summary: str = ""


class Job(BaseModel):
    id: str
    status: JobStatus = "queued"
    progress: int = 0
    message: str = ""
    video_name: str = ""
    error: Optional[str] = None
    result: Optional[AnalysisResult] = None
