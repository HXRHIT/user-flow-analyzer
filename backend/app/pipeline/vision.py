"""Step 3 — screen recognition with a vision LLM (Gemini free tier or Claude).

Keyframes are sent in timestamp order (batched) and the model returns, per frame:
screen name, screen type, notable UI elements, the inferred user action since the
previous frame, and whether sensitive data (account numbers, balances, names) is
visible. Frames sharing the same screen name are clustered into unique screens.

Provider is selected by config.LLM_PROVIDER ("gemini" | "anthropic").
"""
import base64
import json
import time
from pathlib import Path

from .. import config
from ..models import Event, Frame, Screen

SYSTEM_PROMPT = """You are a mobile UX analyst. You will receive consecutive keyframes
from one app screen-recording, each labeled with its timestamp. For EVERY frame return
a JSON object with:
- "t": timestamp (copy from label)
- "screen": short stable screen name (reuse the EXACT same name when the same logical
  screen reappears, even if scrolled or with different banner content)
- "type": one of hub|list|detail|form|sheet|keypad|confirm|survey|loading|error|secure|other
- "elements": up to 6 notable UI elements (buttons, inputs, tabs) as short strings
- "action": user action inferred relative to the PREVIOUS frame:
  tap|input|scroll|back|wait|transition|start
- "target": what was tapped/edited if inferable, else ""
- "sensitive": true if account numbers, balances, or personal names are visible

Respond with ONLY a JSON array, no prose. Use the recording's UI language for names."""

BATCH_SIZE = 10
MAX_RETRIES = 3
RETRY_WAIT_SEC = 20  # free tiers are rate-limited per minute; back off and retry


def recognize(keyframes: list[Frame], progress_cb=None) -> tuple[list[Screen], list[Event]]:
    visible = [f for f in keyframes if not f.is_blank][: config.MAX_KEYFRAMES_TO_LLM]
    generate = _generate_gemini if config.LLM_PROVIDER == "gemini" else _generate_anthropic
    raw: list[dict] = []

    for start in range(0, len(visible), BATCH_SIZE):
        batch = visible[start : start + BATCH_SIZE]
        text = _with_retries(generate, batch)
        text = text[text.find("[") : text.rfind("]") + 1]  # tolerate stray prose/code fences
        raw.extend(json.loads(text))
        if progress_cb:
            progress_cb(min(start + BATCH_SIZE, len(visible)), len(visible))

    return _cluster(raw, keyframes)


def _with_retries(generate, batch) -> str:
    last_exc: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            return generate(batch)
        except Exception as exc:  # noqa: BLE001 — retry rate limits / transient errors
            last_exc = exc
            if "429" in str(exc) or "RESOURCE_EXHAUSTED" in str(exc) or "rate" in str(exc).lower():
                time.sleep(RETRY_WAIT_SEC * (attempt + 1))
                continue
            raise
    raise RuntimeError(f"LLM call failed after {MAX_RETRIES} retries: {last_exc}")


# ── Providers ──────────────────────────────────────────────────────────────────

def _generate_gemini(batch: list[Frame]) -> str:
    """Google Gemini via google-genai SDK (free tier available at aistudio.google.com)."""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=config.GEMINI_API_KEY)
    contents: list = []
    for f in batch:
        contents.append(f"[frame @ {f.timestamp:.1f}s]")
        contents.append(types.Part.from_bytes(
            data=Path(f.path).read_bytes(), mime_type="image/png"))
    resp = client.models.generate_content(
        model=config.VISION_MODEL,
        contents=contents,
        config=types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT),
    )
    return (resp.text or "").strip()


def _generate_anthropic(batch: list[Frame]) -> str:
    """Anthropic Claude (paid)."""
    import anthropic

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    content: list[dict] = []
    for f in batch:
        content.append({"type": "text", "text": f"[frame @ {f.timestamp:.1f}s]"})
        data = base64.standard_b64encode(Path(f.path).read_bytes()).decode()
        content.append({"type": "image", "source": {
            "type": "base64", "media_type": "image/png", "data": data}})
    msg = client.messages.create(
        model=config.VISION_MODEL,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": content}],
    )
    return msg.content[0].text.strip()


# ── Clustering ─────────────────────────────────────────────────────────────────

def _cluster(raw: list[dict], keyframes: list[Frame]) -> tuple[list[Screen], list[Event]]:
    screens: dict[str, Screen] = {}
    events: list[Event] = []
    frame_by_ts = {round(f.timestamp, 1): f for f in keyframes}

    for item in raw:
        name = str(item.get("screen", "Unknown")).strip()
        ts = float(item.get("t", 0))
        if name not in screens:
            f = frame_by_ts.get(round(ts, 1))
            screens[name] = Screen(
                id=f"S{len(screens) + 1:02d}", name=name, type=item.get("type", "other"),
                elements=[str(e) for e in item.get("elements", [])][:6],
                representative_frame=f.index if f else 0,
            )
        screens[name].appearances.append(ts)
        events.append(Event(
            timestamp=ts, screen_id=screens[name].id,
            action=item.get("action", "wait"), target=str(item.get("target", "")),
            note="sensitive data visible" if item.get("sensitive") else "",
        ))

    # blank frames -> secure screen + secure events
    blanks = [f for f in keyframes if f.is_blank]
    if blanks:
        sid = f"S{len(screens) + 1:02d}"
        sec = Screen(id=sid, name="Secure input (capture blocked)", type="secure",
                     representative_frame=blanks[0].index,
                     appearances=[b.timestamp for b in blanks])
        screens[sec.name] = sec
        for b in blanks:
            events.append(Event(timestamp=b.timestamp, screen_id=sid, action="secure",
                                note="OS capture blocking (likely password/PIN entry)",
                                confidence="high"))

    events.sort(key=lambda e: e.timestamp)
    return list(screens.values()), events
