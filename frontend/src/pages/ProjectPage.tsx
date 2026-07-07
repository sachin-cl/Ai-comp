import { useState } from "react";
import { useParams } from "react-router-dom";
import { useProject, useProjectAction } from "../api/hooks";
import { useProjectSocket } from "../ws/useProjectSocket";
import { useAuthStore } from "../stores/auth";
import StatusBadge from "../components/StatusBadge";
import ConversationFeed from "../components/ConversationFeed";
import KanbanBoard from "../components/KanbanBoard";
import FileExplorer from "../components/FileExplorer";
import TimelineView from "../components/TimelineView";
import ProjectOverview from "../components/ProjectOverview";

const TABS = ["Conversation", "Board", "Files", "Timeline", "Overview"] as const;
type Tab = (typeof TABS)[number];

export default function ProjectPage() {
  const { projectId = "" } = useParams();
  const { data: project, isLoading } = useProject(projectId);
  const action = useProjectAction(projectId);
  const [tab, setTab] = useState<Tab>("Conversation");
  const token = useAuthStore((s) => s.accessToken);
  useProjectSocket(projectId);

  if (isLoading || !project) {
    return <div className="card animate-pulse">Loading project…</div>;
  }

  const canCancel = ["pending", "planning", "in_progress", "review", "needs_attention"].includes(
    project.status,
  );
  const awaitingApproval =
    project.status === "review" && project.workflow?.paused_reason?.includes("gate");
  const gateName = project.workflow?.paused_reason?.match(/'([a-z_]+)'/)?.[1] ?? "qa_review";

  const download = async () => {
    const res = await fetch(`/api/v1/projects/${projectId}/download`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) return;
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${project.name}.zip`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold">{project.name}</h1>
            <StatusBadge status={project.status} />
          </div>
          <p className="mt-1 max-w-2xl text-sm text-slate-500 dark:text-slate-400">
            {project.prompt}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button className="btn-ghost" onClick={download}>
            ⬇ Download ZIP
          </button>
          {project.status === "needs_attention" && (
            <button
              className="btn-primary"
              onClick={() => action.mutate({ action: "resume" })}
              disabled={action.isPending}
            >
              ▶ Resume
            </button>
          )}
          {canCancel && (
            <button
              className="btn-ghost text-red-500"
              onClick={() => action.mutate({ action: "cancel" })}
              disabled={action.isPending}
            >
              ✕ Cancel
            </button>
          )}
        </div>
      </div>

      {project.status === "needs_attention" && (
        <div className="card border-orange-400 bg-orange-50 text-sm dark:bg-orange-950/40">
          <strong>Needs attention:</strong> {project.workflow?.paused_reason}
        </div>
      )}
      {awaitingApproval && (
        <div className="card flex flex-wrap items-center justify-between gap-3 border-amber-400 bg-amber-50 text-sm dark:bg-amber-950/40">
          <span>
            <strong>Your approval required</strong> — {project.workflow?.paused_reason}
          </span>
          <div className="flex gap-2">
            <button
              className="btn-primary"
              onClick={() =>
                action.mutate({ action: "approve", body: { gate: gateName, approved: true } })
              }
            >
              ✓ Approve
            </button>
            <button
              className="btn-ghost"
              onClick={() => {
                const feedback = window.prompt("What should change?") ?? "";
                if (feedback)
                  action.mutate({
                    action: "approve",
                    body: { gate: gateName, approved: false, feedback },
                  });
              }}
            >
              Request changes
            </button>
          </div>
        </div>
      )}

      <div className="card flex items-center gap-6 text-sm">
        <span>
          Stage: <strong>{project.workflow?.current_stage || "—"}</strong>
        </span>
        <span>
          Tokens:{" "}
          <strong>
            {project.tokens_used.toLocaleString()} / {project.token_budget.toLocaleString()}
          </strong>
        </span>
        <span>
          Cost: <strong>${project.cost_usd.toFixed(4)}</strong>
        </span>
      </div>

      <div role="tablist" className="flex gap-1 border-b border-slate-200 dark:border-slate-700">
        {TABS.map((t) => (
          <button
            key={t}
            role="tab"
            aria-selected={tab === t}
            className={`px-4 py-2 text-sm font-medium ${
              tab === t
                ? "border-b-2 border-accent text-accent"
                : "text-slate-500 hover:text-slate-800 dark:hover:text-slate-200"
            }`}
            onClick={() => setTab(t)}
          >
            {t}
          </button>
        ))}
      </div>

      {tab === "Conversation" && <ConversationFeed projectId={projectId} />}
      {tab === "Board" && <KanbanBoard projectId={projectId} />}
      {tab === "Files" && <FileExplorer projectId={projectId} />}
      {tab === "Timeline" && <TimelineView projectId={projectId} />}
      {tab === "Overview" && <ProjectOverview projectId={projectId} />}
    </div>
  );
}
