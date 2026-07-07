import { useState } from "react";
import { useAgents, useAgentStats } from "../api/hooks";
import AgentAvatar from "../components/AgentAvatar";
import type { Agent } from "../types";

function AgentStatsPanel({ agentKey }: { agentKey: string }) {
  const { data: stats, isLoading } = useAgentStats(agentKey);
  if (isLoading)
    return <div className="mt-3 animate-pulse text-sm text-slate-500">Loading stats…</div>;
  if (!stats) return null;
  const rows: [string, string][] = [
    ["Tasks completed", `${stats.tasks_completed} / ${stats.tasks_total}`],
    ["Revision rate", `${(stats.revision_rate * 100).toFixed(0)}%`],
    ["Avg tokens / task", Math.round(stats.avg_tokens).toLocaleString()],
    ["Avg latency", `${(stats.avg_latency_ms / 1000).toFixed(1)}s`],
    ["LLM calls", stats.llm_calls.toLocaleString()],
    ["Cost", `$${stats.cost_usd.toFixed(4)}`],
  ];
  return (
    <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1.5 border-t border-slate-200 pt-3 text-sm dark:border-slate-700">
      {rows.map(([label, value]) => (
        <div key={label} className="flex justify-between gap-2">
          <dt className="text-slate-500 dark:text-slate-400">{label}</dt>
          <dd className="font-medium tabular-nums">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

function AgentCard({ agent }: { agent: Agent }) {
  const [open, setOpen] = useState(false);
  return (
    <button
      className="card block w-full text-left transition-colors hover:border-accent"
      onClick={() => setOpen((v) => !v)}
      aria-expanded={open}
    >
      <div className="flex items-start gap-3">
        <AgentAvatar agentKey={agent.key} size="lg" />
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h3 className="font-semibold">{agent.name}</h3>
            <span
              className={`h-2 w-2 rounded-full ${
                agent.is_active ? "bg-emerald-500" : "bg-slate-400"
              }`}
              title={agent.is_active ? "active" : "inactive"}
            />
          </div>
          <div className="text-sm text-slate-500 dark:text-slate-400">{agent.role_title}</div>
          <div className="mt-1 flex flex-wrap gap-1">
            <span className="badge bg-slate-100 text-slate-600 dark:bg-surface-lighter dark:text-slate-300">
              {agent.provider}
            </span>
            <span className="badge bg-slate-100 text-slate-600 dark:bg-surface-lighter dark:text-slate-300">
              {agent.model}
            </span>
          </div>
        </div>
      </div>
      <p className="mt-3 text-sm italic text-slate-600 dark:text-slate-400">
        “{agent.personality}”
      </p>
      {open && <AgentStatsPanel agentKey={agent.key} />}
    </button>
  );
}

export default function TeamPage() {
  const { data: agents, isLoading } = useAgents();

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">The Team</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400">
          {agents?.length ?? "…"} AI employees on staff. Click a card for their performance record.
        </p>
      </div>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {isLoading && <div className="card animate-pulse">Assembling the roster…</div>}
        {agents?.map((agent) => <AgentCard key={agent.key} agent={agent} />)}
      </div>
    </div>
  );
}
