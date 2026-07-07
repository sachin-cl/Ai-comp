import { useMemo } from "react";
import { useAnalytics } from "../api/hooks";
import AgentAvatar from "../components/AgentAvatar";
import StatusBadge from "../components/StatusBadge";

function StatTile({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="card">
      <div className="text-sm text-slate-500 dark:text-slate-400">{label}</div>
      <div className="mt-1 text-3xl font-bold tabular-nums">{value}</div>
      {hint && <div className="mt-1 text-xs text-slate-400">{hint}</div>}
    </div>
  );
}

/** Thin single-hue meter; the printed value carries the number, the bar is a visual aid. */
function Meter({ value, max }: { value: number; max: number }) {
  const pct = max > 0 ? Math.min((value / max) * 100, 100) : 0;
  return (
    <div className="h-1.5 w-24 overflow-hidden rounded-full bg-slate-200 dark:bg-surface-lighter">
      <div className="h-full rounded-full bg-accent" style={{ width: `${pct}%` }} />
    </div>
  );
}

export default function AnalyticsPage() {
  const { data, isLoading } = useAnalytics();

  const agents = useMemo(
    () => [...(data?.agents ?? [])].sort((a, b) => b.tasks_completed - a.tasks_completed),
    [data],
  );
  const maxTokens = Math.max(...agents.map((a) => a.avg_tokens), 1);
  const maxLatency = Math.max(...agents.map((a) => a.avg_latency_ms), 1);
  const totalProjects = Object.values(data?.projects_by_status ?? {}).reduce((s, n) => s + n, 0);

  if (isLoading) return <div className="card animate-pulse">Crunching the numbers…</div>;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Analytics</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400">
          Company-wide spend and agent performance.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <StatTile
          label="Total tokens"
          value={(data?.total_tokens ?? 0).toLocaleString()}
          hint="across all projects"
        />
        <StatTile
          label="Total cost"
          value={`$${(data?.total_cost_usd ?? 0).toFixed(2)}`}
          hint="estimated LLM spend"
        />
        <StatTile label="Projects" value={String(totalProjects)} hint="all time" />
      </div>

      <div className="card">
        <h2 className="mb-3 font-semibold">Projects by status</h2>
        {totalProjects === 0 ? (
          <p className="text-sm text-slate-500">No projects yet.</p>
        ) : (
          <div className="flex flex-wrap items-center gap-3">
            {Object.entries(data?.projects_by_status ?? {}).map(([status, count]) => (
              <span key={status} className="flex items-center gap-1.5 text-sm">
                <StatusBadge status={status} />
                <span className="font-medium tabular-nums">{count}</span>
              </span>
            ))}
          </div>
        )}
      </div>

      <div className="card overflow-x-auto p-0">
        <h2 className="px-4 pt-4 font-semibold">Agent performance</h2>
        {agents.length === 0 ? (
          <p className="p-4 text-sm text-slate-500">
            No agent activity yet — start a project to put the team to work.
          </p>
        ) : (
          <table className="mt-3 w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500 dark:border-slate-700">
                <th className="px-4 py-2 font-medium">Agent</th>
                <th className="px-4 py-2 font-medium">Tasks done</th>
                <th className="px-4 py-2 font-medium">Revision rate</th>
                <th className="px-4 py-2 font-medium">Avg tokens</th>
                <th className="px-4 py-2 font-medium">Avg latency</th>
                <th className="px-4 py-2 font-medium">LLM calls</th>
                <th className="px-4 py-2 text-right font-medium">Cost</th>
              </tr>
            </thead>
            <tbody>
              {agents.map((a) => (
                <tr
                  key={a.agent_key}
                  className="border-b border-slate-100 last:border-0 dark:border-slate-800"
                >
                  <td className="px-4 py-2">
                    <div className="flex items-center gap-2">
                      <AgentAvatar agentKey={a.agent_key} size="sm" />
                      <div>
                        <div className="font-medium">{a.name ?? a.agent_key}</div>
                        {a.role_title && (
                          <div className="text-xs text-slate-400">{a.role_title}</div>
                        )}
                      </div>
                    </div>
                  </td>
                  <td className="px-4 py-2 tabular-nums">
                    {a.tasks_completed} / {a.tasks_total}
                  </td>
                  <td className="px-4 py-2">
                    <div className="flex items-center gap-2">
                      <Meter value={a.revision_rate} max={1} />
                      <span className="tabular-nums">{(a.revision_rate * 100).toFixed(0)}%</span>
                    </div>
                  </td>
                  <td className="px-4 py-2">
                    <div className="flex items-center gap-2">
                      <Meter value={a.avg_tokens} max={maxTokens} />
                      <span className="tabular-nums">
                        {Math.round(a.avg_tokens).toLocaleString()}
                      </span>
                    </div>
                  </td>
                  <td className="px-4 py-2">
                    <div className="flex items-center gap-2">
                      <Meter value={a.avg_latency_ms} max={maxLatency} />
                      <span className="tabular-nums">{(a.avg_latency_ms / 1000).toFixed(1)}s</span>
                    </div>
                  </td>
                  <td className="px-4 py-2 tabular-nums">{a.llm_calls.toLocaleString()}</td>
                  <td className="px-4 py-2 text-right tabular-nums">${a.cost_usd.toFixed(4)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
