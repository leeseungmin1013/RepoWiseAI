"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export type VoiceSessionStatus =
  | "idle"
  | "connecting"
  | "ready"
  | "talking"
  | "reconnecting"
  | "stopping"
  | "stopped"
  | "error";

export type SdpAnswer = string | { sdp: string; voiceSessionId?: string; maxDurationSeconds?: number };

export type RealtimeEvent = Record<string, unknown>;

export type UseRealtimeLearningSessionOptions = {
  /**
   * Exchanges the browser-generated SDP offer for the server-generated SDP
   * answer. Keeping this callback injectable lets the owning workbench attach
   * authentication and learning-session context without coupling WebRTC to a
   * particular API client.
   */
  exchangeSdp: (
    offerSdp: string,
    signal: AbortSignal,
    vadEnabled: boolean,
  ) => Promise<SdpAnswer>;
  audioConstraints?: boolean | MediaTrackConstraints;
  rtcConfiguration?: RTCConfiguration;
  onRealtimeEvent?: (event: RealtimeEvent) => void;
  onFinalTranscript?: (transcript: string) => void;
  stopSession?: (voiceSessionId: string) => Promise<unknown>;
  defaultVadEnabled?: boolean;
  /** Test seam. Production callers should use the browser default. */
  createPeerConnection?: (configuration?: RTCConfiguration) => RTCPeerConnection;
  maxDurationSeconds?: number;
};

export type RealtimeLearningSession = {
  status: VoiceSessionStatus;
  connectionState: RTCPeerConnectionState;
  error: Error | null;
  interimTranscript: string;
  isSupported: boolean;
  isConnected: boolean;
  isTalking: boolean;
  isVadEnabled: boolean;
  start: () => Promise<void>;
  stop: () => void;
  startTalking: () => void;
  endTalking: () => void;
  setVadEnabled: (enabled: boolean) => void;
  sendEvent: (event: RealtimeEvent) => boolean;
  speakVerifiedText: (text: string) => boolean;
  remoteAudioRef: (element: HTMLAudioElement | null) => void;
};

function browserSupportsRealtimeVoice() {
  return (
    typeof window !== "undefined" &&
    typeof window.RTCPeerConnection !== "undefined" &&
    Boolean(navigator.mediaDevices?.getUserMedia)
  );
}

function normalizeAnswer(answer: SdpAnswer) {
  const sdp = typeof answer === "string" ? answer : answer.sdp;
  if (!sdp?.trim()) {
    throw new Error("음성 서버가 비어 있는 SDP 응답을 반환했습니다.");
  }
  return sdp;
}

function normalizeConnectionError(value: unknown) {
  if (value instanceof DOMException && value.name === "NotAllowedError") {
    return new Error(
      "마이크 권한이 거부되었습니다. 브라우저 설정에서 권한을 허용해 주세요.",
    );
  }
  if (value instanceof Error) {
    return value;
  }
  return new Error("음성 연결을 시작하지 못했습니다.");
}

