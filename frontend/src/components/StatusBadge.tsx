const COLORS: Record<string, string> = {
  pending: "bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-200",
  planning: "bg-sky-100 text-sky-700 dark:bg-sky-900/60 dark:text-sky-300",
  queued: "bg-sky-100 text-sky-700 dark:bg-sky-900/60 dark:text-sky-300",
  running: "bg-indigo-100 text-indigo-700 dark:bg-indigo-900/60 dark:text-indigo-300",
  in_progress: "bg-indigo-100 text-indigo-700 dark:bg-indigo-900/60 dark:text-indigo-300",
  review: "bg-amber-100 text-amber-700 dark:bg-amber-900/60 dark:text-amber-300",
  revision: "bg-amber-100 text-amber-700 dark:bg-amber-900/60 dark:text-amber-300",
  needs_attention: "bg-orange-100 text-orange-700 dark:bg-orange-900/60 dark:text-orange-300",
  completed: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/60 dark:text-emerald-300",
  failed: "bg-red-100 text-red-700 dark:bg-red-900/60 dark:text-red-300",
  dead_letter: "bg-red-100 text-red-700 dark:bg-red-900/60 dark:text-red-300",
  cancelled: "bg-slate-200 text-slate-500 dark:bg-slate-700 dark:text-slate-400",
};

export default function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`badge ${COLORS[status] ?? COLORS.pending}`}>
      {status === "running" && (
        <span className="mr-1 inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-current" />
      )}
      {status.replace(/_/g, " ")}
    </span>
  );
}
