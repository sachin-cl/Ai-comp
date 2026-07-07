import { useEffect, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useAuthStore } from "../stores/auth";
import type { WsEvent } from "../types";

/** Live updates: subscribes to a project's event channel and invalidates the
 *  matching queries. Falls back gracefully — REST polling still runs underneath. */
export function useProjectSocket(projectId: string | null) {
  const qc = useQueryClient();
  const token = useAuthStore((s) => s.accessToken);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!token) return;
    const proto = window.location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${window.location.host}/ws?token=${token}`);
    wsRef.current = ws;

    ws.onopen = () => {
      if (projectId) ws.send(JSON.stringify({ action: "subscribe", project_id: projectId }));
    };
    ws.onmessage = (raw) => {
      let event: WsEvent;
      try {
        event = JSON.parse(raw.data as string);
      } catch {
        return;
      }
      const pid = event.project_id as string | undefined;
      switch (event.type) {
        case "task.updated":
          if (pid) {
            qc.invalidateQueries({ queryKey: ["projects", pid, "tasks"] });
            qc.invalidateQueries({ queryKey: ["projects", pid, "timeline"] });
          }
          break;
        case "workflow.updated":
        case "budget.updated":
          if (pid) qc.invalidateQueries({ queryKey: ["projects", pid] });
          qc.invalidateQueries({ queryKey: ["projects"] });
          break;
        case "agent.message":
        case "messages.changed":
          if (pid) qc.invalidateQueries({ queryKey: ["projects", pid, "messages"] });
          break;
        case "artifact.created":
          if (pid) qc.invalidateQueries({ queryKey: ["projects", pid, "artifacts"] });
          break;
        case "notification":
          qc.invalidateQueries({ queryKey: ["notifications"] });
          break;
      }
    };
    return () => {
      ws.close();
      wsRef.current = null;
    };
  }, [token, projectId, qc]);
}
