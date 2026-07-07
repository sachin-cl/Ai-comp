import { useEffect, useRef } from "react";
import { useProjectMessages } from "../api/hooks";
import AgentAvatar from "./AgentAvatar";
import type { Message } from "../types";

const TYPE_STYLE: Record<string, string> = {
  assignment: "border-l-sky-400",
  result: "border-l-emerald-400",
  review: "border-l-amber-400",
  revision_request: "border-l-orange-400",
  status: "border-l-slate-400",
  system: "border-l-indigo-400",
};

function MessageRow({ message }: { message: Message }) {
  const who = message.sender_name ?? (message.message_type === "system" ? "Company" : "Orchestrator");
  return (
    <div
      className={`card flex gap-3 border-l-4 ${TYPE_STYLE[message.message_type] ?? "border-l-slate-400"}`}
      data-testid="message-row"
    >
      <AgentAvatar agentKey={message.sender_agent_key} />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-baseline gap-2">
          <span className="text-sm font-semibold">{who}</span>
          {message.recipient_name && (
            <span className="text-xs text-slate-500">→ {message.recipient_name}</span>
          )}
          <span className="badge bg-slate-100 text-slate-500 dark:bg-surface-lighter dark:text-slate-400">
            {message.message_type.replace(/_/g, " ")}
          </span>
          <span className="ml-auto text-xs text-slate-400">
            {message.created_at ? new Date(message.created_at).toLocaleTimeString() : ""}
          </span>
        </div>
        <p className="mt-1 whitespace-pre-wrap text-sm text-slate-700 dark:text-slate-300">
          {message.content}
        </p>
      </div>
    </div>
  );
}

export default function ConversationFeed({ projectId }: { projectId: string }) {
  const { data, isLoading } = useProjectMessages(projectId);
  const bottomRef = useRef<HTMLDivElement>(null);
  const count = data?.items.length ?? 0;

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [count]);

  if (isLoading) return <div className="card animate-pulse">Loading conversation…</div>;
  if (!count)
    return (
      <div className="card py-10 text-center text-slate-500">
        The team hasn't started talking yet — give them a moment.
      </div>
    );

  return (
    <div className="max-h-[65vh] space-y-3 overflow-y-auto pr-2" aria-live="polite">
      {data!.items.map((m) => (
        <MessageRow key={m.id} message={m} />
      ))}
      <div ref={bottomRef} />
    </div>
  );
}
