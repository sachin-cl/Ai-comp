import { useState } from "react";
import { useProjectTasks, useRetryTask, useTask } from "../api/hooks";
import AgentAvatar from "./AgentAvatar";
import StatusBadge from "./StatusBadge";
import type { Task } from "../types";

const COLUMNS: { title: string; statuses: string[] }[] = [
  { title: "Backlog", statuses: ["pending"] },
  { title: "Queued", statuses: ["queued"] },
  { title: "In Progress", statuses: ["running", "revision"] },
  { title: "Review", statuses: ["review"] },
  { title: "Done", statuses: ["completed"] },
  { title: "Blocked", statuses: ["failed", "dead_letter"] },
];

function TaskCard({ task, onOpen }: { task: Task; onOpen: (id: string) => void }) {
  return (
    <button
      className="card w-full cursor-pointer p-3 text-left hover:border-accent"
      onClick={() => onOpen(task.id)}
      data-testid="kanban-card"
    >
      <div className="flex items-center gap-2">
        <AgentAvatar agentKey={task.agent_key} size="sm" />
        <span className="truncate text-xs text-slate-500">{task.agent_name}</span>
        {task.revision_round > 0 && (
          <span className="badge bg-amber-100 text-amber-700 dark:bg-amber-900/60 dark:text-amber-300">
            R{task.revision_round}
          </span>
        )}
      </div>
      <div className="mt-2 text-sm font-medium leading-snug">{task.title}</div>
    </button>
  );
}

function TaskDrawer({
  taskId,
  projectId,
  onClose,
}: {
  taskId: string;
  projectId: string;
  onClose: () => void;
}) {
  const { data: task } = useTask(taskId);
  const retry = useRetryTask(projectId);
  if (!task) return null;
  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-black/40" onClick={onClose}>
      <div
        className="h-full w-full max-w-lg overflow-y-auto bg-white p-6 dark:bg-surface-light"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-label={task.title}
      >
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-bold">{task.title}</h2>
            <div className="mt-1 flex items-center gap-2 text-sm text-slate-500">
              <AgentAvatar agentKey={task.agent_key} size="sm" /> {task.agent_name}
              <StatusBadge status={task.status} />
            </div>
          </div>
          <button className="btn-ghost" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </div>
        <p className="mt-4 whitespace-pre-wrap text-sm text-slate-600 dark:text-slate-300">
          {task.description}
        </p>
        {task.error && (
          <div className="card mt-4 border-red-400 text-sm">
            <strong>Error:</strong> {task.error}
            {["failed", "dead_letter"].includes(task.status) && (
              <button
                className="btn-primary mt-3"
                onClick={() => retry.mutate(task.id)}
                disabled={retry.isPending}
              >
                ↻ Retry task
              </button>
            )}
          </div>
        )}
        {(task.reviews ?? []).map((review, i) => (
          <div key={i} className="card mt-4 text-sm">
            <div className="font-semibold">
              Review round {review.round}: {review.verdict.replace("_", " ")}
            </div>
            <ul className="mt-2 space-y-1">
              {review.reasons.map((r, j) => (
                <li key={j}>
                  <span className="badge mr-1 bg-slate-100 dark:bg-surface-lighter">
                    {r.severity}
                  </span>
                  {r.description}
                </li>
              ))}
            </ul>
          </div>
        ))}
        {task.output && (
          <details className="mt-4">
            <summary className="cursor-pointer text-sm font-medium">Structured output</summary>
            <pre className="mt-2 max-h-96 overflow-auto rounded-lg bg-slate-950 p-3 text-xs text-slate-200">
              {JSON.stringify(task.output, null, 2)}
            </pre>
          </details>
        )}
      </div>
    </div>
  );
}

export default function KanbanBoard({ projectId }: { projectId: string }) {
  const { data: tasks, isLoading } = useProjectTasks(projectId);
  const [openTask, setOpenTask] = useState<string | null>(null);

  if (isLoading) return <div className="card animate-pulse">Loading board…</div>;

  return (
    <>
      <div className="grid gap-3 md:grid-cols-3 xl:grid-cols-6">
        {COLUMNS.map((col) => {
          const items = (tasks ?? []).filter((t) => col.statuses.includes(t.status));
          return (
            <div key={col.title} className="space-y-2">
              <div className="flex items-center justify-between px-1 text-sm font-semibold">
                {col.title}
                <span className="text-xs text-slate-400">{items.length}</span>
              </div>
              {items.map((t) => (
                <TaskCard key={t.id} task={t} onOpen={setOpenTask} />
              ))}
            </div>
          );
        })}
      </div>
      {openTask && (
        <TaskDrawer taskId={openTask} projectId={projectId} onClose={() => setOpenTask(null)} />
      )}
    </>
  );
}
