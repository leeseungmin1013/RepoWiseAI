from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Literal

VoiceAction = Literal[
    "stop",
    "mute",
    "next",
    "previous",
    "return",
    "understood",
    "needs_help",
    "skip",
    "submit_choice",
    "repeat",
    "concise",
]


@dataclass(frozen=True)
class VoiceCommandContext:
    has_current_lesson: bool = True
    has_previous_lesson: bool = False
    has_return_target: bool = False
    choice_ids: tuple[str, ...] = ()
    choice_labels: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ParsedVoiceCommand:
    action: VoiceAction | None
    confidence: float
    allowed: bool
    choice_id: str | None = None
    reason: str | None = None

    @property
    def is_confident(self) -> bool:
        return self.action is not None and self.confidence >= 0.98


_PHRASES: tuple[tuple[VoiceAction, tuple[str, ...]], ...] = (
    ("stop", ("멈춰", "말그만", "그만말해", "중단해")),
    ("mute", ("음소거", "마이크꺼", "마이크끄기")),
    ("return", ("원래레슨으로돌아가", "원래수업으로돌아가", "돌아가기")),
    ("understood", ("이해했어", "이해했어요", "알겠어", "알겠어요")),
    ("needs_help", ("아직어려워", "어려워요", "잘모르겠어", "도와줘")),
    ("skip", ("건너뛸래", "건너뛰기", "스킵", "넘어갈래")),
    ("next", ("다음", "다음레슨", "다음으로")),
    ("previous", ("이전", "이전레슨", "앞으로돌아가")),
    ("repeat", ("다시읽어줘", "다시말해줘", "한번더")),
    ("concise", ("짧게말해줘", "간단히말해줘", "요약해줘")),
)


def normalize_korean_command(transcript: str) -> str:
    normalized = unicodedata.normalize("NFKC", transcript).casefold()
    return re.sub(r"[^0-9a-z가-힣]+", "", normalized)


def parse_deterministic_command(
    transcript: str,
    context: VoiceCommandContext,
) -> ParsedVoiceCommand:
    normalized = normalize_korean_command(transcript)
    if not normalized:
        return ParsedVoiceCommand(None, 0.0, False, reason="empty transcript")

    choice_id = _resolve_choice(normalized, context)
    if choice_id is not None:
        return ParsedVoiceCommand(
            "submit_choice",
            1.0,
            bool(context.choice_ids),
            choice_id=choice_id,
            reason=None if context.choice_ids else "no active checkpoint choices",
        )

    for action, phrases in _PHRASES:
        if normalized not in phrases:
            continue
        allowed, reason = _allowed(action, context)
        return ParsedVoiceCommand(action, 1.0, allowed, reason=reason)
    return ParsedVoiceCommand(None, 0.0, False, reason="not a deterministic command")


def _resolve_choice(normalized: str, context: VoiceCommandContext) -> str | None:
    aliases = {
        "1": 0,
        "1번": 0,
        "일번": 0,
        "a": 0,
        "에이": 0,
        "2": 1,
        "2번": 1,
        "이번": 1,
        "b": 1,
        "비": 1,
        "3": 2,
        "3번": 2,
        "삼번": 2,
        "c": 2,
        "씨": 2,
        "4": 3,
        "4번": 3,
        "사번": 3,
        "d": 3,
        "디": 3,
    }
    index = aliases.get(normalized)
    if index is not None:
        return context.choice_ids[index] if index < len(context.choice_ids) else None
    for choice_id, label in context.choice_labels.items():
        if normalized == normalize_korean_command(label):
            return choice_id
    return None


def _allowed(action: VoiceAction, context: VoiceCommandContext) -> tuple[bool, str | None]:
    if action == "previous" and not context.has_previous_lesson:
        return False, "no previous lesson"
    if action == "return" and not context.has_return_target:
        return False, "no remediation return target"
    if action in {"next", "understood", "needs_help", "skip"} and not context.has_current_lesson:
        return False, "no current lesson"
    return True, None
