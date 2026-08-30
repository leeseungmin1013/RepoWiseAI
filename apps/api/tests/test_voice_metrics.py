from types import SimpleNamespace

from app.services.voice_metrics import summarize_voice_metrics


def test_voice_metrics_summarizes_routes_latency_usage_and_failures():
    sessions = [
        SimpleNamespace(status="ended", disconnect_reason="user_stopped"),
        SimpleNamespace(status="active", disconnect_reason=None),
        SimpleNamespace(status="failed", disconnect_reason="sideband_failed"),
    ]
    turns = [
        SimpleNamespace(
            route="grounded_answer",
            tool_name="answer_with_repository_evidence",
            interrupted=False,
            speech_end_to_ack_ms=400,
            first_audio_ms=800,
            completed_ms=1800,
            audio_duration_ms=1200,
        ),
        SimpleNamespace(
            route="deterministic_command",
            tool_name="apply_learning_action",
            interrupted=True,
            speech_end_to_ack_ms=900,
            first_audio_ms=1400,
            completed_ms=2600,
            audio_duration_ms=500,
        ),
    ]
    events = [
        SimpleNamespace(
            settled_cost_micro_usd=120,
            usage_json={"audio_input_seconds": 2.5, "input_tokens": 30},
        ),
        SimpleNamespace(
            settled_cost_micro_usd=80,
            usage_json={"audio_input_seconds": 1.5, "output_tokens": 12},
        ),
    ]

    report = summarize_voice_metrics(sessions, turns, events)

    assert report["sessions"] == {
        "total": 3,
        "connected": 2,
        "failed": 1,
        "success_rate": 0.6667,
        "disconnect_reasons": {"user_stopped": 1, "sideband_failed": 1},
    }
    assert report["turns"]["routes"] == {
        "grounded_answer": 1,
        "deterministic_command": 1,
    }
    assert report["turns"]["interrupted"] == 1
    assert report["latency_p95_ms"] == {
        "speech_end_to_ack": 900,
        "first_audio": 1400,
        "completed": 2600,
    }
    assert report["usage"] == {
        "settled_cost_micro_usd": 200,
        "audio_duration_ms": 1700,
        "provider": {
            "audio_input_seconds": 4.0,
            "input_tokens": 30,
            "output_tokens": 12,
        },
    }


def test_voice_session_id_header_is_cors_exposed():
    from app.main import app

    cors = next(
        middleware
        for middleware in app.user_middleware
        if middleware.cls.__name__ == "CORSMiddleware"
    )
    assert "X-RepoWise-Voice-Session-Id" in cors.kwargs["expose_headers"]
