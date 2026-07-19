"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  api,
  type DeepTask,
  type DeepTaskRequest,
  type DeepTaskResult,
} from "../lib/api";

export type DeepTaskEventSource = {
  onmessage: ((event: MessageEvent<string>) => void) | null;
  onerror: ((event: Event) => void) | null;
  addEventListener: (type: string, listener: EventListener) => void;
  removeEventListener: (type: string, listener: EventListener) => void;
  close: () => void;
};

type UseDeepLearningTaskOptions = {
  createTask?: (
    learningSessionId: string,
    input: DeepTaskRequest,
    idempotencyKey: string,
  ) => Promise<DeepTask>;
  getTask?: (taskId: string) => Promise<DeepTask>;
  cancelTask?: (taskId: string) => Promise<DeepTask>;
  eventsUrl?: (taskId: string) => string;
  createEventSource?: (url: string) => DeepTaskEventSource;
  pollIntervalMs?: number;
  onCompleted?: (
    answer: DeepTaskResult,
    task: DeepTask,
    request: DeepTaskRequest | null,
  ) => void;
};

export type DeepLearningTaskController = {
  task: DeepTask | null;
  error: string | null;
  isStarting: boolean;
  isRunning: boolean;
  isCancelling: boolean;
  start: (
    learningSessionId: string,
    request: DeepTaskRequest,
  ) => Promise<DeepTask | null>;
  reset: () => void;
  cancel: () => Promise<DeepTask | null>;
};

const terminalStatuses = new Set<DeepTask["status"]>([
  "completed",
  "failed",
  "cancelled",
]);
const deepTaskEventNames = [
  "queued",
  "running",
  "retrieving",
  "reasoning",
  "verifying",
  "completed",
  "failed",
  "cancelled",
] as const;

export function isDeepTaskTerminal(task: DeepTask) {
  return terminalStatuses.has(task.status);
}

