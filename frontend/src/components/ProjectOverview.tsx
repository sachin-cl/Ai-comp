import { useEffect, useMemo, useState } from "react";
import { useProject, useProjectTasks } from "../api/hooks";
import { useUiStore } from "../stores/ui";
import AgentAvatar from "./AgentAvatar";
import StatusBadge from "./StatusBadge";
import type { Task } from "../types";

function MermaidDiagram({ code }: { code: string }) {
  const theme = useUiStore((s) => s.theme);
  const [svg, setSvg] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const mermaid = (await import("mermaid")).default;
        mermaid.initialize({
          startOnLoad: false,
          securityLevel: "strict",
          theme: theme === "dark" ? "dark" : "neutral",
        });
        const { svg } = await mermaid.render(`arch-${Date.now()}`, code);
        if (!cancelled) {
          setSvg(svg);
          setError(null);
        }
      } catch (e) {
        if (!cancelled) setError((e as Error).message);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [code, theme]);

  if (error)
    return (
      <pre className="overflow-x-auto rounded-lg bg-slate-100 p-3 text-xs dark:bg-surface-lighter">
        {code}
      </pre>
    );
  return (
    <div
      className="overflow-x-auto [&_svg]:mx-auto [&_svg]:max-w-full"
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
}

function GateVerdicts({ task }: { task: Task }) {
  if (!task.reviews?.length) return null;
  return (
    <div className="space-y-2">
      {task.reviews.map((review, i) => (
        <div key={i} className="rounded-lg border border-slate-200 p-3 text-sm dark:border-slate-700">
          <div className="flex items-center gap-2">
            <AgentAvatar agentKey={task.agent_key} size="sm" />
            <span className="font-medium">{task.agent_name}</span>
            <StatusBadge status={review.verdict} />
            <span className="ml-auto text-xs text-slate-400">round {review.round}</span>
          </div>
          {review.reasons.length > 0 && (
            <ul className="mt-2 space-y-1 text-xs text-slate-600 dark:text-slate-400">
              {review.reasons.map((r, j) => (
                <li key={j}>
                  <span className="font-medium uppercase">{r.severity}</span> · {r.area} →{" "}
                  {r.target_node}: {r.description}
                  {r.suggestion && <span className="italic"> — {r.suggestion}</span>}
                </li>
              ))}
            </ul>
          )}
        </div>
      ))}
    </div>
  );
}

export default function ProjectOverview({ projectId }: { projectId: string }) {
  const { data: project } = useProject(projectId);
  const { data: tasks, isLoading } = useProjectTasks(projectId);

  const architecture = useMemo(
    () => tasks?.find((t) => t.node_key === "architecture"),
    [tasks],
  );
  const gates = useMemo(
    () => (tasks ?? []).filter((t) => t.reviews?.length),
    [tasks],
  );
  const activity = useMemo(
    () =>
      [...(tasks ?? [])]
        .filter((t) => t.started_at || t.finished_at)
        .sort((a, b) =>
          (b.finished_at ?? b.started_at ?? "").localeCompare(a.finished_at ?? a.started_at ?? ""),
        )
        .slice(0, 12),
    [tasks],
  );

  if (isLoading) return <div className="card animate-pulse">Loading overview…</div>;

  const mermaidCode = (architecture?.output?.mermaid_diagram as string) || "";
  const overviewText = (architecture?.output?.architecture_overview as string) || "";
  const decisions = (architecture?.output?.decisions as string[]) ?? [];

  return (
    <div className="grid gap-4 lg:grid-cols-[1fr,340px]">
      <div className="space-y-4">
        <div className="card">
          <h2 className="mb-2 font-semibold">🏗 Architecture</h2>
          {!architecture || architecture.status !== "completed" ? (
            <p className="text-sm text-slate-500">
              The architect hasn't delivered the system design yet.
            </p>
          ) : (
            <>
              {overviewText && (
                <p className="mb-3 text-sm text-slate-600 dark:text-slate-300">{overviewText}</p>
              )}
              {mermaidCode ? (
                <MermaidDiagram code={mermaidCode} />
              ) : (
                <p className="text-sm text-slate-500">No diagram was produced.</p>
              )}
              {decisions.length > 0 && (
                <ul className="mt-3 list-inside list-disc space-y-1 text-sm text-slate-600 dark:text-slate-400">
                  {decisions.map((d, i) => (
                    <li key={i}>{d}</li>
                  ))}
                </ul>
              )}
            </>
          )}
        </div>

        {gates.length > 0 && (
          <div className="card">
            <h2 className="mb-3 font-semibold">✅ Review gates</h2>
            <div className="space-y-3">
              {gates.map((t) => (
                <GateVerdicts key={t.id} task={t} />
              ))}
            </div>
          </div>
        )}
      </div>

      <div className="space-y-4">
        <div className="card text-sm">
          <h2 className="mb-2 font-semibold">Project</h2>
          <dl className="space-y-1.5 text-slate-600 dark:text-slate-300">
            <div className="flex justify-between">
              <dt>Status</dt>
              <dd>
                <StatusBadge status={project?.status ?? "…"} />
              </dd>
            </div>
            <div className="flex justify-between">
              <dt>Stage</dt>
              <dd className="font-medium">{project?.workflow?.current_stage || "—"}</dd>
            </div>
            <div className="flex justify-between">
              <dt>Tasks</dt>
              <dd className="font-medium">
                {(tasks ?? []).filter((t) => t.status === "completed").length} /{" "}
                {(tasks ?? []).length} done
              </dd>
            </div>
            <div className="flex justify-between">
              <dt>Human-in-loop</dt>
              <dd className="font-medium">{project?.human_in_loop ? "yes" : "no"}</dd>
            </div>
          </dl>
        </div>

        <div className="card">
          <h2 className="mb-2 font-semibold">Recent activity</h2>
          {activity.length === 0 ? (
            <p className="text-sm text-slate-500">Nothing has happened yet.</p>
          ) : (
            <ul className="space-y-2">
              {activity.map((t) => (
                <li key={t.id} className="flex items-center gap-2 text-sm">
                  <AgentAvatar agentKey={t.agent_key} size="sm" />
                  <span className="min-w-0 flex-1 truncate">
                    <span className="font-medium">{t.agent_name}</span>{" "}
                    <span className="text-slate-500 dark:text-slate-400">{t.title}</span>
                  </span>
                  <StatusBadge status={t.status} />
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
