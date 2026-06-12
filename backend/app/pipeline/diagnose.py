"""Step 5 — UX findings: deterministic heuristics + optional LLM narrative."""
from collections import Counter

from ..models import Event, Finding, Screen, Transition
from .flow import detect_backtracks

LONG_DWELL_FACTOR = 2.5  # dwell longer than 2.5x median is flagged


def heuristics(screens: list[Screen], events: list[Event],
               transitions: list[Transition], duration: float) -> list[Finding]:
    findings: list[Finding] = []
    by_id = {s.id: s for s in screens}

    # 1) long dwell per screen visit
    dwells: list[tuple[str, float, float]] = []  # (screen_id, start, dwell)
    for i, e in enumerate(events):
        end = events[i + 1].timestamp if i + 1 < len(events) else duration
        dwells.append((e.screen_id, e.timestamp, end - e.timestamp))
    per_visit = [d for _, _, d in dwells if d > 0]
    if per_visit:
        median = sorted(per_visit)[len(per_visit) // 2]
        for sid, start, d in dwells:
            if median > 0 and d > median * LONG_DWELL_FACTOR and d > 8:
                s = by_id.get(sid)
                findings.append(Finding(
                    severity="mid",
                    title=f"Long dwell on '{s.name if s else sid}' ({d:.0f}s)",
                    evidence=f"{d:.0f}s vs median {median:.0f}s per visit",
                    timestamps=[start],
                    suggestion="Check whether users hesitate here (unclear copy, too many options).",
                ))

    # 2) backtracking (overlay round-trips like sheets/modals are excluded)
    for a, b in detect_backtracks(transitions, screens):
        sa, sb = by_id.get(a), by_id.get(b)
        findings.append(Finding(
            severity="mid",
            title=f"Backtracking between '{sa.name if sa else a}' and '{sb.name if sb else b}'",
            evidence="User navigated forward and returned to the previous screen.",
            suggestion="Consider surfacing the missing information earlier to avoid round-trips.",
        ))

    # 3) repeated visits
    visits = Counter(t.to_screen for t in transitions)
    for sid, n in visits.items():
        if n >= 3:
            s = by_id.get(sid)
            findings.append(Finding(
                severity="low",
                title=f"Screen '{s.name if s else sid}' re-entered {n} times",
                evidence=f"{n} entries during one session",
                suggestion="Frequent re-entry can signal a hub working well — or users getting lost.",
            ))

    # 4) error/loading screens
    for s in screens:
        if s.type in ("error", "loading"):
            findings.append(Finding(
                severity="low" if s.type == "loading" else "high",
                title=f"{s.type.capitalize()} screen observed: '{s.name}'",
                evidence=f"appearances at {', '.join(f'{t:.0f}s' for t in s.appearances[:5])}",
                timestamps=s.appearances[:5],
                suggestion="Skeleton UI for loading; recovery guidance for errors.",
            ))

    # 5) secure (capture-blocked) sections — informational
    for s in screens:
        if s.type == "secure":
            findings.append(Finding(
                severity="info",
                title="Capture-blocked (secure) section detected",
                evidence=f"black frames at {', '.join(f'{t:.0f}s' for t in s.appearances[:5])}",
                timestamps=s.appearances[:5],
                suggestion="Likely password/PIN entry. Actions in this section cannot be analyzed.",
            ))

    # 6) sensitive data exposure
    sensitive_ts = [e.timestamp for e in events if "sensitive" in e.note]
    if sensitive_ts:
        findings.append(Finding(
            severity="high",
            title="Sensitive data visible in recording",
            evidence=f"account numbers/balances/names visible at "
                     f"{', '.join(f'{t:.0f}s' for t in sensitive_ts[:5])}",
            timestamps=sensitive_ts[:5],
            suggestion="Share this recording carefully; enable masking before distribution.",
        ))

    order = {"high": 0, "mid": 1, "low": 2, "info": 3}
    findings.sort(key=lambda f: order[f.severity])
    return findings
