"""Step 4 — build screen transitions and a Mermaid flow diagram."""
from ..models import Event, Screen, Transition


def build_transitions(events: list[Event]) -> list[Transition]:
    transitions: list[Transition] = []
    prev: str | None = None
    for e in events:
        if prev is not None and e.screen_id != prev:
            transitions.append(Transition(from_screen=prev, to_screen=e.screen_id,
                                          timestamp=e.timestamp))
        prev = e.screen_id
    return transitions


def detect_backtracks(transitions: list[Transition]) -> list[tuple[str, str]]:
    """A->B followed later by B->A is a backtrack pair."""
    seen = {(t.from_screen, t.to_screen) for t in transitions}
    return sorted({(a, b) for (a, b) in seen if (b, a) in seen and a < b})


def to_mermaid(screens: list[Screen], transitions: list[Transition]) -> str:
    by_id = {s.id: s for s in screens}
    lines = ["flowchart TD"]
    for s in screens:
        label = s.name.replace('"', "'")
        if s.type == "secure":
            lines.append(f'    {s.id}["{label} 🔒"]')
            lines.append(f"    style {s.id} fill:#333,color:#fff")
        elif s.type in ("sheet", "confirm"):
            lines.append(f'    {s.id}{{{{"{label}"}}}}')
        else:
            lines.append(f'    {s.id}["{label}"]')

    backtracks = set(detect_backtracks(transitions))
    drawn: set[tuple[str, str]] = set()
    for t in transitions:
        key = (t.from_screen, t.to_screen)
        if key in drawn or t.from_screen not in by_id or t.to_screen not in by_id:
            continue
        drawn.add(key)
        pair = tuple(sorted(key))
        arrow = "-.->" if pair in backtracks else "-->"
        lines.append(f"    {t.from_screen} {arrow} {t.to_screen}")
    return "\n".join(lines)
