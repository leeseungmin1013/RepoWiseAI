from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from math import ceil


def _p95(values: Iterable[int]) -> int:
    measured = sorted(int(value) for value in values if int(value) > 0)
    if not measured:
        return 0
    return measured[max(0, ceil(len(measured) * 0.95) - 1)]


def summarize_voice_metrics(sessions, turns, usage_events) -> dict:
    sessions = list(sessions)
    turns = list(turns)
    usage_events = list(usage_events)
    connected_statuses = {"active", "reconnecting", "ended"}
    connected = sum(session.status in connected_statuses for session in sessions)
    usage_totals = Counter()
    for event in usage_events:
        for key, value in (event.usage_json or {}).items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                usage_totals[key] += value
    return {
        "sessions": {
            "total": len(sessions),
            "connected": connected,
            "failed": sum(session.status == "failed" for session in sessions),
            "success_rate": round(connected / len(sessions), 4) if sessions else 0.0,
            "disconnect_reasons": dict(
                Counter(
                    session.disconnect_reason for session in sessions if session.disconnect_reason
                )
            ),
        },
        "turns": {
            "total": len(turns),
            "routes": dict(Counter(turn.route or "unclassified" for turn in turns)),
            "tools": dict(Counter(turn.tool_name for turn in turns if turn.tool_name)),
            "interrupted": sum(bool(turn.interrupted) for turn in turns),
        },
        "latency_p95_ms": {
            "speech_end_to_ack": _p95(turn.speech_end_to_ack_ms for turn in turns),
            "first_audio": _p95(turn.first_audio_ms for turn in turns),
            "completed": _p95(turn.completed_ms for turn in turns),
        },
        "usage": {
            "settled_cost_micro_usd": sum(
                int(event.settled_cost_micro_usd or 0) for event in usage_events
            ),
            "audio_duration_ms": sum(int(turn.audio_duration_ms or 0) for turn in turns),
            "provider": dict(usage_totals),
        },
    }
