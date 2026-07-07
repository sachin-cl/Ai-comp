import { useState } from "react";
import { Link } from "react-router-dom";
import { useCreateProject, useProjects } from "../api/hooks";
import StatusBadge from "../components/StatusBadge";

const EXAMPLES = [
  "Build a food delivery app",
  "Create an expense tracker",
  "Develop an AI study assistant",
  "Build a SaaS landing page",
];

export default function DashboardPage() {
  const { data, isLoading } = useProjects();
  const create = useCreateProject();
  const [name, setName] = useState("");
  const [prompt, setPrompt] = useState("");
  const [humanInLoop, setHumanInLoop] = useState(false);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    create.mutate(
      { name: name || prompt.slice(0, 60), prompt, human_in_loop: humanInLoop },
      {
        onSuccess: () => {
          setName("");
          setPrompt("");
        },
      },
    );
  };

  const projects = data?.items ?? [];
  const active = projects.filter((p) =>
    ["planning", "in_progress", "review"].includes(p.status),
  ).length;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Company Dashboard</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400">
          {projects.length} projects · {active} in flight
        </p>
      </div>

      <form onSubmit={submit} className="card space-y-3">
        <h2 className="font-semibold">Start a new project</h2>
        <textarea
          className="input min-h-20"
          placeholder='Tell the company what to build, e.g. "Build a food delivery app"'
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          required
          aria-label="Project prompt"
        />
        <div className="flex flex-wrap gap-2">
          {EXAMPLES.map((ex) => (
            <button
              key={ex}
              type="button"
              className="badge bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-surface-lighter dark:text-slate-300"
              onClick={() => setPrompt(ex)}
            >
              {ex}
            </button>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-4">
          <input
            className="input max-w-xs"
            placeholder="Project name (optional)"
            value={name}
            onChange={(e) => setName(e.target.value)}
            aria-label="Project name"
          />
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={humanInLoop}
              onChange={(e) => setHumanInLoop(e.target.checked)}
            />
            Require my approval at QA / Security / CEO gates
          </label>
          <button
            type="submit"
            className="btn-primary ml-auto"
            disabled={create.isPending || !prompt.trim()}
          >
            {create.isPending ? "Hiring the team…" : "🚀 Kick off"}
          </button>
        </div>
        {create.isError && (
          <p role="alert" className="text-sm text-red-500">
            {(create.error as Error).message}
          </p>
        )}
      </form>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {isLoading && <div className="card animate-pulse">Loading projects…</div>}
        {!isLoading && projects.length === 0 && (
          <div className="card col-span-full py-12 text-center text-slate-500">
            No projects yet. Give the company its first assignment above. 👆
          </div>
        )}
        {projects.map((p) => (
          <Link key={p.id} to={`/projects/${p.id}`} className="card block hover:border-accent">
            <div className="flex items-start justify-between gap-2">
              <h3 className="font-semibold leading-tight">{p.name}</h3>
              <StatusBadge status={p.status} />
            </div>
            <p className="mt-1 line-clamp-2 text-sm text-slate-500 dark:text-slate-400">
              {p.prompt}
            </p>
            <div className="mt-3 space-y-1">
              <div className="flex justify-between text-xs text-slate-500">
                <span>Stage: {p.workflow?.current_stage || "—"}</span>
                <span>${p.cost_usd.toFixed(2)}</span>
              </div>
              <div className="h-1.5 overflow-hidden rounded-full bg-slate-200 dark:bg-surface-lighter">
                <div
                  className="h-full rounded-full bg-accent transition-all"
                  style={{
                    width: `${Math.min((p.tokens_used / p.token_budget) * 100, 100)}%`,
                  }}
                  title={`${p.tokens_used.toLocaleString()} / ${p.token_budget.toLocaleString()} tokens`}
                />
              </div>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
