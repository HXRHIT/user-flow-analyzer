"""Step 4 — build screen transitions and a Mermaid flow diagram.

Overlays (bottom sheets, modals, keypads, confirm dialogs) naturally produce
parent -> overlay -> parent round-trips when opened and closed. Those are normal
interactions, not navigation cycles, so the diagram draws only the opening edge
and backtrack detection ignores overlay round-trips.
"""
from ..models import Event, Screen, Transition

OVERLAY_TYPES = {"sheet", "keypad", "confirm", "survey", "loading", "secure"}


def build_transitions(events: list[Event]) -> list[Transition]:
    transitions: list[Transition] = []
    prev: str | None = None
    for e in events:
        if prev is not None and e.screen_id != prev:
            transitions.append(Transition(from_screen=prev, to_screen=e.screen_id,
                                          timestamp=e.timestamp))
        prev = e.screen_id
    return transitions


def _overlay_ids(screens: list[Screen] | None) -> set[str]:
    return {s.id for s in screens or [] if s.type in OVERLAY_TYPES}


def detect_backtracks(transitions: list[Transition],
                      screens: list[Screen] | None = None) -> list[tuple[str, str]]:
    """A->B followed later by B->A is a backtrack pair — unless one side is an overlay
    (opening and closing a sheet/modal is not backtracking)."""
    overlays = _overlay_ids(screens)
    seen = {(t.from_screen, t.to_screen) for t in transitions}
    return sorted({(a, b) for (a, b) in seen
                   if (b, a) in seen and a < b and a not in overlays and b not in overlays})


def to_mermaid(screens: list[Screen], transitions: list[Transition]) -> str:
    by_id = {s.id: s for s in screens}
    overlays = _overlay_ids(screens)
    lines = ["flowchart TD"]
    for s in screens:
        label = s.name.replace('"', "'")
        if s.type == "secure":
            lines.append(f'    {s.id}["{label} 🔒"]')
            lines.append(f"    style {s.id} fill:#333,color:#fff")
        elif s.id in overlays:
            lines.append(f'    {s.id}{{{{"{label}"}}}}')
        else:
            lines.append(f'    {s.id}["{label}"]')

    pairs = {(t.from_screen, t.to_screen) for t in transitions}
    backtracks = set(detect_backtracks(transitions, screens))
    drawn: set[tuple[str, str]] = set()
    for t in transitions:
        key = (t.from_screen, t.to_screen)
        if key in drawn or t.from_screen not in by_id or t.to_screen not in by_id:
            continue
        # closing an overlay back to the screen that opened it → skip the return edge
        if t.from_screen in overlays and (t.to_screen, t.from_screen) in pairs:
            continue
        drawn.add(key)
        pair = tuple(sorted(key))
        arrow = "-.->" if pair in backtracks else "-->"
        lines.append(f"    {t.from_screen} {arrow} {t.to_screen}")
    return "\n".join(lines)
