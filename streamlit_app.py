"""Streamlit entry point — wraps the same analysis pipeline as the FastAPI backend.

Deploy on Streamlit Community Cloud:
  1. Set main file to: streamlit_app.py
  2. Add GEMINI_API_KEY (free — aistudio.google.com) or ANTHROPIC_API_KEY to Streamlit secrets
  3. Add packages.txt at repo root with: ffmpeg

Requires:
  - requirements.txt  (Python deps — see file at repo root)
  - packages.txt      (system packages — ffmpeg)
  - GEMINI_API_KEY (free tier) or ANTHROPIC_API_KEY in Streamlit secrets or env
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "backend"))

import streamlit as st  # noqa: E402

# ── Secrets / env must be wired BEFORE importing app.config ──────────────────
try:
    for _key in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "ANTHROPIC_API_KEY"):
        if _key in st.secrets:
            os.environ[_key] = st.secrets[_key]
except FileNotFoundError:
    pass  # no secrets.toml locally → fall back to plain env vars

# Use a temp directory that persists for the process lifetime
_DATA_DIR = Path(tempfile.gettempdir()) / "ufa-data"
os.environ.setdefault("UFA_DATA_DIR", str(_DATA_DIR))

import importlib  # noqa: E402

from app import config  # noqa: E402

# Re-read env on every rerun so secrets added after first boot are picked up
# without requiring a full app reboot (config reads env at import time).
importlib.reload(config)

from app.pipeline import run as run_pipeline  # noqa: E402
from app.pipeline.report import to_markdown  # noqa: E402

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="User Flow Analyzer",
    page_icon="🎬",
    layout="wide",
    menu_items={
        "Get help": "https://github.com/HXRHIT/user-flow-analyzer",
        "Report a bug": "https://github.com/HXRHIT/user-flow-analyzer/issues",
    },
)

# ── Header ────────────────────────────────────────────────────────────────────
st.title("🎬 User Flow Analyzer")
st.caption("앱 화면 녹화 영상을 업로드하면 user flow를 자동 분석합니다.")

if not config.llm_api_key():
    st.error(
        "LLM API 키가 설정되지 않았습니다.  \n"
        "**무료**: [Google AI Studio](https://aistudio.google.com/apikey)에서 키 발급 후 "
        "Streamlit Cloud → App Settings → Secrets 에 `GEMINI_API_KEY = \"...\"` 추가  \n"
        "또는 유료 Claude: `ANTHROPIC_API_KEY = \"sk-ant-...\"`",
        icon="🔐",
    )
    st.stop()

# ── Constants ─────────────────────────────────────────────────────────────────
SEV_ICON = {"high": "🔴", "mid": "🟠", "low": "⚪", "info": "🔵"}
SEV_COLOR = {"high": "#ff4b4b", "mid": "#ffa500", "low": "#808080", "info": "#1c83e1"}


# ── Helpers ───────────────────────────────────────────────────────────────────
def render_mermaid(code: str, height: int = 560) -> None:
    """Render a Mermaid diagram inside an iframe-like component."""
    import streamlit.components.v1 as components

    html = f"""
    <div id="mermaid-diagram" style="background:#fafafa;border-radius:8px;padding:16px;">
      <pre class="mermaid">{code}</pre>
    </div>
    <script type="module">
      import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs';
      mermaid.initialize({{ startOnLoad: true, theme: 'neutral', securityLevel: 'loose' }});
    </script>
    """
    components.html(html, height=height, scrolling=True)


def _keyframe_path(work_dir: Path, frame_index: int) -> Path | None:
    """Return the keyframe PNG path saved by the pipeline, or None."""
    p = work_dir / "keyframes" / f"kf_{frame_index:05d}.png"
    return p if p.exists() else None


# ── Upload + Analysis ─────────────────────────────────────────────────────────
with st.sidebar:
    st.header("📁 영상 업로드")
    uploaded = st.file_uploader(
        "mp4 / mov / webm (최대 10분)",
        type=["mp4", "mov", "webm"],
        help="OS 화면 녹화나 앱 시뮬레이터 녹화 파일을 올려 주세요.",
    )

    st.divider()
    st.subheader("⚙️ 분석 설정")
    max_kf = st.slider(
        "최대 키프레임 수 (LLM 전송)",
        min_value=10, max_value=100,
        value=config.MAX_KEYFRAMES_TO_LLM, step=5,
        help="키프레임을 줄이면 빠르지만 정확도가 낮아질 수 있습니다.",
    )
    os.environ["UFA_MAX_KEYFRAMES_TO_LLM"] = str(max_kf)

    run_btn = st.button("🚀 분석 시작", type="primary", disabled=uploaded is None, use_container_width=True)

if uploaded and run_btn:
    # Save upload to a temp dir that we preserve in session_state
    work = Path(tempfile.mkdtemp(prefix="ufa-"))
    st.session_state["work_dir"] = str(work)

    video = work / uploaded.name
    video.write_bytes(uploaded.getbuffer())

    bar = st.progress(0, text="대기 중…")
    stage_labels = {
        "extracting":  "① 프레임 추출 중…",
        "deduping":    "② 키프레임 선별 중…",
        "recognizing": "③ 화면 인식 중 (AI Vision)…",
        "analyzing":   "④ 흐름도 · 진단 생성 중…",
        "done":        "✅ 분석 완료!",
    }

    def on_progress(stage: str, pct: int) -> None:
        bar.progress(pct, text=f"{stage_labels.get(stage, stage)} — {pct}%")

    with st.spinner("분석 파이프라인 실행 중…"):
        try:
            result = run_pipeline(video, work, progress_cb=on_progress)
            st.session_state["result"] = result
            st.session_state["result_video"] = uploaded.name
        except Exception as exc:  # noqa: BLE001
            st.error(f"**분석 실패:** {exc}", icon="❌")
            st.exception(exc)

# ── Results ───────────────────────────────────────────────────────────────────
if "result" in st.session_state:
    r = st.session_state["result"]
    work_dir = Path(st.session_state.get("work_dir", ""))

    # Summary banner
    st.success(
        f"**{r.video_name}** · {r.duration:.0f}초 · "
        f"{len(r.screens)}개 화면 · {len(r.transitions)}개 전환 · {len(r.findings)}개 발견",
        icon="✅",
    )

    st.download_button(
        "📄 보고서 다운로드 (Markdown)",
        to_markdown(r).encode("utf-8"),
        file_name=f"{Path(r.video_name).stem}-flow-report.md",
        mime="text/markdown",
        help="화면 흐름도(Mermaid)·인벤토리·행동 로그·UX 진단을 하나의 문서로 저장합니다.",
    )

    tab_flow, tab_screens, tab_events, tab_findings, tab_raw = st.tabs(
        ["🗺️ 화면 흐름도", "📱 화면 인벤토리", "📋 행동 로그", "🔍 UX 진단", "🛠️ 원시 데이터"]
    )

    # ── Tab 1: Mermaid flow diagram ───────────────────────────────────────────
    with tab_flow:
        st.subheader("화면 흐름도")
        render_mermaid(r.mermaid)
        with st.expander("Mermaid 소스 코드 보기"):
            st.code(r.mermaid, language="text")

    # ── Tab 2: Screen inventory ───────────────────────────────────────────────
    with tab_screens:
        st.subheader(f"화면 인벤토리 — {len(r.screens)}개 고유 화면")
        cols = st.columns(3)
        for i, s in enumerate(r.screens):
            with cols[i % 3]:
                with st.container(border=True):
                    # Show representative keyframe if available
                    kf_path = _keyframe_path(work_dir, s.representative_frame)
                    if kf_path:
                        st.image(str(kf_path), use_container_width=True)
                    else:
                        st.markdown("🖼️ *(이미지 없음)*")

                    st.markdown(f"**{s.id} · {s.name}**")
                    st.caption(f"타입: `{s.type}`")
                    if s.elements:
                        st.caption("UI 요소: " + " · ".join(s.elements))
                    appear_str = ", ".join(f"{t:.0f}s" for t in s.appearances[:6])
                    if len(s.appearances) > 6:
                        appear_str += f" 외 {len(s.appearances) - 6}회"
                    st.caption(f"등장 시각: {appear_str}")

    # ── Tab 3: Event log ──────────────────────────────────────────────────────
    with tab_events:
        st.subheader(f"행동 로그 — {len(r.events)}개 이벤트")
        names = {s.id: s.name for s in r.screens}
        rows = [
            {
                "시각(s)": round(e.timestamp, 1),
                "화면 ID": e.screen_id,
                "화면명": names.get(e.screen_id, e.screen_id),
                "행동": e.action + (" *" if e.confidence == "estimated" else ""),
                "대상": e.target,
                "비고": e.note,
            }
            for e in r.events
        ]
        st.dataframe(rows, use_container_width=True, height=500)
        st.caption("* = 추정된 행동 (confidence: estimated)")

    # ── Tab 4: UX findings ────────────────────────────────────────────────────
    with tab_findings:
        st.subheader(f"UX 진단 — {len(r.findings)}개 발견")
        if not r.findings:
            st.info("발견된 UX 문제가 없습니다. 👍", icon="✅")
        for f in r.findings:
            icon = SEV_ICON[f.severity]
            color = SEV_COLOR[f.severity]
            with st.container(border=True):
                st.markdown(
                    f"<span style='color:{color};font-weight:700'>"
                    f"{icon} [{f.severity.upper()}] {f.title}</span>",
                    unsafe_allow_html=True,
                )
                st.markdown(f"**근거:** {f.evidence}")
                if f.timestamps:
                    ts_str = " · ".join(f"{t:.0f}s" for t in f.timestamps)
                    st.caption(f"관련 시각: {ts_str}")
                if f.suggestion:
                    st.info(f"💡 {f.suggestion}", icon="💡")
        st.caption("단일 영상(n=1) 기반 진단 — 일반화 전 추가 검증이 필요합니다.")

    # ── Tab 5: Raw JSON ───────────────────────────────────────────────────────
    with tab_raw:
        st.subheader("원시 분석 데이터 (JSON)")
        st.download_button(
            label="📥 JSON 다운로드",
            data=r.model_dump_json(indent=2),
            file_name=f"{Path(r.video_name).stem}_analysis.json",
            mime="application/json",
        )
        st.json(r.model_dump(), expanded=False)