function createIdempotencyKey() {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `deep-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function defaultEventSource(url: string): DeepTaskEventSource {
  if (typeof EventSource === "undefined") {
    throw new Error("EventSource is unavailable");
  }
  return new EventSource(url);
}

export function useDeepLearningTask({
  createTask = api.createDeepTask,
  getTask = api.getDeepTask,
  cancelTask = api.cancelDeepTask,
  eventsUrl = api.deepTaskEventsUrl,
  createEventSource = defaultEventSource,
  pollIntervalMs = 1_500,
  onCompleted,
}: UseDeepLearningTaskOptions = {}): DeepLearningTaskController {
  const [task, setTask] = useState<DeepTask | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isStarting, setIsStarting] = useState(false);
  const [isCancelling, setIsCancelling] = useState(false);

  const mountedRef = useRef(false);
  const taskRef = useRef<DeepTask | null>(null);
  const eventSourceRef = useRef<DeepTaskEventSource | null>(null);
  const eventListenerRef = useRef<EventListener | null>(null);
  const pollingTimerRef = useRef<number | null>(null);
  const pollingRequestRef = useRef(false);
  const generationRef = useRef(0);
  const lastSnapshotRef = useRef("");
  const completedTaskIdsRef = useRef(new Set<string>());
  const requestByTaskIdRef = useRef(new Map<string, DeepTaskRequest>());
  const requestKeyByTaskIdRef = useRef(new Map<string, string>());
  const idempotencyKeyByRequestRef = useRef(new Map<string, string>());
  const inFlightRef = useRef<{
    key: string;
    promise: Promise<DeepTask | null>;
  } | null>(null);

  const createTaskRef = useRef(createTask);
  const getTaskRef = useRef(getTask);
  const cancelTaskRef = useRef(cancelTask);
  const eventsUrlRef = useRef(eventsUrl);
  const eventSourceFactoryRef = useRef(createEventSource);
  const completedHandlerRef = useRef(onCompleted);
  const pollIntervalRef = useRef(pollIntervalMs);

  useEffect(() => {
    createTaskRef.current = createTask;
    getTaskRef.current = getTask;
    cancelTaskRef.current = cancelTask;
    eventsUrlRef.current = eventsUrl;
    eventSourceFactoryRef.current = createEventSource;
    completedHandlerRef.current = onCompleted;
    pollIntervalRef.current = pollIntervalMs;
  }, [
    createEventSource,
    createTask,
    cancelTask,
    eventsUrl,
    getTask,
    onCompleted,
    pollIntervalMs,
  ]);

  const cleanupTransports = useCallback(() => {
    const source = eventSourceRef.current;
    eventSourceRef.current = null;
    if (source) {
      if (eventListenerRef.current) {
        deepTaskEventNames.forEach((eventName) =>
          source.removeEventListener(eventName, eventListenerRef.current!),
        );
      }
      eventListenerRef.current = null;
      source.onmessage = null;
      source.onerror = null;
      source.close();
    }
    if (pollingTimerRef.current !== null) {
      window.clearInterval(pollingTimerRef.current);
      pollingTimerRef.current = null;
    }
    pollingRequestRef.current = false;
  }, []);

  const applyTask = useCallback(
    (nextTask: DeepTask) => {
      const fingerprint = JSON.stringify(nextTask);
      if (lastSnapshotRef.current === fingerprint) return;
      lastSnapshotRef.current = fingerprint;
      taskRef.current = nextTask;
      if (mountedRef.current) {
        setTask(nextTask);
        setError(null);
      }

      if (!isDeepTaskTerminal(nextTask)) return;
      cleanupTransports();

      if (
        nextTask.status === "completed" &&
        nextTask.result &&
        !completedTaskIdsRef.current.has(nextTask.id)
      ) {
        completedTaskIdsRef.current.add(nextTask.id);
        completedHandlerRef.current?.(
          nextTask.result,
          nextTask,
          requestByTaskIdRef.current.get(nextTask.id) ?? null,
        );
      }
      const requestKey = requestKeyByTaskIdRef.current.get(nextTask.id);
      if (requestKey) {
        idempotencyKeyByRequestRef.current.delete(requestKey);
        requestKeyByTaskIdRef.current.delete(nextTask.id);
      }
      requestByTaskIdRef.current.delete(nextTask.id);
    },
    [cleanupTransports],
  );

  const beginPolling = useCallback(
    (taskId: string) => {
      if (pollingTimerRef.current !== null) {
        window.clearInterval(pollingTimerRef.current);
      }

      const poll = async () => {
        if (
          pollingRequestRef.current ||
          taskRef.current?.id !== taskId ||
          isDeepTaskTerminal(taskRef.current)
        ) {
          return;
        }
        pollingRequestRef.current = true;
        try {
          const nextTask = await getTaskRef.current(taskId);
          if (mountedRef.current && taskRef.current?.id === taskId) {
            applyTask(nextTask);
          }
        } catch (reason) {
          if (mountedRef.current && taskRef.current?.id === taskId) {
            setError(
              reason instanceof Error
                ? reason.message
                : "심층 작업 진행 상태를 확인하지 못했습니다.",
            );
          }
        } finally {
          pollingRequestRef.current = false;
        }
      };

      void poll();
      pollingTimerRef.current = window.setInterval(
        () => void poll(),
        pollIntervalRef.current,
      );
    },
    [applyTask],
  );

  const subscribe = useCallback(
    (taskId: string) => {
      cleanupTransports();
      try {
        const source = eventSourceFactoryRef.current(
          eventsUrlRef.current(taskId),
        );
        eventSourceRef.current = source;
        const handleProgressEvent: EventListener = (event) => {
          if (taskRef.current?.id !== taskId) return;
          try {
            const data = (event as MessageEvent<string>).data;
            const nextTask = JSON.parse(data) as DeepTask;
            if (nextTask.id === taskId) applyTask(nextTask);
          } catch {
            // A malformed progress event must not terminate polling or the
            // underlying model task.
          }
        };
        eventListenerRef.current = handleProgressEvent;
        source.onmessage = handleProgressEvent as (
          event: MessageEvent<string>,
        ) => void;
        deepTaskEventNames.forEach((eventName) =>
          source.addEventListener(eventName, handleProgressEvent),
        );
        source.onerror = () => {
          if (eventSourceRef.current !== source) return;
          deepTaskEventNames.forEach((eventName) =>
            source.removeEventListener(eventName, handleProgressEvent),
          );
          eventListenerRef.current = null;
          source.onmessage = null;
          source.onerror = null;
          source.close();
          eventSourceRef.current = null;
          beginPolling(taskId);
        };
      } catch {
        beginPolling(taskId);
      }
    },
    [applyTask, beginPolling, cleanupTransports],
  );

  const reset = useCallback(() => {
    generationRef.current += 1;
    cleanupTransports();
    taskRef.current = null;
    lastSnapshotRef.current = "";
    requestKeyByTaskIdRef.current.clear();
    idempotencyKeyByRequestRef.current.clear();
    requestByTaskIdRef.current.clear();
    inFlightRef.current = null;
    if (mountedRef.current) {
      setTask(null);
      setError(null);
      setIsStarting(false);
      setIsCancelling(false);
    }
  }, [cleanupTransports]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      generationRef.current += 1;
      cleanupTransports();
    };
  }, [cleanupTransports]);

  const start = useCallback(
    (learningSessionId: string, request: DeepTaskRequest) => {
      const requestKey = JSON.stringify([learningSessionId, request]);
      if (inFlightRef.current?.key === requestKey) {
        return inFlightRef.current.promise;
      }
      if (taskRef.current && !isDeepTaskTerminal(taskRef.current)) {
        return Promise.resolve(taskRef.current);
      }

      const generation = generationRef.current + 1;
      generationRef.current = generation;
      lastSnapshotRef.current = "";
      cleanupTransports();
      if (mountedRef.current) {
        setError(null);
        setIsStarting(true);
      }

      const promise = (async (): Promise<DeepTask | null> => {
        try {
          const idempotencyKey =
            idempotencyKeyByRequestRef.current.get(requestKey) ??
            createIdempotencyKey();
          idempotencyKeyByRequestRef.current.set(requestKey, idempotencyKey);
          const created = await createTaskRef.current(
            learningSessionId,
            request,
            idempotencyKey,
          );
          if (!mountedRef.current || generationRef.current !== generation) {
            return null;
          }
          requestByTaskIdRef.current.set(created.id, request);
          requestKeyByTaskIdRef.current.set(created.id, requestKey);
          applyTask(created);
          if (!isDeepTaskTerminal(created)) subscribe(created.id);
          return created;
        } catch (reason) {
          if (mountedRef.current && generationRef.current === generation) {
            setError(
              reason instanceof Error
                ? reason.message
                : "심층 작업을 시작하지 못했습니다.",
            );
          }
          return null;
        } finally {
          if (mountedRef.current && generationRef.current === generation) {
            setIsStarting(false);
          }
          if (inFlightRef.current?.key === requestKey) {
            inFlightRef.current = null;
          }
        }
      })();

      inFlightRef.current = { key: requestKey, promise };
      return promise;
    },
    [applyTask, cleanupTransports, subscribe],
  );

  const cancel = useCallback(async (): Promise<DeepTask | null> => {
    const current = taskRef.current;
    if (!current || isDeepTaskTerminal(current) || isCancelling) return current;
    setIsCancelling(true);
    try {
      const cancelled = await cancelTaskRef.current(current.id);
      applyTask(cancelled);
      return cancelled;
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "심층 작업을 취소하지 못했습니다.",
      );
      return null;
    } finally {
      if (mountedRef.current) setIsCancelling(false);
    }
  }, [applyTask, isCancelling]);

  return {
    task,
    error,
    isStarting,
    isRunning: isStarting || Boolean(task && !isDeepTaskTerminal(task)),
    isCancelling,
    start,
    reset,
    cancel,
  };
}
