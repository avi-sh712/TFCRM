import {
  Activity,
  ArrowUpRight,
  Bot,
  CheckCircle2,
  ChevronRight,
  CircleDot,
  Clock3,
  LayoutDashboard,
  LifeBuoy,
  Mail,
  Settings2,
  ShieldCheck,
  Sparkles,
  Users,
} from "lucide-react";

const campaigns = [
  {
    company: "Northstar Labs",
    initials: "NL",
    issue: "Workspace activation stalled",
    status: "Awaiting-Approval",
    time: "8 min ago",
    accent: "amber",
  },
  {
    company: "Vertex Health",
    initials: "VH",
    issue: "Weekly usage dropped 34%",
    status: "Awaiting-Approval",
    time: "24 min ago",
    accent: "amber",
  },
  {
    company: "Orbit Systems",
    initials: "OS",
    issue: "Resolved billing incident",
    status: "Sent",
    time: "1 hr ago",
    accent: "emerald",
  },
];

const activity = [
  { label: "Root cause analysis complete", company: "Northstar Labs", time: "now", color: "bg-indigo-400" },
  { label: "Historical records retrieved", company: "Vertex Health", time: "2m", color: "bg-cyan-400" },
  { label: "Outreach draft staged for review", company: "Orbit Systems", time: "9m", color: "bg-emerald-400" },
];

function StatusBadge({ status, accent }) {
  const styles = accent === "emerald"
    ? "border-emerald-400/20 bg-emerald-400/10 text-emerald-300"
    : "border-amber-400/20 bg-amber-400/10 text-amber-300";

  return <span className={`rounded-full border px-2.5 py-1 text-[11px] font-medium tracking-wide ${styles}`}>{status}</span>;
}

function MetricCard({ label, value, detail, icon: Icon, tone }) {
  const tones = {
    emerald: "text-emerald-300 bg-emerald-400/10 border-emerald-400/20 glow-emerald",
    cyan: "text-cyan-300 bg-cyan-400/10 border-cyan-400/20 shadow-[0_0_15px_-3px_rgba(34,211,238,0.15)]",
    violet: "text-violet-300 bg-violet-400/10 border-violet-400/20 glow-indigo",
  };

  return (
    <article className={`glass-card rounded-2xl p-5 ${tones[tone]}`}>
      <div className="flex items-start justify-between">
        <p className="text-sm text-slate-400">{label}</p>
        <span className="rounded-lg border border-current/10 p-2"><Icon size={17} strokeWidth={1.8} /></span>
      </div>
      <div className="mt-5 flex items-end justify-between gap-3">
        <p className="text-3xl font-semibold tracking-tight text-slate-100">{value}</p>
        <p className="text-right text-xs text-slate-500">{detail}</p>
      </div>
    </article>
  );
}

function Sidebar() {
  const links = [
    { label: "Overview", icon: LayoutDashboard, active: true },
    { label: "Customers", icon: Users },
    { label: "Campaigns", icon: Mail, count: "3" },
    { label: "Agent Runs", icon: Bot },
  ];

  return (
    <aside className="flex w-full shrink-0 flex-col border-b border-slate-800/80 bg-slate-950/70 p-4 md:min-h-screen md:w-64 md:border-b-0 md:border-r md:p-5">
      <div className="flex items-center gap-3 px-2 py-2">
        <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 to-violet-500 shadow-glow-indigo">
          <Sparkles size={18} className="text-white" />
        </div>
        <div>
          <p className="font-semibold tracking-wide text-slate-100">TalentForge</p>
          <p className="text-[10px] uppercase tracking-[0.2em] text-slate-500">Success Intelligence</p>
        </div>
      </div>

      <nav className="mt-8 grid grid-cols-2 gap-1 md:block md:space-y-1">
        {links.map(({ label, icon: Icon, active, count }) => (
          <button
            key={label}
            className={`group relative flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm transition-colors ${active ? "bg-indigo-500/10 text-indigo-200" : "text-slate-500 hover:bg-slate-900 hover:text-slate-200"}`}
          >
            {active && <span className="absolute left-0 h-5 w-0.5 rounded-full bg-indigo-400 shadow-[0_0_10px_2px_rgba(129,140,248,0.7)]" />}
            <Icon size={17} strokeWidth={1.8} />
            <span>{label}</span>
            {count && <span className="ml-auto rounded-full bg-slate-800 px-2 py-0.5 text-[10px] text-slate-400">{count}</span>}
          </button>
        ))}
      </nav>

      <div className="mt-auto hidden space-y-1 md:block">
        <button className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm text-slate-500 transition-colors hover:bg-slate-900 hover:text-slate-200">
          <LifeBuoy size={17} strokeWidth={1.8} /> Support
        </button>
        <button className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm text-slate-500 transition-colors hover:bg-slate-900 hover:text-slate-200">
          <Settings2 size={17} strokeWidth={1.8} /> Settings
        </button>
        <div className="mt-5 flex items-center gap-3 border-t border-slate-800/80 px-2 pt-5">
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-br from-slate-700 to-slate-800 text-xs font-medium text-slate-200">AM</div>
          <div className="min-w-0">
            <p className="truncate text-sm text-slate-200">Alex Morgan</p>
            <p className="text-xs text-slate-500">Customer Success</p>
          </div>
          <ChevronRight size={15} className="ml-auto text-slate-600" />
        </div>
      </div>
    </aside>
  );
}

