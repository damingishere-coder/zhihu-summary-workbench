import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

export type ConnectionState = "connecting" | "connected" | "reconnecting";

const eventNames = [
  "snapshot",
  "task_queued",
  "task_progress",
  "worker_heartbeat",
  "stream_error",
] as const;

export function useTaskEvents(): ConnectionState {
  const queryClient = useQueryClient();
  const [state, setState] = useState<ConnectionState>("connecting");

  useEffect(() => {
    const source = new EventSource("/api/queues/status/stream");
    const refresh = () => {
      void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      void queryClient.invalidateQueries({ queryKey: ["questions"] });
      void queryClient.invalidateQueries({ queryKey: ["tasks"] });
      void queryClient.invalidateQueries({ queryKey: ["drafts"] });
    };
    source.onopen = () => setState("connected");
    source.onerror = () => setState("reconnecting");
    eventNames.forEach((name) => source.addEventListener(name, refresh));
    return () => {
      eventNames.forEach((name) => source.removeEventListener(name, refresh));
      source.close();
    };
  }, [queryClient]);

  return state;
}

