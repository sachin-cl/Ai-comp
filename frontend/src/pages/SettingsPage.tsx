import { useNavigate } from "react-router-dom";
import { useAuthStore } from "../stores/auth";
import { useUiStore } from "../stores/ui";

export default function SettingsPage() {
  const { user, logout } = useAuthStore();
  const { theme, toggleTheme } = useUiStore();
  const navigate = useNavigate();

  return (
    <div className="max-w-2xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Settings</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400">
          Your account and workspace preferences.
        </p>
      </div>

      <div className="card">
        <h2 className="mb-3 font-semibold">Account</h2>
        <dl className="space-y-2 text-sm">
          <div className="flex justify-between">
            <dt className="text-slate-500 dark:text-slate-400">Name</dt>
            <dd className="font-medium">{user?.full_name ?? "…"}</dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-slate-500 dark:text-slate-400">Email</dt>
            <dd className="font-medium">{user?.email ?? "…"}</dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-slate-500 dark:text-slate-400">Role</dt>
            <dd>
              <span className="badge bg-accent/10 text-accent">{user?.role ?? "…"}</span>
            </dd>
          </div>
        </dl>
      </div>

      <div className="card">
        <h2 className="mb-3 font-semibold">Appearance</h2>
        <div className="flex items-center justify-between text-sm">
          <span className="text-slate-500 dark:text-slate-400">
            Theme — currently <strong>{theme}</strong>
          </span>
          <button className="btn-ghost" onClick={toggleTheme}>
            {theme === "dark" ? "☀ Switch to light" : "🌙 Switch to dark"}
          </button>
        </div>
      </div>

      <div className="card">
        <h2 className="mb-3 font-semibold">Workflow guardrails</h2>
        <p className="text-sm text-slate-500 dark:text-slate-400">
          Per-project token budgets, revision-loop limits, and approval gates are configured when
          you create a project. A running workflow that exceeds its limits pauses in{" "}
          <span className="badge bg-orange-100 text-orange-700 dark:bg-orange-950/60 dark:text-orange-300">
            needs attention
          </span>{" "}
          and waits for you — it never loops forever.
        </p>
      </div>

      <div className="card border-red-200 dark:border-red-900/60">
        <h2 className="mb-3 font-semibold text-red-600 dark:text-red-400">Session</h2>
        <div className="flex items-center justify-between text-sm">
          <span className="text-slate-500 dark:text-slate-400">
            Sign out of this device. Your refresh token is revoked.
          </span>
          <button
            className="btn-ghost text-red-500"
            onClick={() => {
              logout();
              navigate("/login");
            }}
          >
            Sign out
          </button>
        </div>
      </div>
    </div>
  );
}
