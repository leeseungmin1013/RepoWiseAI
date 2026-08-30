import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useRealtimeLearningSession } from "./useRealtimeLearningSession";

class FakeDataChannel {
  readyState: RTCDataChannelState = "connecting";
  onmessage: ((event: MessageEvent) => void) | null = null;
  onopen: ((event: Event) => void) | null = null;
  onclose: ((event: Event) => void) | null = null;
  sent: string[] = [];

  close() {
    this.readyState = "closed";
  }

  open() {
    this.readyState = "open";
    this.onopen?.(new Event("open"));
  }

  receive(event: Record<string, unknown>) {
    this.onmessage?.(
      new MessageEvent("message", { data: JSON.stringify(event) }),
    );
  }

  send(data: string) {
    this.sent.push(data);
  }
}

class FakePeerConnection {
  connectionState: RTCPeerConnectionState = "new";
  localDescription: RTCSessionDescriptionInit | null = null;
  remoteDescription: RTCSessionDescriptionInit | null = null;
  onconnectionstatechange: (() => void) | null = null;
  ontrack: ((event: RTCTrackEvent) => void) | null = null;
  readonly dataChannel = new FakeDataChannel();
  readonly addTrack = vi.fn();
  readonly close = vi.fn(() => {
    this.connectionState = "closed";
  });

  createDataChannel() {
    return this.dataChannel as unknown as RTCDataChannel;
  }

  async createOffer(): Promise<RTCSessionDescriptionInit> {
    return { type: "offer", sdp: "browser-offer-sdp" };
  }

  async setLocalDescription(description: RTCSessionDescriptionInit) {
    this.localDescription = description;
  }

  async setRemoteDescription(description: RTCSessionDescriptionInit) {
    this.remoteDescription = description;
  }

  receiveTrack(stream: MediaStream, track: MediaStreamTrack) {
    this.ontrack?.({ streams: [stream], track } as unknown as RTCTrackEvent);
  }
}

