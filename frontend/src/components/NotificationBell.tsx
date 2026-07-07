import { useState } from "react";
import { Link } from "react-router-dom";
import { useMarkRead, useNotifications } from "../api/hooks";

export default function NotificationBell() {
  const [open, setOpen] = useState(false);
  const { data } = useNotifications();
  const markRead = useMarkRead();
  const unread = data?.items.filter((n) => !n.read_at) ?? [];

  return (
    <div className="relative">
      <button
        className="btn-ghost relative"
        onClick={() => setOpen((o) => !o)}
        aria-label={`Notifications (${unread.length} unread)`}
      >
        🔔
        {unread.length > 0 && (
          <span className="absolute -right-1 -top-1 flex h-5 min-w-5 items-center justify-center rounded-full bg-red-500 px-1 text-xs font-bold text-white">
            {unread.length}
          </span>
        )}
      </button>
      {open && (
        <div className="absolute right-0 top-12 z-30 w-96 max-w-[90vw] rounded-xl border border-slate-200 bg-white shadow-xl dark:border-slate-700 dark:bg-surface-light">
          <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3 dark:border-slate-700">
            <span className="text-sm font-semibold">Notifications</span>
            <button
              className="text-xs text-accent hover:underline"
              onClick={() => markRead.mutate("all")}
            >
              Mark all read
            </button>
          </div>
          <div className="max-h-96 overflow-y-auto">
            {(data?.items ?? []).length === 0 && (
              <div className="px-4 py-8 text-center text-sm text-slate-500">
                Nothing yet — create a project and the team will keep you posted.
              </div>
            )}
            {(data?.items ?? []).map((n) => (
              <Link
                key={n.id}
                to={n.project_id ? `/projects/${n.project_id}` : "/"}
                onClick={() => {
                  if (!n.read_at) markRead.mutate(n.id);
                  setOpen(false);
                }}
                className={`block border-b border-slate-100 px-4 py-3 text-sm hover:bg-slate-50 dark:border-slate-700/50 dark:hover:bg-surface-lighter ${
                  n.read_at ? "opacity-60" : ""
                }`}
              >
                <div className="font-medium">{n.title}</div>
                <div className="mt-0.5 line-clamp-2 text-xs text-slate-500 dark:text-slate-400">
                  {n.body}
                </div>
              </Link>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
