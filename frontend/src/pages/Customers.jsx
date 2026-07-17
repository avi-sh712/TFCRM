import { ChevronRight, LoaderCircle, Plus, Search, Star, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api } from "../lib/api";

function spectrum(score) {
  if (Number(score) >= 75) return { label: "Healthy", color: "text-emerald-600", bar: "bg-emerald-500" };
  if (Number(score) >= 45) return { label: "Watch", color: "text-amber-500", bar: "bg-amber-400" };
  return { label: "Critical", color: "text-rose-500", bar: "bg-rose-500" };
}

function Rating({ score }) {
  const stars = Math.max(1, Math.min(5, Math.ceil(Number(score || 0) / 20)));
  return <span className="flex items-center gap-0.5" aria-label={`${stars} out of 5 health rating`}>{Array.from({ length: 5 }, (_, index) => <Star key={index} size={14} className={index < stars ? "fill-amber-400 text-amber-400" : "text-slate-600"} />)}</span>;
}

function interactionSummary(interaction) {
  const raw = interaction.raw_payload || "";
  try { return JSON.stringify(JSON.parse(raw)).slice(0, 180); } catch { return String(raw).slice(0, 180); }
}

function Stat({ label, value, tone = "text-blue-600" }) {
  return <section className={`metric-card ${tone}`}><p className="text-sm text-text-secondary">{label}</p><p className="mt-3 text-2xl font-bold text-text-primary">{value}</p></section>;
}

