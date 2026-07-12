"use client";

// Global SSE bridge: one EventSource for the whole app. Persists nothing —
// the control plane's run_events table is the source of truth; this only
// accelerates the UI (queries re-fetch on relevant events).

import { createContext, useContext, useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { API_URL } from "@/lib/api";
import type { RunEvent } from "@/lib/types";

interface LiveEvents {
  recent: RunEvent[];
  connected: boolean;
}

const EventsContext = createContext<LiveEvents>({ recent: [], connected: false });

export function useLiveEvents() {
  return useContext(EventsContext);
}

const INVALIDATE_MAP: Record<string, string[][]> = {
  "run.queued": [["runs"], ["briefing"]],
  "agent.status_changed": [["runs"], ["briefing"]],
  "approval.required": [["approvals"], ["briefing"], ["runs"]],
  "approval.resolved": [["approvals"], ["briefing"], ["runs"]],
  "artifact.created": [["artifacts"]],
  "memory.proposed": [["memories"]],
  "run.completed": [["runs"], ["briefing"], ["artifacts"], ["usage"]],
  "run.failed": [["runs"], ["briefing"]],
  "run.cancelled": [["runs"], ["briefing"]],
  "verification.completed": [["runs"]],
};

export function EventsProvider({ children }: { children: React.ReactNode }) {
  const queryClient = useQueryClient();
  const [recent, setRecent] = useState<RunEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const sourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    let cancelled = false;

    function connect() {
      if (cancelled) return;
      const source = new EventSource(`${API_URL}/api/v1/events/stream`);
      sourceRef.current = source;
      source.onopen = () => setConnected(true);
      source.onerror = () => {
        setConnected(false);
        source.close();
        if (!cancelled) setTimeout(connect, 3000); // EventSource-style retry with backfill on server
      };
      source.onmessage = (message) => {
        try {
          const event = JSON.parse(message.data) as RunEvent;
          if (event.human_text) {
            setRecent((prev) => [event, ...prev].slice(0, 60));
          }
          for (const key of INVALIDATE_MAP[event.type] ?? []) {
            queryClient.invalidateQueries({ queryKey: key });
          }
          // per-run streams key on ["run-events", run_id]
          queryClient.invalidateQueries({ queryKey: ["run-events", event.run_id] });
          if (["run.completed", "run.failed", "run.cancelled", "agent.status_changed"].includes(event.type)) {
            queryClient.invalidateQueries({ queryKey: ["run", event.run_id] });
          }
        } catch {
          /* keepalive comments are not JSON */
        }
      };
    }

    connect();
    return () => {
      cancelled = true;
      sourceRef.current?.close();
    };
  }, [queryClient]);

  return <EventsContext.Provider value={{ recent, connected }}>{children}</EventsContext.Provider>;
}
