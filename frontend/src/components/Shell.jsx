import { useEffect, useState } from "react";
import {
  Activity,
  Bot,
  Database,
  LayoutDashboard,
  LoaderCircle,
  LogOut,
  Mail,
  Settings,
  Users,
  Workflow,
} from "lucide-react";
import { NavLink } from "react-router-dom";
import { useAuth } from "../lib/auth-context";
import { api } from "../lib/api";
import ThemeToggle from "./ThemeToggle";

const links = [
  ["/dashboard", "Dashboard", LayoutDashboard],
  ["/customers", "Customers", Users],
  ["/deals", "Deals", Workflow],
  ["/integrations", "Integrations", Database],
  ["/agent-runs", "Agent Runs", Bot],
  ["/campaigns", "Campaigns", Mail],
  ["/settings", "Settings", Settings],
];

function Navigation({ items, activeRuns, compact = false }) {
  return items.map(([to, label, Icon]) => (
    <NavLink
      key={to}
      to={to}
      className={({ isActive }) => `group flex items-center gap-3 rounded-lg text-sm transition-colors ${compact ? "min-w-fit px-3 py-2" : "mb-1 p-3"} ${isActive ? "bg-accent-primary/15 font-medium text-indigo-300" : "text-text-secondary hover:bg-bg-hover hover:text-text-primary"}`}
    >
      <Icon size={18} />
      <span>{label}</span>
      {label === "Agent Runs" && activeRuns > 0 && (
        <span className="ml-auto rounded-full bg-amber-400/15 px-2 py-0.5 text-xs text-amber-500">
          {activeRuns}
        </span>
      )}
    </NavLink>
  ));
}

export default function Shell({ children }) {
  const { user, logout } = useAuth();
  const [activeRuns, setActiveRuns] = useState(0);
  const items = user?.role === "admin" ? [...links, ["/admin", "Admin", Settings]] : links;
  const userInitial = (user?.company_name || user?.email || "T").trim().charAt(0).toUpperCase();

  useEffect(() => {
    const load = () => api("/api/agents/runs")
      .then((runs) => setActiveRuns((runs || []).filter((run) => ["queued", "running"].includes(run.status)).length))
      .catch(() => {});
    load();
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="min-h-screen bg-bg-base">
      <div className="flex min-h-screen">
        <aside className="hidden w-64 shrink-0 border-r border-border-subtle bg-bg-surface/80 p-4 lg:block">
          <div className="mb-8 flex items-center gap-3 p-2">
            <span className="grid h-10 w-10 place-items-center rounded-lg bg-accent-primary text-white shadow-glow-indigo">
              <Activity size={21} />
            </span>
            <div>
              <b className="text-[17px]">TalentForge</b>
              <p className="text-sm text-text-secondary">Success intelligence</p>
            </div>
          </div>
          <p className="eyebrow px-3 pb-3">Workspace</p>
          <Navigation items={items} activeRuns={activeRuns} />
          <div className="mt-8 border-t border-border-subtle px-3 pt-5 text-xs text-text-secondary">
            AI recommendations are always queued for review.
          </div>
        </aside>

        <div className="min-w-0 flex-1">
          <header className="border-b border-border-subtle bg-bg-base/85 px-5 py-4 backdrop-blur-md lg:px-10">
            <div className="flex min-h-10 items-center justify-between gap-4">
              <div className="flex min-w-0 items-center gap-3">
                <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-accent-primary text-white lg:hidden">
                  <Activity size={18} />
                </span>
                <div className="min-w-0">
                  <p className="truncate font-semibold">{user?.company_name || "Customer Success Hub"}</p>
                  <p className="truncate text-sm text-text-secondary">{user?.email}</p>
                </div>
              </div>
              <div className="flex items-center gap-3">
                {activeRuns > 0 && (
                  <span className="hidden items-center gap-2 rounded-lg border border-amber-400/20 bg-amber-400/10 px-3 py-2 text-sm text-amber-500 sm:flex">
                    <LoaderCircle size={15} className="animate-spin" />
                    {activeRuns} active
                  </span>
                )}
                <ThemeToggle />
                <span title={user?.email} className="grid h-10 w-10 place-items-center rounded-lg bg-bg-hover font-semibold text-text-secondary">
                  {userInitial}
                </span>
                <button type="button" onClick={logout} title="Sign out" aria-label="Sign out" className="grid h-10 w-10 place-items-center rounded-lg text-text-secondary hover:bg-bg-hover hover:text-text-primary">
                  <LogOut size={18} />
                </button>
              </div>
            </div>
            <nav className="mt-4 -mx-2 flex gap-1 overflow-x-auto border-t border-border-subtle pt-3 lg:hidden">
              <Navigation items={items} activeRuns={activeRuns} compact />
            </nav>
          </header>
          <main className="p-5 lg:p-10">{children}</main>
        </div>
      </div>
    </div>
  );
}