function App() {
  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <div className="flex min-h-screen flex-col md:flex-row">
        <Sidebar />
        <main className="min-w-0 flex-1 p-5 sm:p-8 lg:p-10">
          <header className="mb-8 flex flex-col justify-between gap-5 sm:flex-row sm:items-end">
            <div>
              <div className="mb-3 flex items-center gap-2 text-xs font-medium uppercase tracking-[0.18em] text-indigo-300">
                <CircleDot size={13} className="animate-pulse-glow" /> Command center
              </div>
              <h1 className="text-2xl font-semibold tracking-tight text-slate-100 sm:text-3xl">Customer health overview</h1>
              <p className="mt-2 text-sm text-slate-500">Your autonomous success team is monitoring 248 accounts.</p>
            </div>
            <div className="flex items-center gap-2 text-xs text-slate-500">
              <span className="h-2 w-2 rounded-full bg-emerald-400 shadow-[0_0_8px_2px_rgba(52,211,153,0.55)]" /> All systems operational
            </div>
          </header>

          <section className="grid gap-4 lg:grid-cols-3">
            <MetricCard label="Churn Prevention Rate" value="87.4%" detail="+6.2% this month" icon={ShieldCheck} tone="emerald" />
            <MetricCard label="Cached Resolutions" value="1,284" detail="<200ms processing" icon={Activity} tone="cyan" />
            <MetricCard label="Active Swarm Runs" value="12" detail="4 requiring review" icon={Bot} tone="violet" />
          </section>

          <section className="mt-8 grid gap-6 xl:grid-cols-[minmax(0,1.45fr)_minmax(300px,0.8fr)]">
            <div>
              <div className="mb-4 flex items-center justify-between">
                <div>
                  <h2 className="text-lg font-medium text-slate-100">Campaign review queue</h2>
                  <p className="mt-1 text-sm text-slate-500">Human approval is required before any outreach is sent.</p>
                </div>
                <button className="flex items-center gap-1 text-xs font-medium text-indigo-300 transition-colors hover:text-indigo-200">View all <ArrowUpRight size={14} /></button>
              </div>
              <div className="space-y-3">
                {campaigns.map((campaign) => (
                  <article key={campaign.company} className="glass-card rounded-2xl p-4 transition-all duration-300 hover:scale-[1.01] hover:border-slate-700/80 sm:p-5">
                    <div className="flex items-start gap-4">
                      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-slate-800 text-xs font-semibold text-slate-300">{campaign.initials}</div>
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                          <div>
                            <h3 className="font-medium text-slate-100">{campaign.company}</h3>
                            <p className="mt-1 text-sm text-slate-500">{campaign.issue}</p>
                          </div>
                          <StatusBadge status={campaign.status} accent={campaign.accent} />
                        </div>
                        <div className="mt-4 flex items-center justify-between border-t border-slate-800/70 pt-3">
                          <span className="flex items-center gap-1.5 text-xs text-slate-600"><Clock3 size={13} /> {campaign.time}</span>
                          <button className="flex items-center gap-1 text-xs font-medium text-slate-400 transition-colors hover:text-indigo-300">Review draft <ChevronRight size={14} /></button>
                        </div>
                      </div>
                    </div>
                  </article>
                ))}
              </div>
            </div>

            <aside className="glass-card rounded-2xl p-5">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="font-medium text-slate-100">Swarm activity</h2>
                  <p className="mt-1 text-xs text-slate-500">Live orchestration feed</p>
                </div>
                <span className="rounded-lg bg-indigo-400/10 p-2 text-indigo-300"><Bot size={17} /></span>
              </div>
              <div className="mt-6 space-y-6">
                {activity.map((item) => (
                  <div key={item.label} className="relative flex gap-3">
                    <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${item.color} shadow-[0_0_8px_2px_rgba(129,140,248,0.35)]`} />
                    <div className="min-w-0">
                      <p className="text-sm text-slate-300">{item.label}</p>
                      <div className="mt-1 flex items-center justify-between gap-3 text-xs text-slate-600"><span>{item.company}</span><span>{item.time}</span></div>
                    </div>
                  </div>
                ))}
              </div>
              <div className="mt-8 flex items-center gap-2 rounded-xl border border-indigo-400/10 bg-indigo-400/5 px-3 py-3 text-xs text-indigo-200/70">
                <CheckCircle2 size={15} className="text-indigo-300" /> All agents are within policy limits.
              </div>
            </aside>
          </section>
        </main>
      </div>
    </div>
  );
}

export default App;
