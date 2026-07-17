import { ArrowRight, Bot, CircleAlert, HeartPulse, Mail, Sparkles, Users, Workflow } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";

const currency = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});

function relativeDate(value) {
  if (!value) return "No recent activity";
  const hours = Math.max(0, Math.round((Date.now() - new Date(value).getTime()) / 3_600_000));
  if (hours < 1) return "Updated just now";
  if (hours < 24) return `Updated ${hours}h ago`;
  return `Updated ${Math.round(hours / 24)}d ago`;
}

function MetricCard({ label, value, detail, icon: Icon, tone = "text-indigo-400" }) {
  return (
    <section className={`metric-card ${tone}`}>
      <div className="flex items-start justify-between gap-4">
        <div><p className="text-sm text-text-secondary">{label}</p><p className="mt-4 text-3xl font-bold text-text-primary">{value}</p></div>
        <span className="grid h-10 w-10 place-items-center rounded-lg bg-current/10"><Icon size={19} /></span>
      </div>
      <p className="mt-4 text-sm text-text-secondary">{detail}</p>
    </section>
  );
}

function HealthRow({ label, count, total, color }) {
  const percent = total ? Math.round((count / total) * 100) : 0;
  return <div className="mt-4"><div className="flex justify-between text-sm"><span>{label}</span><span className="text-text-secondary">{count} customers</span></div><div className="mt-2 h-2 overflow-hidden rounded-full bg-bg-hover"><div className={`h-full rounded-full ${color}`} style={{ width: `${percent}%` }} /></div></div>;
}