export default function Customers() {
  const [items, setItems] = useState([]);
  const [name, setName] = useState(""); const [email, setEmail] = useState(""); const [phone, setPhone] = useState("");
  const [mrr, setMrr] = useState(""); const [lifetimeValue, setLifetimeValue] = useState(""); const [purchaseCount, setPurchaseCount] = useState("");
  const [selected, setSelected] = useState(null); const [history, setHistory] = useState([]); const [interactions, setInteractions] = useState([]);
  const [interactionType, setInteractionType] = useState("note"); const [interactionDetails, setInteractionDetails] = useState("");
  const [selectedIds, setSelectedIds] = useState([]); const [insights, setInsights] = useState({});
  const [query, setQuery] = useState(""); const [healthFilter, setHealthFilter] = useState("all"); const [showAdd, setShowAdd] = useState(false);
  const [error, setError] = useState(""); const [notice, setNotice] = useState(""); const [adding, setAdding] = useState(false); const [running, setRunning] = useState(false);

  const load = async () => {
    try { const result = await api("/api/customers?limit=100"); setItems(result.items || []); } catch (cause) { setError(cause.message); }
  };
  useEffect(() => { load(); }, []);
  const visibleItems = useMemo(() => items.filter((customer) => {
    const text = `${customer.name} ${customer.email || ""} ${customer.phone || ""}`.toLowerCase();
    return text.includes(query.toLowerCase()) && (healthFilter === "all" || spectrum(customer.health_score).label.toLowerCase() === healthFilter);
  }), [items, query, healthFilter]);
  const selectedCustomers = useMemo(() => items.filter((customer) => selectedIds.includes(customer.customer_id)), [items, selectedIds]);
  const averageHealth = items.length ? Math.round(items.reduce((sum, customer) => sum + Number(customer.health_score || 0), 0) / items.length) : 0;
  const atRisk = items.filter((customer) => Number(customer.health_score || 0) < 45).length;
  const allVisibleSelected = visibleItems.length > 0 && visibleItems.every((customer) => selectedIds.includes(customer.customer_id));

  useEffect(() => {
    if (!selectedIds.length) { setInsights({}); return undefined; }
    let active = true;
    Promise.all(selectedIds.map(async (customerId) => {
      const [healthResult, interactionResult] = await Promise.all([api(`/api/customers/${customerId}/health-history`), api(`/api/customers/${customerId}/interactions?limit=3`)]);
      return [customerId, { history: healthResult.items || [], interactions: interactionResult.items || [] }];
    })).then((results) => { if (active) setInsights(Object.fromEntries(results)); }).catch((cause) => { if (active) setError(cause.message); });
    return () => { active = false; };
  }, [selectedIds]);

  function toggleCustomer(customerId) { setSelectedIds((current) => current.includes(customerId) ? current.filter((id) => id !== customerId) : [...current, customerId]); }
  function toggleAllVisible() { setSelectedIds((current) => allVisibleSelected ? current.filter((id) => !visibleItems.some((customer) => customer.customer_id === id)) : [...new Set([...current, ...visibleItems.map((customer) => customer.customer_id)])]); }

  async function inspect(customer) {
    setSelected(customer); setHistory([]); setInteractions([]); setError("");
    try { const [healthResult, interactionResult] = await Promise.all([api(`/api/customers/${customer.customer_id}/health-history`), api(`/api/customers/${customer.customer_id}/interactions?limit=25`)]); setHistory(healthResult.items || []); setInteractions(interactionResult.items || []); } catch (cause) { setError(cause.message); }
  }
  async function addCustomer(event) {
    event.preventDefault(); if (adding) return; setAdding(true); setError("");
    try { await api("/api/customers", { method: "POST", body: JSON.stringify({ name, email: email || null, phone: phone || null, mrr: Number(mrr || 0), lifetime_value: Number(lifetimeValue || 0), purchase_count: Number(purchaseCount || 0) }) }); setName(""); setEmail(""); setPhone(""); setMrr(""); setLifetimeValue(""); setPurchaseCount(""); setShowAdd(false); setNotice("Customer added to the workspace."); await load(); } catch (cause) { setError(cause.message); } finally { setAdding(false); }
  }
  async function runSelectedAnalysis() {
    if (!selectedIds.length || running) return; setRunning(true); setError("");
    try { const run = await api("/api/agents/run", { method: "POST", body: JSON.stringify({ type: "churn_analysis", config: { customer_ids: selectedIds } }) }); setNotice(`Analysis queued for ${selectedIds.length} customer${selectedIds.length === 1 ? "" : "s"}. Run ${String(run.id).slice(0, 8)} is visible in Agent Runs.`); } catch (cause) { setError(cause.message); } finally { setRunning(false); }
  }
  async function addInteraction(event) {
    event.preventDefault(); if (!selected) return; setError("");
    try { const created = await api(`/api/customers/${selected.customer_id}/interactions`, { method: "POST", body: JSON.stringify({ event_type: interactionType, details: interactionDetails ? { note: interactionDetails } : {} }) }); setInteractions((current) => [created, ...current]); setInteractionDetails(""); setNotice("Interaction recorded for future analysis."); } catch (cause) { setError(cause.message); }
  }

  return <>
    <div className="flex flex-wrap items-end justify-between gap-4"><div><p className="eyebrow text-cyan-600">Customer directory</p><h1 className="mt-2 text-3xl font-bold">Know every customer before the next conversation.</h1><p className="mt-2 text-sm text-text-secondary">Contacts, revenue context, interactions, health history, and AI analysis live in one working record.</p></div><div className="flex flex-wrap gap-3"><button type="button" onClick={() => setShowAdd((show) => !show)} className="inline-flex min-h-11 items-center gap-2 rounded-lg border border-border bg-bg-card px-4 text-sm hover:bg-bg-hover"><Plus size={16} />Add customer</button><button type="button" disabled={!selectedIds.length || running} onClick={runSelectedAnalysis} className="inline-flex min-h-11 items-center gap-2 rounded-lg bg-accent-primary px-5 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-60">{running && <LoaderCircle size={16} className="animate-spin" />}{running ? "Queueing analysis..." : `Run analysis (${selectedIds.length})`}</button></div></div>
    {error && <p className="mt-5 rounded-lg border border-rose-400/25 bg-rose-400/10 px-4 py-3 text-sm text-rose-500">{error}</p>}{notice && <p className="mt-5 rounded-lg border border-emerald-400/25 bg-emerald-400/10 px-4 py-3 text-sm text-emerald-600">{notice}</p>}
    <div className="mt-7 grid gap-4 md:grid-cols-3"><Stat label="Tracked customers" value={items.length} tone="text-blue-600" /><Stat label="Average health" value={`${averageHealth}/100`} tone="text-emerald-600" /><Stat label="Needs attention" value={atRisk} tone="text-rose-500" /></div>
    {showAdd && <form className="glass-card mt-6 grid gap-3 rounded-lg md:grid-cols-3" onSubmit={addCustomer}><input className="rounded-lg border border-border bg-bg-base p-3" value={name} onChange={(event) => setName(event.target.value)} placeholder="Customer or company name" disabled={adding} required /><input className="rounded-lg border border-border bg-bg-base p-3" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="Contact email" type="email" disabled={adding} /><input className="rounded-lg border border-border bg-bg-base p-3" value={phone} onChange={(event) => setPhone(event.target.value)} placeholder="Phone number" disabled={adding} /><input className="rounded-lg border border-border bg-bg-base p-3" value={mrr} onChange={(event) => setMrr(event.target.value)} placeholder="MRR" type="number" min="0" disabled={adding} /><input className="rounded-lg border border-border bg-bg-base p-3" value={lifetimeValue} onChange={(event) => setLifetimeValue(event.target.value)} placeholder="Lifetime value" type="number" min="0" disabled={adding} /><input className="rounded-lg border border-border bg-bg-base p-3" value={purchaseCount} onChange={(event) => setPurchaseCount(event.target.value)} placeholder="Purchase count" type="number" min="0" disabled={adding} /><button disabled={adding} className="inline-flex min-h-11 items-center gap-2 rounded-lg bg-accent-primary px-5 text-white disabled:opacity-60">{adding && <LoaderCircle size={16} className="animate-spin" />}{adding ? "Adding..." : "Save customer"}</button></form>}
    <section className="glass-card mt-6 rounded-lg"><div className="flex flex-wrap items-center justify-between gap-3"><div><p className="eyebrow">Customer list</p><h2 className="mt-1 text-xl font-semibold">Directory and health signals</h2></div><span className="text-sm text-text-secondary">{visibleItems.length} shown</span></div><div className="mt-5 flex flex-wrap gap-3"><label className="flex min-w-[14rem] flex-1 items-center gap-2 rounded-lg border border-border bg-bg-base px-3"><Search size={17} className="text-text-muted" /><input className="w-full bg-transparent py-3 outline-none" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search name, email, or phone" /></label><select value={healthFilter} onChange={(event) => setHealthFilter(event.target.value)} className="rounded-lg border border-border bg-bg-base px-3 py-3 text-sm"><option value="all">All health</option><option value="healthy">Healthy</option><option value="watch">Watch</option><option value="critical">Critical</option></select></div><div className="mt-5 overflow-x-auto"><table className="w-full min-w-[760px] text-left text-sm"><thead><tr className="border-b border-border-subtle text-text-secondary"><th className="w-12 py-3">#</th><th className="w-10"><input type="checkbox" checked={allVisibleSelected} onChange={toggleAllVisible} aria-label="Select visible customers" /></th><th>Name</th><th>Contact</th><th>Health</th><th>Rating</th><th>Revenue</th><th /></tr></thead><tbody>{visibleItems.map((item, index) => { const band = spectrum(item.health_score); return <tr key={item.customer_id} className="border-b border-border-subtle/80 transition-colors hover:bg-bg-hover/50"><td className="py-4 text-text-secondary">{index + 1}</td><td><input type="checkbox" checked={selectedIds.includes(item.customer_id)} onChange={() => toggleCustomer(item.customer_id)} aria-label={`Select ${item.name}`} /></td><td><p className="font-medium">{item.name}</p><p className="mt-1 text-xs text-text-secondary">{item.active_campaign_count || 0} active campaign{item.active_campaign_count === 1 ? "" : "s"}</p></td><td className="text-text-secondary">{item.email || item.phone || "No contact detail"}</td><td><span className={`font-medium ${band.color}`}>{item.health_score}/100</span><p className={`mt-1 text-xs ${band.color}`}>{band.label}</p></td><td><Rating score={item.health_score} /></td><td><p>{Number(item.mrr || 0).toLocaleString()} MRR</p><p className="mt-1 text-xs text-text-secondary">{Number(item.lifetime_value || 0).toLocaleString()} LTV</p></td><td><button type="button" onClick={() => inspect(item)} className="inline-flex items-center gap-1 rounded-lg px-2 py-2 text-sm text-blue-600 hover:bg-blue-500/10">Inspect <ChevronRight size={15} /></button></td></tr>; })}</tbody></table></div>{!visibleItems.length && <p className="py-10 text-center text-sm text-text-secondary">No matching customers. Add a customer or import a CRM/store export from Integrations.</p>}</section>
    {selectedCustomers.length > 0 && <section className="mt-7"><div className="flex items-center justify-between"><div><p className="eyebrow">Selected records</p><h2 className="mt-1 text-xl font-semibold">Customer feedback spectrum</h2></div><button type="button" onClick={() => setSelectedIds([])} className="text-sm text-text-secondary hover:text-text-primary">Clear selection</button></div><div className="mt-4 grid gap-4 xl:grid-cols-3">{selectedCustomers.map((customer) => { const detail = insights[customer.customer_id]; const band = spectrum(customer.health_score); const latestReason = detail?.history?.at(-1)?.reason || "No health-history explanation yet."; return <article key={customer.customer_id} className="glass-card rounded-lg"><div className="flex items-start justify-between gap-3"><div><h3 className="font-semibold">{customer.name}</h3><p className={`mt-1 text-sm ${band.color}`}>{band.label} signal</p></div><Rating score={customer.health_score} /></div><div className="mt-4 h-2 overflow-hidden rounded-full bg-bg-hover"><div className={`h-full ${band.bar}`} style={{ width: `${Math.max(0, Math.min(100, customer.health_score || 0))}%` }} /></div><p className="mt-3 text-sm text-text-secondary">{latestReason}</p><div className="mt-3 space-y-2">{detail?.interactions?.length ? detail.interactions.map((interaction) => <p key={interaction.id} className="rounded-lg border border-border-subtle bg-bg-base p-2 text-xs text-text-secondary"><b className="text-text-primary">{interaction.event_type}:</b> {interactionSummary(interaction)}</p>) : <p className="text-xs text-text-secondary">No recorded interactions yet.</p>}</div></article>; })}</div></section>}
    {selected && <aside className="fixed inset-y-0 right-0 z-50 w-full max-w-md overflow-y-auto border-l border-border bg-bg-card p-6 shadow-2xl"><div className="flex justify-between"><div><p className="eyebrow">Customer record</p><h2 className="mt-2 text-2xl font-bold">{selected.name}</h2></div><button type="button" onClick={() => setSelected(null)} title="Close customer record" className="grid h-9 w-9 place-items-center rounded-lg hover:bg-bg-hover"><X size={18} /></button></div><p className="mt-2 text-sm text-text-secondary">{selected.email || "No email"} | {selected.phone || "No phone"}</p><div className="mt-4 flex items-center gap-3"><Rating score={selected.health_score} /><span className="text-sm text-text-secondary">{selected.health_score}/100 health</span></div><form className="mt-6 border-t border-border-subtle pt-5" onSubmit={addInteraction}><h3 className="font-semibold">Record interaction</h3><select className="mt-3 w-full rounded-lg border border-border bg-bg-base p-3" value={interactionType} onChange={(event) => setInteractionType(event.target.value)}><option value="note">CRM note</option><option value="call">Customer call</option><option value="email">Customer email</option><option value="purchase">Purchase</option><option value="support_ticket">Support ticket</option></select><textarea className="mt-3 min-h-24 w-full rounded-lg border border-border bg-bg-base p-3" value={interactionDetails} onChange={(event) => setInteractionDetails(event.target.value)} placeholder="What happened? This becomes evidence for future AI analysis." /><button className="mt-3 rounded-lg bg-accent-primary px-4 py-2 text-sm text-white">Save interaction</button></form><div className="mt-7 space-y-3"><h3 className="font-semibold">Health history</h3>{history.map((item) => <p key={item.id} className="border-t border-border-subtle pt-3 text-sm"><b>{item.health_score}</b> {item.reason}</p>)}{!history.length && <p className="text-sm text-text-secondary">No health history yet.</p>}<h3 className="pt-3 font-semibold">Interactions</h3>{interactions.map((item) => <p key={item.id} className="border-t border-border-subtle pt-3 text-sm"><b>{item.event_type}</b> {interactionSummary(item)}</p>)}{!interactions.length && <p className="text-sm text-text-secondary">No interactions yet.</p>}</div></aside>}
  </>;
}
