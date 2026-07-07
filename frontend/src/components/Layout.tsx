import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useEffect } from "react";
import { useAuthStore } from "../stores/auth";
import { useUiStore } from "../stores/ui";
import { useMe } from "../api/hooks";
import { useProjectSocket } from "../ws/useProjectSocket";
import NotificationBell from "./NotificationBell";

const nav = [
  { to: "/", label: "Dashboard", icon: "▦", end: true },
  { to: "/team", label: "The Team", icon: "👥" },
  { to: "/analytics", label: "Analytics", icon: "📈" },
  { to: "/settings", label: "Settings", icon: "⚙" },
];

export default function Layout() {
  const { user, setUser, logout, accessToken } = useAuthStore();
  const { theme, toggleTheme } = useUiStore();
  const navigate = useNavigate();
  const me = useMe(!!accessToken && !user);
  useProjectSocket(null); // global socket for notifications

  useEffect(() => {
    if (me.data) setUser(me.data);
    if (me.isError) {
      logout();
      navigate("/login");
    }
  }, [me.data, me.isError, setUser, logout, navigate]);

  return (
    <div className="flex min-h-screen">
      <aside className="fixed inset-y-0 left-0 z-20 flex w-56 flex-col border-r border-slate-200 bg-white dark:border-slate-700/60 dark:bg-surface-light">
        <div className="flex items-center gap-2 px-5 py-5">
          <span className="text-2xl">🏢</span>
          <div>
            <div className="text-sm font-bold leading-tight">AI Software Co.</div>
            <div className="text-xs text-slate-500 dark:text-slate-400">12 agents on staff</div>
          </div>
        </div>
        <nav className="flex-1 space-y-1 px-3">
          {nav.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium ${
                  isActive
                    ? "bg-accent/10 text-accent"
                    : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-surface-lighter"
                }`
              }
            >
              <span aria-hidden>{item.icon}</span>
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="border-t border-slate-200 p-4 dark:border-slate-700/60">
          <div className="mb-2 truncate text-sm font-medium">{user?.full_name ?? "…"}</div>
          <div className="mb-3 truncate text-xs text-slate-500">{user?.email}</div>
          <div className="flex gap-2">
            <button
              className="btn-ghost flex-1 text-xs"
              onClick={toggleTheme}
              aria-label="Toggle theme"
            >
              {theme === "dark" ? "☀ Light" : "🌙 Dark"}
            </button>
            <button
              className="btn-ghost flex-1 text-xs"
              onClick={() => {
                logout();
                navigate("/login");
              }}
            >
              Sign out
            </button>
          </div>
        </div>
      </aside>
      <div className="ml-56 flex-1">
        <header className="sticky top-0 z-10 flex items-center justify-end border-b border-slate-200 bg-white/80 px-6 py-3 backdrop-blur dark:border-slate-700/60 dark:bg-surface/80">
          <NotificationBell />
        </header>
        <main className="p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