export default function Dashboard() {
  const [stats, setStats] = useState(null);
  const [campaigns, setCampaigns] = useState([]);
  const [runs, setRuns] = useState([]);
  const [customers, setCustomers] = useState([]);
  const [deals, setDeals] = useState([]);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const [overview, campaignList, runList, customerResult, dealList] = await Promise.all([
          api("/api/stats/overview"),
          api("/api/campaigns"),
          api("/api/agents/runs"),
          api("/api/customers?limit=100"),
          api("/api/deals"),
        ]);
        if (!active) return;
        setStats(overview);
        setCampaigns(campaignList || []);
        setRuns(runList || []);
        setCustomers(customerResult.items || []);
        setDeals(dealList || []);
        setError("");
      } catch (cause) {
        if (active) setError(cause.message);
      }
    }
    load();
    const id = setInterval(load, 15_000);
    return () => { active = false; clearInterval(id); };
  }, []);

  const insights = useMemo(() => {
    const atRisk = customers.filter((customer) => Number(customer.health_score || 0) < 45);
    const watch = customers.filter((customer) => {
      const score = Number(customer.health_score || 0);
      return score >= 45 && score < 75;
    });
    const healthy = customers.filter((customer) => Number(customer.health_score || 0) >= 75);
    const averageHealth = customers.length
      ? Math.round(customers.reduce((sum, customer) => sum + Number(customer.health_score || 0), 0) / customers.length)
      : 0;
    const pipelineValue = deals
      .filter((deal) => !["closed_won", "closed_lost"].includes(deal.stage))
      .reduce((sum, deal) => sum + Number(deal.value || 0), 0);
    const atRiskMrr = atRisk.reduce((sum, customer) => sum + Number(customer.mrr || 0), 0);
    return { atRisk, watch, healthy, averageHealth, pipelineValue, atRiskMrr };
  }, [customers, deals]);

  const pendingCampaigns = campaigns.filter((campaign) => campaign.status === "pending_review");
  const activeRuns = runs.filter((run) => ["queued", "running"].includes(run.status));
  const attentionCustomers = [...insights.atRisk, ...insights.watch].sort((a, b) => Number(a.health_score) - Number(b.health_score)).slice(0, 4);

  return <>
    <div className="flex flex-wrap items-end justify-between gap-5">
      <div><p className="eyebrow text-indigo-400">Workspace overview</p><h1 className="mt-2 text-3xl font-bold">Customer health, at a glance.</h1><p className="mt-2 text-sm text-text-secondary">Your next retention decisions, pipeline movement, and supervised outreach in one view.</p></div>
      <div className="flex flex-wrap gap-3"><Link to="/integrations" className="inline-flex min-h-11 items-center gap-2 rounded-lg border border-border bg-bg-card px-4 text-sm hover:bg-bg-hover"><Users size={16} />Import contacts</Link><Link to="/customers" className="inline-flex min-h-11 items-center gap-2 rounded-lg bg-accent-primary px-4 text-sm font-medium text-white shadow-glow-indigo hover:bg-accent-hover"><Sparkles size={16} />Review health</Link></div>
    </div>
    {error && <p className="mt-5 rounded-lg border border-rose-400/25 bg-rose-400/10 px-4 py-3 text-sm text-rose-500">{error}</p>}

    <div className="mt-8 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
      <MetricCard label="Portfolio health" value={`${insights.averageHealth}/100`} detail={`${customers.length} tracked customer${customers.length === 1 ? "" : "s"}`} icon={HeartPulse} tone="text-emerald-500" />
      <MetricCard label="Attention needed" value={insights.atRisk.length} detail={`${currency.format(insights.atRiskMrr)} MRR at risk`} icon={CircleAlert} tone="text-rose-500" />
      <MetricCard label="Open pipeline" value={currency.format(insights.pipelineValue)} detail={`${deals.filter((deal) => !["closed_won", "closed_lost"].includes(deal.stage)).length} active opportunities`} icon={Workflow} tone="text-cyan-500" />
      <MetricCard label="Agent activity" value={stats?.active_swarm_runs ?? activeRuns.length} detail={`${stats?.cached_resolutions ?? 0} cached resolutions available`} icon={Bot} tone="text-violet-500" />
    </div>

    <div className="mt-8 grid gap-6 xl:grid-cols-[minmax(0,1.3fr)_minmax(20rem,0.7fr)]">
      <section className="glass-card rounded-lg"><div className="flex items-center justify-between gap-3"><div><p className="eyebrow">Health portfolio</p><h2 className="mt-1 text-xl font-semibold">Where to focus this week</h2></div><Link to="/customers" className="inline-flex items-center gap-1 text-sm text-indigo-400 hover:text-indigo-300">All customers <ArrowRight size={15} /></Link></div><div className="mt-7"><HealthRow label="Healthy" count={insights.healthy.length} total={customers.length} color="bg-emerald-500" /><HealthRow label="Watch" count={insights.watch.length} total={customers.length} color="bg-amber-400" /><HealthRow label="Critical" count={insights.atRisk.length} total={customers.length} color="bg-rose-500" /></div><div className="mt-7 grid gap-3 sm:grid-cols-2">{attentionCustomers.map((customer) => <Link to="/customers" key={customer.customer_id} className="rounded-lg border border-border-subtle bg-bg-base/60 p-3 hover:border-indigo-400/40"><div className="flex justify-between gap-3"><span className="truncate font-medium">{customer.name}</span><span className={Number(customer.health_score) < 45 ? "text-rose-500" : "text-amber-500"}>{customer.health_score}</span></div><p className="mt-1 truncate text-xs text-text-secondary">{customer.email || customer.phone || "No contact detail"}</p></Link>)}{!attentionCustomers.length && <p className="py-4 text-sm text-text-secondary">Add or import customers to begin building the health portfolio.</p>}</div></section>

      <section className="glass-card rounded-lg"><div className="flex items-center justify-between"><div><p className="eyebrow">Operations</p><h2 className="mt-1 text-xl font-semibold">Review queue</h2></div><Mail className="text-indigo-400" size={21} /></div><div className="mt-6 space-y-4"><div className="rounded-lg border border-border-subtle bg-bg-base/60 p-4"><div className="flex items-center justify-between"><span className="font-medium">Campaign approval</span><span className="text-amber-500">{pendingCampaigns.length} pending</span></div><p className="mt-1 text-sm text-text-secondary">Review customer messaging before it is dispatched.</p><Link to="/campaigns" className="mt-3 inline-flex items-center gap-1 text-sm text-indigo-400">Open campaigns <ArrowRight size={15} /></Link></div><div className="rounded-lg border border-border-subtle bg-bg-base/60 p-4"><div className="flex items-center justify-between"><span className="font-medium">Agent runs</span><span className={activeRuns.length ? "text-amber-500" : "text-emerald-500"}>{activeRuns.length ? `${activeRuns.length} active` : "Up to date"}</span></div><p className="mt-1 text-sm text-text-secondary">Long-running work continues while your team navigates the CRM.</p><Link to="/agent-runs" className="mt-3 inline-flex items-center gap-1 text-sm text-indigo-400">Inspect runs <ArrowRight size={15} /></Link></div></div></section>
    </div>

    <section className="glass-card mt-8 rounded-lg"><div className="flex flex-wrap items-center justify-between gap-4"><div><p className="eyebrow">Recent intelligence</p><h2 className="mt-1 text-xl font-semibold">Agent activity</h2></div><Link to="/agent-runs" className="text-sm text-indigo-400 hover:text-indigo-300">View all runs</Link></div><div className="mt-5 grid gap-3 md:grid-cols-3">{runs.slice(0, 3).map((run) => <Link to="/agent-runs" key={run.id} className="rounded-lg border border-border-subtle bg-bg-base/60 p-4 hover:border-indigo-400/40"><div className="flex items-center justify-between gap-3"><span className="capitalize font-medium">{run.type.replaceAll("_", " ")}</span><span className={run.status === "complete" ? "text-emerald-500" : ["failed", "cancelled"].includes(run.status) ? "text-rose-500" : "text-amber-500"}>{run.status}</span></div><p className="mt-2 text-xs text-text-secondary">{relativeDate(run.updated_at || run.created_at)}</p></Link>)}{!runs.length && <p className="text-sm text-text-secondary">No agent runs yet. Select customers and start a focused health analysis when the team is ready.</p>}</div></section>
  </>;
}