export function useRealtimeLearningSession({
  exchangeSdp,
  audioConstraints = true,
  rtcConfiguration,
  onRealtimeEvent,
  onFinalTranscript,
  stopSession,
  defaultVadEnabled = false,
  createPeerConnection,
  maxDurationSeconds =
    Number(process.env.NEXT_PUBLIC_REALTIME_MAX_DURATION_SECONDS ?? 300) || 300,
}: UseRealtimeLearningSessionOptions): RealtimeLearningSession {
  const [status, setStatus] = useState<VoiceSessionStatus>("idle");
  const [connectionState, setConnectionState] =
    useState<RTCPeerConnectionState>("new");
  const [error, setError] = useState<Error | null>(null);
  const [interimTranscript, setInterimTranscript] = useState("");
  const [isVadEnabled, setIsVadEnabled] = useState(defaultVadEnabled);
  const [isSupported, setIsSupported] = useState(false);

  const statusRef = useRef<VoiceSessionStatus>("idle");
  const mountedRef = useRef(false);
  const peerRef = useRef<RTCPeerConnection | null>(null);
  const dataChannelRef = useRef<RTCDataChannel | null>(null);
  const localStreamRef = useRef<MediaStream | null>(null);
  const microphoneTrackRef = useRef<MediaStreamTrack | null>(null);
  const remoteStreamRef = useRef<MediaStream | null>(null);
  const remoteAudioElementRef = useRef<HTMLAudioElement | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const durationTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const voiceSessionIdRef = useRef<string | null>(null);
  const stopRef = useRef<() => void>(() => undefined);

  const exchangeSdpRef = useRef(exchangeSdp);
  const eventHandlerRef = useRef(onRealtimeEvent);
  const finalTranscriptHandlerRef = useRef(onFinalTranscript);
  const constraintsRef = useRef(audioConstraints);
  const rtcConfigurationRef = useRef(rtcConfiguration);
  const peerFactoryRef = useRef(createPeerConnection);
  const stopSessionRef = useRef(stopSession);
  const vadEnabledRef = useRef(defaultVadEnabled);

  useEffect(() => {
    exchangeSdpRef.current = exchangeSdp;
    eventHandlerRef.current = onRealtimeEvent;
    finalTranscriptHandlerRef.current = onFinalTranscript;
    constraintsRef.current = audioConstraints;
    rtcConfigurationRef.current = rtcConfiguration;
    peerFactoryRef.current = createPeerConnection;
    stopSessionRef.current = stopSession;
  }, [
    audioConstraints,
    createPeerConnection,
    exchangeSdp,
    onFinalTranscript,
    onRealtimeEvent,
    rtcConfiguration,
    stopSession,
  ]);

  const updateStatus = useCallback((nextStatus: VoiceSessionStatus) => {
    statusRef.current = nextStatus;
    if (mountedRef.current) {
      setStatus(nextStatus);
    }
  }, []);

  const disposeResources = useCallback(() => {
    const voiceSessionId = voiceSessionIdRef.current;
    voiceSessionIdRef.current = null;
    if (voiceSessionId) {
      void stopSessionRef.current?.(voiceSessionId).catch(() => undefined);
    }
    if (durationTimerRef.current) {
      clearTimeout(durationTimerRef.current);
      durationTimerRef.current = null;
    }
    abortControllerRef.current?.abort();
    abortControllerRef.current = null;

    const dataChannel = dataChannelRef.current;
    dataChannelRef.current = null;
    if (dataChannel) {
      dataChannel.onmessage = null;
      dataChannel.onopen = null;
      dataChannel.onclose = null;
      dataChannel.close();
    }

    const peer = peerRef.current;
    peerRef.current = null;
    if (peer) {
      peer.ontrack = null;
      peer.onconnectionstatechange = null;
      peer.close();
    }

    microphoneTrackRef.current = null;
    localStreamRef.current?.getTracks().forEach((track) => track.stop());
    localStreamRef.current = null;
    remoteStreamRef.current = null;

    const audio = remoteAudioElementRef.current;
    if (audio) {
      if (audio.srcObject) audio.pause();
      audio.srcObject = null;
    }
  }, []);

  const fail = useCallback(
    (value: unknown) => {
      const nextError = normalizeConnectionError(value);
      disposeResources();
      if (mountedRef.current) {
        setError(nextError);
        setConnectionState("failed");
      }
      updateStatus("error");
    },
    [disposeResources, updateStatus],
  );

  useEffect(() => {
    mountedRef.current = true;
    setIsSupported(
      Boolean(peerFactoryRef.current) || browserSupportsRealtimeVoice(),
    );
    return () => {
      mountedRef.current = false;
      disposeResources();
    };
  }, [disposeResources]);

  const remoteAudioRef = useCallback((element: HTMLAudioElement | null) => {
    const previous = remoteAudioElementRef.current;
    if (previous && previous !== element) {
      previous.srcObject = null;
    }
    remoteAudioElementRef.current = element;
    if (element && remoteStreamRef.current) {
      element.srcObject = remoteStreamRef.current;
    }
  }, []);

  const start = useCallback(async () => {
    if (
      statusRef.current === "connecting" ||
      statusRef.current === "ready" ||
      statusRef.current === "talking" ||
      statusRef.current === "reconnecting"
    ) {
      return;
    }

    const supported =
      Boolean(peerFactoryRef.current) || browserSupportsRealtimeVoice();
    if (!supported || !navigator.mediaDevices?.getUserMedia) {
      fail(new Error("이 브라우저는 WebRTC 음성 대화를 지원하지 않습니다."));
      return;
    }

    disposeResources();
    if (mountedRef.current) {
      setError(null);
      setConnectionState("new");
    }
    updateStatus("connecting");

    const abortController = new AbortController();
    abortControllerRef.current = abortController;

    try {
      const peer = peerFactoryRef.current
        ? peerFactoryRef.current(rtcConfigurationRef.current)
        : new RTCPeerConnection(rtcConfigurationRef.current);
      peerRef.current = peer;

      peer.onconnectionstatechange = () => {
        if (peerRef.current !== peer) return;
        const nextConnectionState = peer.connectionState;
        if (mountedRef.current) {
          setConnectionState(nextConnectionState);
        }
        if (nextConnectionState === "failed") {
          fail(new Error("WebRTC 음성 연결에 실패했습니다."));
        } else if (nextConnectionState === "disconnected") {
          updateStatus("reconnecting");
        } else if (
          nextConnectionState === "connected" &&
          statusRef.current === "reconnecting"
        ) {
          updateStatus("ready");
        }
      };

      peer.ontrack = (event) => {
        if (peerRef.current !== peer) return;
        const remoteStream =
          event.streams[0] ?? new MediaStream([event.track]);
        remoteStreamRef.current = remoteStream;
        if (remoteAudioElementRef.current) {
          remoteAudioElementRef.current.srcObject = remoteStream;
        }
      };

      const localStream = await navigator.mediaDevices.getUserMedia({
        audio: constraintsRef.current,
      });
      if (peerRef.current !== peer || abortController.signal.aborted) {
        localStream.getTracks().forEach((track) => track.stop());
        return;
      }
      localStreamRef.current = localStream;

      const microphoneTrack = localStream.getAudioTracks()[0];
      if (!microphoneTrack) {
        throw new Error("사용 가능한 마이크 오디오 트랙을 찾지 못했습니다.");
      }
      microphoneTrack.enabled = vadEnabledRef.current;
      microphoneTrackRef.current = microphoneTrack;
      peer.addTrack(microphoneTrack, localStream);

      const dataChannel = peer.createDataChannel("oai-events");
      dataChannelRef.current = dataChannel;
      dataChannel.onopen = () => {
        if (peerRef.current === peer && statusRef.current === "connecting") {
          updateStatus("ready");
        }
      };
      dataChannel.onclose = () => {
        if (
          peerRef.current === peer &&
          statusRef.current !== "stopping" &&
          statusRef.current !== "stopped"
        ) {
          fail(new Error("Realtime 이벤트 채널 연결이 종료되었습니다."));
        }
      };
      dataChannel.onmessage = (message) => {
        if (typeof message.data !== "string") return;
        try {
          const event = JSON.parse(message.data) as RealtimeEvent;
          if (
            event.type ===
              "conversation.item.input_audio_transcription.delta" &&
            typeof event.delta === "string"
          ) {
            setInterimTranscript((current) => current + event.delta);
          }
          if (
            event.type ===
              "conversation.item.input_audio_transcription.completed" &&
            typeof event.transcript === "string"
          ) {
            const transcript = event.transcript.trim();
            setInterimTranscript("");
            if (transcript) {
              const normalized = transcript
                .normalize("NFKC")
                .replace(/[\s.,!?~。！？]+/g, "")
                .toLowerCase();
              if (["중지", "종료", "그만", "stop"].includes(normalized)) {
                stopRef.current();
                return;
              }
              if (["음소거", "마이크꺼", "mute"].includes(normalized)) {
                if (microphoneTrackRef.current) {
                  microphoneTrackRef.current.enabled = false;
                }
                dataChannel.send(JSON.stringify({ type: "response.cancel" }));
                dataChannel.send(
                  JSON.stringify({ type: "output_audio_buffer.clear" }),
                );
                updateStatus("ready");
                return;
              }
              finalTranscriptHandlerRef.current?.(transcript);
            }
          }
          eventHandlerRef.current?.(event);
        } catch {
          // Realtime events are JSON. Ignore malformed application data rather
          // than taking down an otherwise healthy audio connection.
        }
      };

      const offer = await peer.createOffer();
      await peer.setLocalDescription(offer);
      if (!offer.sdp) {
        throw new Error("WebRTC SDP offer를 만들지 못했습니다.");
      }

      const answer = await exchangeSdpRef.current(
        offer.sdp,
        abortController.signal,
        vadEnabledRef.current,
      );
      if (peerRef.current !== peer || abortController.signal.aborted) return;
      if (typeof answer !== "string" && answer.voiceSessionId) {
        voiceSessionIdRef.current = answer.voiceSessionId;
      }

      await peer.setRemoteDescription({
        type: "answer",
        sdp: normalizeAnswer(answer),
      });
      if (peerRef.current !== peer || abortController.signal.aborted) return;

      if (mountedRef.current) {
        setConnectionState(peer.connectionState);
      }
      if (dataChannel.readyState === "open") {
        updateStatus("ready");
      }
      durationTimerRef.current = setTimeout(() => {
        if (peerRef.current !== peer) return;
        disposeResources();
        if (mountedRef.current) setConnectionState("closed");
        updateStatus("stopped");
      },
      Math.max(
        1,
        typeof answer === "string"
          ? maxDurationSeconds
          : answer.maxDurationSeconds ?? maxDurationSeconds,
      ) * 1000,
      );
    } catch (value) {
      if (!abortController.signal.aborted) {
        fail(value);
      }
    }
  }, [disposeResources, fail, maxDurationSeconds, updateStatus]);

  const sendEvent = useCallback((event: RealtimeEvent) => {
    const dataChannel = dataChannelRef.current;
    if (!dataChannel || dataChannel.readyState !== "open") return false;
    dataChannel.send(JSON.stringify(event));
    return true;
  }, []);

  const startTalking = useCallback(() => {
    const track = microphoneTrackRef.current;
    if (
      !track ||
      statusRef.current !== "ready" ||
      vadEnabledRef.current
    ) return;
    setInterimTranscript("");
    sendEvent({ type: "response.cancel" });
    sendEvent({ type: "output_audio_buffer.clear" });
    sendEvent({ type: "input_audio_buffer.clear" });
    track.enabled = true;
    updateStatus("talking");
  }, [sendEvent, updateStatus]);

  const endTalking = useCallback(() => {
    const track = microphoneTrackRef.current;
    if (track) track.enabled = false;
    if (statusRef.current === "talking") {
      sendEvent({ type: "input_audio_buffer.commit" });
      updateStatus("ready");
    }
  }, [sendEvent, updateStatus]);

  const setVadEnabled = useCallback((enabled: boolean) => {
    if (
      statusRef.current !== "idle" &&
      statusRef.current !== "stopped" &&
      statusRef.current !== "error"
    ) return;
    vadEnabledRef.current = enabled;
    setIsVadEnabled(enabled);
  }, []);

  const stop = useCallback(() => {
    if (
      statusRef.current === "idle" ||
      statusRef.current === "stopped" ||
      statusRef.current === "stopping"
    ) {
      return;
    }
    updateStatus("stopping");
    disposeResources();
    if (mountedRef.current) {
      setError(null);
      setConnectionState("closed");
    }
    updateStatus("stopped");
  }, [disposeResources, updateStatus]);

  useEffect(() => {
    stopRef.current = stop;
  }, [stop]);

  const speakVerifiedText = useCallback(
    (text: string) => {
      const verifiedText = text.trim();
      if (!verifiedText) return false;
      return sendEvent({
        type: "response.create",
        response: {
          conversation: "none",
          output_modalities: ["audio"],
          instructions: [
            "다음은 서버가 근거를 확인한 학습 답변입니다.",
            "새로운 사실을 추가하거나 내용을 바꾸지 말고 한국어로 자연스럽게 읽으세요.",
            verifiedText,
          ].join("\n\n"),
        },
      });
    },
    [sendEvent],
  );

  return {
    status,
    connectionState,
    error,
    interimTranscript,
    isSupported,
    isConnected:
      status === "ready" ||
      status === "talking" ||
      status === "reconnecting",
    isTalking: status === "talking",
    isVadEnabled,
    start,
    stop,
    startTalking,
    endTalking,
    setVadEnabled,
    sendEvent,
    speakVerifiedText,
    remoteAudioRef,
  };
}
