"""Step 3 — screen recognition with the Claude vision API.

Keyframes are sent in timestamp order (batched) and the model returns, per frame:
screen name, screen type, notable UI elements, the inferred user action since the
previous frame, and whether sensitive data (account numbers, balances, names) is
visible. Frames sharing the same screen name are clustered into unique screens.
"""
import base64
import json
from pathlib import Path

import anthropic

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


def _img_block(path: str) -> dict:
    data = base64.standard_b64encode(Path(path).read_bytes()).decode()
    return {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": data}}


def recognize(keyframes: list[Frame], progress_cb=None) -> tuple[list[Screen], list[Event]]:
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    visible = [f for f in keyframes if not f.is_blank][: config.MAX_KEYFRAMES_TO_LLM]
    raw: list[dict] = []

    for start in range(0, len(visible), BATCH_SIZE):
        batch = visible[start : start + BATCH_SIZE]
        content: list[dict] = []
        for f in batch:
            content.append({"type": "text", "text": f"[frame @ {f.timestamp:.1f}s]"})
            content.append(_img_block(f.path))
        msg = client.messages.create(
            model=config.VISION_MODEL,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": content}],
        )
        text = msg.content[0].text.strip()
        text = text[text.find("[") : text.rfind("]") + 1]  # tolerate stray prose
        raw.extend(json.loads(text))
        if progress_cb:
            progress_cb(min(start + BATCH_SIZE, len(visible)), len(visible))

    return _cluster(raw, keyframes)


def _cluster(raw: list[dict], keyframes: list[Frame]) -> tuple[list[Screen], list[Event]]:
    screens: dict[str, Screen] = {}
    events: list[Event] = []
    frame_by_ts = {round(f.timestamp, 1): f for f in keyframes}

    for item in raw:
        name = str(item.get("screen", "Unknown")).strip()
        ts = float(item.get("t", 0))
        sid = f"S{list(screens).index(name) + 1:02d}" if name in screens else f"S{len(screens) + 1:02d}"
        if name not in screens:
            f = frame_by_ts.get(round(ts, 1))
            screens[name] = Screen(
                id=sid, name=name, type=item.get("type", "other"),
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
