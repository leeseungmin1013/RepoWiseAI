"use client";

import type { KeyboardEvent, PointerEvent } from "react";

import type {
  RealtimeLearningSession,
  VoiceSessionStatus,
} from "@/hooks/useRealtimeLearningSession";

import styles from "./VoiceSessionDock.module.css";

type VoiceSessionDockProps = {
  session: RealtimeLearningSession;
  currentLessonLabel?: string;
  disabled?: boolean;
  className?: string;
};

const statusLabels: Record<VoiceSessionStatus, string> = {
  idle: "음성 대화를 시작할 수 있어요",
  connecting: "음성 연결 중",
  ready: "버튼을 누르고 말해 주세요",
  talking: "듣는 중 — 버튼을 놓으면 질문을 전송해요",
  reconnecting: "음성 연결 복구 중",
  stopping: "음성 대화 종료 중",
  stopped: "음성 대화가 종료됐어요",
  error: "음성 연결에 문제가 생겼어요",
};

function isPushToTalkKey(event: KeyboardEvent<HTMLButtonElement>) {
  return event.key === " " || event.key === "Enter";
}

export function VoiceSessionDock({
  session: {
    status,
    error,
    interimTranscript,
    isSupported,
    isConnected,
    isTalking,
    start,
    stop,
    startTalking,
    endTalking,
    remoteAudioRef,
  },
  currentLessonLabel,
  disabled = false,
  className,
}: VoiceSessionDockProps) {
  const active =
    status === "connecting" ||
    status === "ready" ||
    status === "talking" ||
    status === "reconnecting" ||
    status === "stopping";
  const canTalk =
    !disabled && (status === "ready" || status === "talking");

  const finishTalking = () => {
    if (isTalking) endTalking();
  };

  const handlePointerDown = (event: PointerEvent<HTMLButtonElement>) => {
    if (!canTalk || isTalking) return;
    event.preventDefault();
    event.currentTarget.setPointerCapture?.(event.pointerId);
    startTalking();
  };

  const handlePointerUp = (event: PointerEvent<HTMLButtonElement>) => {
    if (!isTalking) return;
    event.preventDefault();
    if (event.currentTarget.hasPointerCapture?.(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    endTalking();
  };

  return (
    <section
      aria-label="AI 음성 학습"
      className={[styles.dock, className].filter(Boolean).join(" ")}
    >
      <audio
        aria-hidden="true"
        autoPlay
        className={styles.remoteAudio}
        ref={remoteAudioRef}
      />

      <div className={styles.context}>
        <div className={styles.headingRow}>
          <strong>AI 음성 학습</strong>
          <span className={styles.disclosure}>AI가 생성한 음성</span>
        </div>
        {currentLessonLabel ? (
          <span className={styles.lesson} title={currentLessonLabel}>
            현재 학습: {currentLessonLabel}
          </span>
        ) : null}
        <span aria-live="polite" className={styles.status} role="status">
          <i
            aria-hidden="true"
            className={[
              styles.statusDot,
              isConnected ? styles.statusDotConnected : "",
              status === "error" ? styles.statusDotError : "",
            ]
              .filter(Boolean)
              .join(" ")}
          />
          {statusLabels[status]}
        </span>
        {interimTranscript ? (
          <span aria-live="polite" className={styles.transcript}>
            {interimTranscript}
          </span>
        ) : null}
        {error ? (
          <span className={styles.error} role="alert">
            {error.message}
          </span>
        ) : null}
        {!isSupported && status === "idle" ? (
          <span className={styles.error} role="status">
            이 브라우저에서는 마이크 기반 WebRTC를 사용할 수 없습니다.
          </span>
        ) : null}
      </div>

      <div className={styles.controls}>
        {active ? (
          <>
            <button
              aria-label={
                isTalking
                  ? "말하기 종료: 버튼을 놓으세요"
                  : "누르고 말하기"
              }
              aria-pressed={isTalking}
              className={[
                styles.talkButton,
                isTalking ? styles.talkButtonActive : "",
              ]
                .filter(Boolean)
                .join(" ")}
              disabled={!canTalk}
              onBlur={finishTalking}
              onKeyDown={(event) => {
                if (
                  isPushToTalkKey(event) &&
                  !event.repeat &&
                  canTalk &&
                  !isTalking
                ) {
                  event.preventDefault();
                  startTalking();
                }
              }}
              onKeyUp={(event) => {
                if (isPushToTalkKey(event) && isTalking) {
                  event.preventDefault();
                  endTalking();
                }
              }}
              onPointerCancel={finishTalking}
              onPointerDown={handlePointerDown}
              onPointerLeave={finishTalking}
              onPointerUp={handlePointerUp}
              type="button"
            >
              {isTalking ? "말하는 중" : "누르고 말하기"}
            </button>
            <button
              aria-label="음성 대화 종료"
              className={styles.stopButton}
              disabled={status === "stopping"}
              onClick={stop}
              type="button"
            >
              종료
            </button>
          </>
        ) : (
          <button
            className={styles.startButton}
            disabled={disabled || !isSupported}
            onClick={() => void start()}
            type="button"
          >
            음성 대화 시작
          </button>
        )}
      </div>
    </section>
  );
}
