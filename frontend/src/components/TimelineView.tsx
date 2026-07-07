import { useTimeline } from "../api/hooks";
import StatusBadge from "./StatusBadge";

/** Gantt-style timeline: one row per task, bars positioned by start/finish. */
export default function TimelineView({ projectId }: { projectId: string }) {
  const { data, isLoading } = useTimeline(projectId);
  if (isLoading || !data) return <div className="card animate-pulse">Loading timeline…</div>;

  const spans = data.spans.filter((s) => s.started_at);
  const t0 = Math.min(
    ...spans.map((s) => new Date(s.started_at!).getTime()),
    data.workflow.started_at ? new Date(data.workflow.started_at).getTime() : Date.now(),
  );
  const t1 = Math.max(
    ...spans.map((s) => new Date(s.finished_at ?? Date.now()).getTime()),
    t0 + 1,
  );
  const total = t1 - t0;

  return (
    <div className="card overflow-x-auto">
      {data.spans.length === 0 && (
        <div className="py-8 text-center text-slate-500">No tasks scheduled yet.</div>
      )}
      <div className="min-w-[640px] space-y-1.5">
        {data.spans.map((span) => {
          const started = span.started_at ? new Date(span.started_at).getTime() : null;
          const finished = span.finished_at ? new Date(span.finished_at).getTime() : Date.now();
          const left = started ? ((started - t0) / total) * 100 : 0;
          const width = started ? Math.max(((finished - started) / total) * 100, 1.5) : 0;
          return (
            <div key={span.task_id} className="flex items-center gap-3 text-sm">
              <div className="w-56 shrink-0 truncate" title={span.title}>
                {span.title}
                {span.revision_round > 0 && (
                  <span className="ml-1 text-xs text-amber-500">R{span.revision_round}</span>
                )}
              </div>
              <div className="relative h-5 flex-1 rounded bg-slate-100 dark:bg-surface-lighter">
                {started && (
                  <div
                    className={`absolute top-0 h-full rounded ${
                      span.status === "completed"
                        ? "bg-emerald-400/80"
                        : span.status === "running"
                          ? "animate-pulse bg-indigo-400/80"
                          : ["failed", "dead_letter"].includes(span.status)
                            ? "bg-red-400/80"
                            : "bg-slate-400/60"
                    }`}
                    style={{ left: `${left}%`, width: `${width}%` }}
                    title={`${span.status} — ${span.started_at} → ${span.finished_at ?? "now"}`}
                  />
                )}
              </div>
              <div className="w-28 shrink-0 text-right">
                <StatusBadge status={span.status} />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