function installMicrophone() {
  const microphoneTrack = {
    enabled: true,
    kind: "audio",
    stop: vi.fn(),
  } as unknown as MediaStreamTrack;
  const localStream = {
    getAudioTracks: () => [microphoneTrack],
    getTracks: () => [microphoneTrack],
  } as unknown as MediaStream;
  const getUserMedia = vi.fn().mockResolvedValue(localStream);

  Object.defineProperty(navigator, "mediaDevices", {
    configurable: true,
    value: { getUserMedia },
  });

  return { getUserMedia, localStream, microphoneTrack };
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("useRealtimeLearningSession", () => {
  it("connects with an SDP callback and commits push-to-talk audio", async () => {
    const { getUserMedia, microphoneTrack } = installMicrophone();
    const peer = new FakePeerConnection();
    const exchangeSdp = vi
      .fn()
      .mockResolvedValue({ sdp: "server-answer-sdp" });
    const onFinalTranscript = vi.fn();
    const { result } = renderHook(() =>
      useRealtimeLearningSession({
        exchangeSdp,
        onFinalTranscript,
        createPeerConnection: () =>
          peer as unknown as RTCPeerConnection,
      }),
    );

    await act(async () => {
      await result.current.start();
    });

    expect(getUserMedia).toHaveBeenCalledWith({ audio: true });
    expect(exchangeSdp).toHaveBeenCalledWith(
      "browser-offer-sdp",
      expect.any(AbortSignal),
      false,
    );
    expect(peer.remoteDescription).toEqual({
      type: "answer",
      sdp: "server-answer-sdp",
    });
    expect(microphoneTrack.enabled).toBe(false);
    expect(result.current.status).toBe("connecting");

    act(() => peer.dataChannel.open());
    expect(result.current.status).toBe("ready");

    act(() => result.current.startTalking());
    expect(microphoneTrack.enabled).toBe(true);
    expect(result.current.status).toBe("talking");
    expect(peer.dataChannel.sent.slice(0, 3).map((event) => JSON.parse(event))).toEqual([
      { type: "response.cancel" },
      { type: "output_audio_buffer.clear" },
      { type: "input_audio_buffer.clear" },
    ]);

    act(() => {
      peer.dataChannel.receive({
        type: "conversation.item.input_audio_transcription.delta",
        delta: "현재 ",
      });
      peer.dataChannel.receive({
        type: "conversation.item.input_audio_transcription.delta",
        delta: "코드는?",
      });
    });
    expect(result.current.interimTranscript).toBe("현재 코드는?");

    act(() => {
      peer.dataChannel.receive({
        type: "conversation.item.input_audio_transcription.completed",
        transcript: "현재 코드는?",
      });
    });
    expect(result.current.interimTranscript).toBe("");
    expect(onFinalTranscript).toHaveBeenCalledWith("현재 코드는?");

    act(() => result.current.endTalking());
    expect(microphoneTrack.enabled).toBe(false);
    expect(result.current.status).toBe("ready");
    expect(JSON.parse(peer.dataChannel.sent.at(-1) ?? "{}")).toEqual({
      type: "input_audio_buffer.commit",
    });
  });

  it("supports opt-in VAD and closes the persisted server session", async () => {
    const { microphoneTrack } = installMicrophone();
    const peer = new FakePeerConnection();
    const stopSession = vi.fn().mockResolvedValue({ status: "ended" });
    const exchangeSdp = vi.fn().mockResolvedValue({
      sdp: "server-answer-sdp",
      voiceSessionId: "voiceses_1",
      maxDurationSeconds: 180,
    });
    const { result } = renderHook(() =>
      useRealtimeLearningSession({
        exchangeSdp,
        stopSession,
        defaultVadEnabled: true,
        createPeerConnection: () => peer as unknown as RTCPeerConnection,
      }),
    );

    await act(async () => {
      await result.current.start();
    });

    expect(exchangeSdp).toHaveBeenCalledWith(
      "browser-offer-sdp",
      expect.any(AbortSignal),
      true,
    );
    expect(result.current.isVadEnabled).toBe(true);
    expect(microphoneTrack.enabled).toBe(true);

    act(() => peer.dataChannel.open());
    act(() => {
      peer.dataChannel.receive({
        type: "conversation.item.input_audio_transcription.completed",
        transcript: "중지",
      });
    });

    expect(result.current.status).toBe("stopped");
    expect(microphoneTrack.stop).toHaveBeenCalledOnce();
    expect(stopSession).toHaveBeenCalledOnce();
    expect(stopSession).toHaveBeenCalledWith("voiceses_1");
  });
  it("attaches remote audio, speaks only verified text, and releases resources", async () => {
    const { localStream, microphoneTrack } = installMicrophone();
    const peer = new FakePeerConnection();
    const { result } = renderHook(() =>
      useRealtimeLearningSession({
        exchangeSdp: async () => "server-answer-sdp",
        createPeerConnection: () =>
          peer as unknown as RTCPeerConnection,
      }),
    );
    const audio = document.createElement("audio");
    Object.defineProperty(audio, "srcObject", {
      configurable: true,
      value: null,
      writable: true,
    });
    audio.pause = vi.fn();

    act(() => result.current.remoteAudioRef(audio));
    await act(async () => {
      await result.current.start();
    });
    act(() => peer.dataChannel.open());
    act(() => peer.receiveTrack(localStream, microphoneTrack));
    expect(audio.srcObject).toBe(localStream);

    let sent = false;
    act(() => {
      sent = result.current.speakVerifiedText("검증된 짧은 설명입니다.");
    });
    expect(sent).toBe(true);
    expect(JSON.parse(peer.dataChannel.sent.at(-1) ?? "{}")).toMatchObject({
      type: "response.create",
      response: {
        conversation: "none",
        output_modalities: ["audio"],
      },
    });
    expect(peer.dataChannel.sent.at(-1)).toContain("검증된 짧은 설명입니다.");

    act(() => result.current.stop());
    expect(result.current.status).toBe("stopped");
    expect(result.current.connectionState).toBe("closed");
    expect(microphoneTrack.stop).toHaveBeenCalledOnce();
    expect(peer.close).toHaveBeenCalledOnce();
    expect(audio.pause).toHaveBeenCalledOnce();
    expect(audio.srcObject).toBeNull();
  });

  it("surfaces microphone permission failures and closes the peer", async () => {
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: {
        getUserMedia: vi
          .fn()
          .mockRejectedValue(new DOMException("denied", "NotAllowedError")),
      },
    });
    const peer = new FakePeerConnection();
    const { result } = renderHook(() =>
      useRealtimeLearningSession({
        exchangeSdp: async () => "unused",
        createPeerConnection: () =>
          peer as unknown as RTCPeerConnection,
      }),
    );

    await act(async () => {
      await result.current.start();
    });

    expect(result.current.status).toBe("error");
    expect(result.current.error?.message).toContain("마이크 권한");
    expect(peer.close).toHaveBeenCalledOnce();
  });
});
