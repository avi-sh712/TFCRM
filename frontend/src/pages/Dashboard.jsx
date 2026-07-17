import {
  ArrowRight,
  Bot,
  CircleAlert,
  FileUp,
  HeartPulse,
  Mail,
  ShoppingBag,
  Sparkles,
  Users,
  Workflow,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";

const currency = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
const pipelineStages = [
  ["new", "New"], ["contacted", "Contacted"], ["qualified", "Qualified"],
  ["proposal", "Proposal"], ["closed_won", "Won"], ["closed_lost", "Lost"],
];

function relativeDate(value) {
  if (!value) return "No recent activity";
  const hours = Math.max(0, Math.round((Date.now() - new Date(value).getTime()) / 3_600_000));
  if (hours < 1) return "Updated just now";
  if (hours < 24) return `Updated ${hours}h ago`;
  return `Updated ${Math.round(hours / 24)}d ago`;
}

function MetricCard({ label, value, detail, icon: Icon, tone = "text-blue-500" }) {
  return <section className={`metric-card ${tone}`}><div className="flex items-start justify-between gap-4"><div><p className="text-sm text-text-secondary">{label}</p><p className="mt-4 text-3xl font-bold text-text-primary">{value}</p></div><span className="grid h-10 w-10 place-items-center rounded-lg bg-current/10"><Icon size={19} /></span></div><p className="mt-4 text-sm text-text-secondary">{detail}</p></section>;
}

function HealthRow({ label, count, total, color }) {
  const percent = total ? Math.round((count / total) * 100) : 0;
  return <div className="mt-4"><div className="flex justify-between text-sm"><span>{label}</span><span className="text-text-secondary">{count} customers</span></div><div className="mt-2 h-2 overflow-hidden rounded-full bg-bg-hover"><div className={`h-full rounded-full ${color}`} style={{ width: `${percent}%` }} /></div></div>;
}

function ColumnChart({ values }) {
  const max = Math.max(...values.map((item) => item.value), 1);
  return <div className="mt-7 flex h-48 items-end gap-3 border-b border-border-subtle pb-7">{values.map((item) => <div key={item.label} className="flex min-w-0 flex-1 flex-col items-center justify-end gap-2"><span className="text-xs text-text-secondary">{item.value ? currency.format(item.value) : "-"}</span><div title={`${item.label}: ${currency.format(item.value)}`} className={`w-full rounded-t-md ${item.color}`} style={{ height: `${Math.max(6, Math.round((item.value / max) * 112))}px` }} /><span className="truncate text-xs text-text-secondary">{item.label}</span></div>)}</div>;
}

function ValueRow({ label, value, max, color }) {
  const width = value ? Math.max(2, Math.round((value / max) * 100)) : 0;
  return <div className="mt-5"><div className="flex items-center justify-between text-sm"><span>{label}</span><span className="font-medium">{currency.format(value)}</span></div><div className="mt-2 h-2 overflow-hidden rounded-full bg-bg-hover"><div className={`h-full rounded-full ${color}`} style={{ width: `${width}%` }} /></div></div>;
}

function ActivityIcon({ kind }) {
  if (kind === "store") return <ShoppingBag size={16} className="text-emerald-600" />;
  if (kind === "import") return <FileUp size={16} className="text-cyan-600" />;
  if (kind === "campaign") return <Mail size={16} className="text-blue-600" />;
  return <Bot size={16} className="text-violet-600" />;
}

export default function Dashboard() {
  const [stats, setStats] = useState(null);
  const [campaigns, setCampaigns] = useState([]);
  const [runs, setRuns] = useState([]);
  const [customers, setCustomers] = useState([]);
  const [deals, setDeals] = useState([]);
  const [activity, setActivity] = useState([]);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const [overview, campaignList, runList, customerResult, dealList, activityResult] = await Promise.all([
          api("/api/stats/overview"), api("/api/campaigns"), api("/api/agents/runs"),
          api("/api/customers?limit=100"), api("/api/deals"), api("/api/activity"),
        ]);
        if (!active) return;
        setStats(overview); setCampaigns(campaignList || []); setRuns(runList || []);
        setCustomers(customerResult.items || []); setDeals(dealList || []); setActivity(activityResult.items || []); setError("");
      } catch (cause) { if (active) setError(cause.message); }
    }
    load();
    const id = setInterval(load, 15_000);
    return () => { active = false; clearInterval(id); };
  }, []);

  const insights = useMemo(() => {
    const atRisk = customers.filter((customer) => Number(customer.health_score || 0) < 45);
    const watch = customers.filter((customer) => { const score = Number(customer.health_score || 0); return score >= 45 && score < 75; });
    const healthy = customers.filter((customer) => Number(customer.health_score || 0) >= 75);
    const sumMrr = (items) => items.reduce((sum, item) => sum + Number(item.mrr || 0), 0);
    const averageHealth = customers.length ? Math.round(customers.reduce((sum, customer) => sum + Number(customer.health_score || 0), 0) / customers.length) : 0;
    const pipelineValue = deals.filter((deal) => !["closed_won", "closed_lost"].includes(deal.stage)).reduce((sum, deal) => sum + Number(deal.value || 0), 0);
    return { atRisk, watch, healthy, averageHealth, pipelineValue, protectedMrr: sumMrr(healthy), watchMrr: sumMrr(watch), atRiskMrr: sumMrr(atRisk) };
  }, [customers, deals]);

  const pendingCampaigns = campaigns.filter((campaign) => campaign.status === "pending_review");
  const activeRuns = runs.filter((run) => ["queued", "running"].includes(run.status));
  const attentionCustomers = [...insights.atRisk, ...insights.watch].sort((a, b) => Number(a.health_score) - Number(b.health_score)).slice(0, 4);
  const pipelineChart = pipelineStages.map(([stage, label]) => ({ label, value: deals.filter((deal) => deal.stage === stage).reduce((sum, deal) => sum + Number(deal.value || 0), 0), color: stage === "closed_lost" ? "bg-rose-500" : stage === "closed_won" ? "bg-emerald-500" : "bg-blue-500" }));
  const largestValue = Math.max(insights.protectedMrr, insights.watchMrr, insights.atRiskMrr, 1);

  return <>
    <div className="flex flex-wrap items-end justify-between gap-5"><div><p className="eyebrow text-cyan-600">Workspace overview</p><h1 className="mt-2 text-3xl font-bold">Customer health, made actionable.</h1><p className="mt-2 text-sm text-text-secondary">See value, risk, pipeline movement, connected data, and AI operations in one calm working view.</p></div><div className="flex flex-wrap gap-3"><Link to="/integrations" className="inline-flex min-h-11 items-center gap-2 rounded-lg border border-border bg-bg-card px-4 text-sm hover:bg-bg-hover"><ShoppingBag size={16} />Connect data</Link><Link to="/customers" className="inline-flex min-h-11 items-center gap-2 rounded-lg bg-accent-primary px-4 text-sm font-medium text-white shadow-glow-indigo hover:bg-accent-hover"><Sparkles size={16} />Review health</Link></div></div>
    {error && <p className="mt-5 rounded-lg border border-rose-400/25 bg-rose-400/10 px-4 py-3 text-sm text-rose-500">{error}</p>}

    <div className="mt-8 grid gap-4 md:grid-cols-2 xl:grid-cols-4"><MetricCard label="Portfolio health" value={`${insights.averageHealth}/100`} detail={`${customers.length} tracked customer${customers.length === 1 ? "" : "s"}`} icon={HeartPulse} tone="text-emerald-600" /><MetricCard label="Revenue exposure" value={currency.format(insights.atRiskMrr)} detail={`${insights.atRisk.length} customer${insights.atRisk.length === 1 ? "" : "s"} need attention`} icon={CircleAlert} tone="text-rose-500" /><MetricCard label="Open pipeline" value={currency.format(insights.pipelineValue)} detail={`${deals.filter((deal) => !["closed_won", "closed_lost"].includes(deal.stage)).length} active opportunities`} icon={Workflow} tone="text-blue-600" /><MetricCard label="AI activity" value={stats?.active_swarm_runs ?? activeRuns.length} detail={`${stats?.cached_resolutions ?? 0} cached resolutions available`} icon={Bot} tone="text-violet-600" /></div>

    <div className="mt-8 grid gap-6 xl:grid-cols-[minmax(0,1.25fr)_minmax(20rem,0.75fr)]"><section className="glass-card rounded-lg"><div className="flex items-center justify-between gap-3"><div><p className="eyebrow">Pipeline analytics</p><h2 className="mt-1 text-xl font-semibold">Opportunity value by stage</h2></div><Link to="/deals" className="inline-flex items-center gap-1 text-sm text-blue-600 hover:text-blue-500">Open pipeline <ArrowRight size={15} /></Link></div><ColumnChart values={pipelineChart} /></section><section className="glass-card rounded-lg"><p className="eyebrow">Value at a glance</p><h2 className="mt-1 text-xl font-semibold">MRR by customer health</h2><div className="mt-2"><ValueRow label="Protected value" value={insights.protectedMrr} max={largestValue} color="bg-emerald-500" /><ValueRow label="Watch value" value={insights.watchMrr} max={largestValue} color="bg-amber-400" /><ValueRow label="Exposed value" value={insights.atRiskMrr} max={largestValue} color="bg-rose-500" /></div><p className="mt-6 text-xs text-text-secondary">The bars scale to the largest health segment: {currency.format(largestValue)}.</p></section></div>

    <div className="mt-8 grid gap-6 xl:grid-cols-[minmax(0,1.15fr)_minmax(20rem,0.85fr)]"><section className="glass-card rounded-lg"><div className="flex items-center justify-between gap-3"><div><p className="eyebrow">Health portfolio</p><h2 className="mt-1 text-xl font-semibold">Where to focus this week</h2></div><Link to="/customers" className="inline-flex items-center gap-1 text-sm text-blue-600 hover:text-blue-500">All customers <ArrowRight size={15} /></Link></div><div className="mt-7"><HealthRow label="Healthy" count={insights.healthy.length} total={customers.length} color="bg-emerald-500" /><HealthRow label="Watch" count={insights.watch.length} total={customers.length} color="bg-amber-400" /><HealthRow label="Critical" count={insights.atRisk.length} total={customers.length} color="bg-rose-500" /></div><div className="mt-7 grid gap-3 sm:grid-cols-2">{attentionCustomers.map((customer) => <Link to="/customers" key={customer.customer_id} className="rounded-lg border border-border-subtle bg-bg-base/60 p-3 hover:border-blue-400/40"><div className="flex justify-between gap-3"><span className="truncate font-medium">{customer.name}</span><span className={Number(customer.health_score) < 45 ? "text-rose-500" : "text-amber-500"}>{customer.health_score}</span></div><p className="mt-1 truncate text-xs text-text-secondary">{customer.email || customer.phone || "No contact detail"}</p></Link>)}{!attentionCustomers.length && <p className="py-4 text-sm text-text-secondary">Add or import customers to begin building the health portfolio.</p>}</div></section>
      <section className="glass-card rounded-lg"><div className="flex items-center justify-between"><div><p className="eyebrow">Operational feed</p><h2 className="mt-1 text-xl font-semibold">Changes and AI activity</h2></div><Bot className="text-violet-600" size={21} /></div><div className="mt-5 max-h-[22rem] space-y-1 overflow-y-auto pr-1">{activity.slice(0, 8).map((item) => <div key={item.id} className="flex gap-3 border-b border-border-subtle py-3 last:border-0"><span className="mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-bg-hover"><ActivityIcon kind={item.kind} /></span><div className="min-w-0 flex-1"><div className="flex items-start justify-between gap-3"><p className="font-medium">{item.title}</p><span className={item.status === "failed" ? "text-rose-500" : item.status === "running" || item.status === "queued" ? "text-amber-500" : "text-emerald-600"}>{item.status}</span></div><p className="mt-1 text-sm text-text-secondary">{item.detail}</p><p className="mt-1 text-xs text-text-muted">{relativeDate(item.timestamp)}</p></div></div>)}{!activity.length && <p className="py-8 text-sm text-text-secondary">The activity feed will populate as you import data, run AI analysis, create campaigns, and receive store events.</p>}</div></section></div>

    <section className="glass-card mt-8 rounded-lg"><div className="flex flex-wrap items-center justify-between gap-4"><div><p className="eyebrow">Review queue</p><h2 className="mt-1 text-xl font-semibold">Retention work that needs a person</h2></div><Link to="/campaigns" className="text-sm text-blue-600 hover:text-blue-500">Open campaigns</Link></div><div className="mt-5 grid gap-3 md:grid-cols-2"><div className="rounded-lg border border-border-subtle bg-bg-base/60 p-4"><div className="flex items-center justify-between"><span className="font-medium">Campaign approval</span><span className="text-amber-500">{pendingCampaigns.length} pending</span></div><p className="mt-1 text-sm text-text-secondary">Review customer messaging before it is dispatched.</p></div><div className="rounded-lg border border-border-subtle bg-bg-base/60 p-4"><div className="flex items-center justify-between"><span className="font-medium">Agent runs</span><span className={activeRuns.length ? "text-amber-500" : "text-emerald-600"}>{activeRuns.length ? `${activeRuns.length} active` : "Up to date"}</span></div><p className="mt-1 text-sm text-text-secondary">Background AI continues while your team works in the CRM.</p></div></div></section>
  </>;
}
