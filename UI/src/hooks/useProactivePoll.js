import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api";

export function useProactivePoll({ sessionId, onMessages, onArrival }) {
  const inFlight = useRef(false);
  const seen = useRef(new Set());
  const arrivalTarget = useRef(null);
  const emphasizeNext = useRef(false);
  const arrivalSource = useRef("poll");
  const highlightTimer = useRef(null);
  const [highlightedId, setHighlightedId] = useState(null);

  const poll = useCallback(async () => {
    if (inFlight.current || document.hidden) return;
    inFlight.current = true;
    try {
      const payload = await api.pendingProactive(sessionId);
      const fresh = (payload.messages || []).filter((message) => {
        if (!message.message_id || seen.current.has(message.message_id)) return false;
        seen.current.add(message.message_id);
        return true;
      });
      if (!fresh.length) return;
      onMessages(fresh);
      onArrival?.(fresh, arrivalSource.current);

      let arrival = fresh.find(
        (message) => message.message_id === arrivalTarget.current,
      );
      if (!arrival && emphasizeNext.current) arrival = fresh[fresh.length - 1];
      if (!arrival) arrival = fresh[fresh.length - 1];
      if (arrival) {
        setHighlightedId(arrival.message_id);
        window.clearTimeout(highlightTimer.current);
        highlightTimer.current = window.setTimeout(() => setHighlightedId(null), 5000);
      }
      arrivalTarget.current = null;
      emphasizeNext.current = false;
      arrivalSource.current = "poll";
    } catch {
      // Polling is intentionally quiet; the next visibility event or interval retries.
    } finally {
      inFlight.current = false;
    }
  }, [onArrival, onMessages, sessionId]);

  useEffect(() => {
    poll();
    const timer = window.setInterval(poll, 5000);
    const onVisibility = () => {
      if (!document.hidden) poll();
    };
    const onServiceWorkerMessage = (event) => {
      if (event.data?.type !== "proactive-push" && event.data?.type !== "notification-opened") return;
      arrivalTarget.current = event.data.message_id || null;
      emphasizeNext.current = true;
      arrivalSource.current = event.data.type === "notification-opened" ? "notification" : "push";
      poll();
    };
    document.addEventListener("visibilitychange", onVisibility);
    navigator.serviceWorker?.addEventListener("message", onServiceWorkerMessage);
    return () => {
      window.clearInterval(timer);
      window.clearTimeout(highlightTimer.current);
      document.removeEventListener("visibilitychange", onVisibility);
      navigator.serviceWorker?.removeEventListener("message", onServiceWorkerMessage);
    };
  }, [poll]);

  return { highlightedId, pollNow: poll };
}
