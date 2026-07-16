import { LoaderCircle, Star } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api } from "../lib/api";

function spectrum(score) {
  if (score >= 75) return { label: "Positive", color: "text-emerald-300", bar: "bg-emerald-400" };
  if (score >= 45) return { label: "Watch", color: "text-amber-300", bar: "bg-amber-400" };
  return { label: "Critical", color: "text-rose-300", bar: "bg-rose-400" };
}

function Rating({ score }) {
  const stars = Math.max(1, Math.min(5, Math.ceil(Number(score || 0) / 20)));
  return <span className="flex items-center gap-0.5" aria-label={`${stars} out of 5 health rating`}>{Array.from({ length: 5 }, (_, index) => <Star key={index} size={15} className={index < stars ? "fill-amber-400 text-amber-400" : "text-slate-700"} />)}</span>;
}

function interactionSummary(interaction) {
  const raw = interaction.raw_payload || "";
  try {
    const parsed = JSON.parse(raw);
    return JSON.stringify(parsed).slice(0, 180);
  } catch {
    return String(raw).slice(0, 180);
  }
}

export default function Customers() {
  const [items, setItems] = useState([]);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [mrr, setMrr] = useState("");
  const [lifetimeValue, setLifetimeValue] = useState("");
  const [purchaseCount, setPurchaseCount] = useState("");
  const [selected, setSelected] = useState(null);
  const [history, setHistory] = useState([]);
  const [interactions, setInteractions] = useState([]);
  const [interactionType, setInteractionType] = useState("note");
  const [interactionDetails, setInteractionDetails] = useState("");
  const [selectedIds, setSelectedIds] = useState([]);
  const [insights, setInsights] = useState({});
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [adding, setAdding] = useState(false);
  const [running, setRunning] = useState(false);

  const selectedCustomers = useMemo(() => items.filter((customer) => selectedIds.includes(customer.customer_id)), [items, selectedIds]);
  const load = () => api("/api/customers?limit=100").then((result) => setItems(result.items || [])).catch((cause) => setError(cause.message));
  useEffect(() => { load(); }, []);

  useEffect(() => {
    if (!selectedIds.length) {
      setInsights({});
      return undefined;
    }
    let active = true;
    void Promise.all(selectedIds.map(async (customerId) => {
      const [healthResult, interactionResult] = await Promise.all([
        api(`/api/customers/${customerId}/health-history`),
        api(`/api/customers/${customerId}/interactions?limit=3`),
      ]);
      return [customerId, { history: healthResult.items || [], interactions: interactionResult.items || [] }];
    })).then((results) => {
      if (active) setInsights(Object.fromEntries(results));
    }).catch((cause) => {
      if (active) setError(cause.message);
    });
    return () => { active = false; };
  }, [selectedIds]);

  function toggleCustomer(customerId) {
    setSelectedIds((current) => current.includes(customerId) ? current.filter((id) => id !== customerId) : [...current, customerId]);
  }

  async function inspect(customer) {
    setSelected(customer);
    setHistory([]);
    setInteractions([]);
    try {
      const [healthResult, interactionResult] = await Promise.all([api(`/api/customers/${customer.customer_id}/health-history`), api(`/api/customers/${customer.customer_id}/interactions?limit=25`)]);
      setHistory(healthResult.items || []);
      setInteractions(interactionResult.items || []);
    } catch (cause) {
      setError(cause.message);
    }
  }

  async function addCustomer(event) {
    event.preventDefault();
    if (adding) return;
    setAdding(true);
    setError("");
    try {
      await api("/api/customers", { method: "POST", body: JSON.stringify({ name, email: email || null, phone: phone || null, mrr: Number(mrr || 0), lifetime_value: Number(lifetimeValue || 0), purchase_count: Number(purchaseCount || 0) }) });
      setName(""); setEmail(""); setPhone(""); setMrr(""); setLifetimeValue(""); setPurchaseCount("");
      setNotice("Customer added.");
      await load();
    } catch (cause) {
      setError(cause.message);
    } finally {
      setAdding(false);
    }
  }

  async function runSelectedAnalysis() {
    if (!selectedIds.length || running) return;
    setRunning(true);
    setError("");
    try {
      const run = await api("/api/agents/run", { method: "POST", body: JSON.stringify({ type: "churn_analysis", config: { customer_ids: selectedIds } }) });
      setNotice(`Analysis queued for ${selectedIds.length} customer${selectedIds.length === 1 ? "" : "s"}. Track run ${String(run.id).slice(0, 8)} in Agent Runs.`);
    } catch (cause) {
      setError(cause.message);
    } finally {
      setRunning(false);
    }
  }

  const allSelected = items.length > 0 && selectedIds.length === items.length;
  async function addInteraction(event) { event.preventDefault(); if (!selected) return; try { const details = interactionDetails ? { note: interactionDetails } : {}; const created = await api(`/api/customers/${selected.customer_id}/interactions`, { method: "POST", body: JSON.stringify({ event_type: interactionType, details }) }); setInteractions((current) => [created, ...current]); setInteractionDetails(""); setNotice("Interaction recorded for live analysis."); } catch (cause) { setError(cause.message); } }
  return <><div className="flex flex-wrap items-end justify-between gap-4"><div><h1 className="text-3xl font-bold">Customers</h1><p className="mt-2 text-sm text-text-secondary">Store customer contacts, purchase history, interactions, and AI health analysis in one place.</p></div><button type="button" disabled={!selectedIds.length || running} onClick={runSelectedAnalysis} className="inline-flex min-h-11 items-center gap-2 rounded-lg bg-accent-primary px-5 disabled:cursor-not-allowed disabled:opacity-60">{running && <LoaderCircle size={16} className="animate-spin" />}{running ? "Queueing analysis..." : `Run analysis (${selectedIds.length})`}</button></div>{error && <p className="mt-3 text-sm text-rose-300">{error}</p>}{notice && <p className="mt-3 text-sm text-emerald-300">{notice}</p>}<form className="glass-card mt-6 grid gap-3 rounded-lg md:grid-cols-3" onSubmit={addCustomer}><input className="rounded-lg border border-border bg-bg-base p-3" value={name} onChange={(event) => setName(event.target.value)} placeholder="Customer or company name" disabled={adding} required /><input className="rounded-lg border border-border bg-bg-base p-3" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="Contact email" type="email" disabled={adding} /><input className="rounded-lg border border-border bg-bg-base p-3" value={phone} onChange={(event) => setPhone(event.target.value)} placeholder="Phone number" disabled={adding} /><input className="rounded-lg border border-border bg-bg-base p-3" value={mrr} onChange={(event) => setMrr(event.target.value)} placeholder="MRR" type="number" min="0" disabled={adding} /><input className="rounded-lg border border-border bg-bg-base p-3" value={lifetimeValue} onChange={(event) => setLifetimeValue(event.target.value)} placeholder="Lifetime value" type="number" min="0" disabled={adding} /><input className="rounded-lg border border-border bg-bg-base p-3" value={purchaseCount} onChange={(event) => setPurchaseCount(event.target.value)} placeholder="Purchase count" type="number" min="0" disabled={adding} /><button disabled={adding} className="inline-flex min-h-11 items-center gap-2 rounded-lg bg-accent-primary px-5 disabled:opacity-60">{adding && <LoaderCircle size={16} className="animate-spin" />}{adding ? "Adding..." : "Add customer"}</button></form><section className="glass-card mt-6 overflow-x-auto rounded-lg"><table className="w-full text-left text-sm"><thead><tr className="text-text-secondary"><th className="w-10"><input type="checkbox" checked={allSelected} onChange={() => setSelectedIds(allSelected ? [] : items.map((item) => item.customer_id))} aria-label="Select all customers" /></th><th>Name</th><th>Contact</th><th>Status</th><th>Health</th><th>Rating</th><th>Revenue</th><th /></tr></thead><tbody>{items.map((item) => <tr key={item.customer_id} className="border-t border-border-subtle"><td className="py-4"><input type="checkbox" checked={selectedIds.includes(item.customer_id)} onChange={() => toggleCustomer(item.customer_id)} aria-label={`Select ${item.name}`} /></td><td>{item.name}</td><td>{item.email || item.phone || "-"}</td><td className={spectrum(item.health_score).color}>{item.status}</td><td>{item.health_score}</td><td><Rating score={item.health_score} /></td><td>{item.mrr} MRR / {item.lifetime_value} LTV</td><td><button onClick={() => inspect(item)} className="text-indigo-300">Inspect</button></td></tr>)}</tbody></table>{!items.length && <p className="py-8 text-center text-sm text-text-secondary">No customers yet. Add one above or import a CSV from Integrations.</p>}</section>{selectedCustomers.length > 0 && <section className="mt-7"><div className="flex items-center justify-between"><div><h2 className="text-xl font-semibold">Customer feedback spectrum</h2><p className="mt-1 text-sm text-text-secondary">Ratings use saved health scores. Evidence below comes from recorded interactions and health-history reasons.</p></div><button onClick={() => setSelectedIds([])} className="text-sm text-text-secondary">Clear selection</button></div><div className="mt-4 grid gap-4 xl:grid-cols-3">{selectedCustomers.map((customer) => { const detail = insights[customer.customer_id]; const band = spectrum(customer.health_score); const latestReason = detail?.history?.at(-1)?.reason || "No health-history explanation yet."; return <article key={customer.customer_id} className="glass-card rounded-lg"><div className="flex items-start justify-between gap-3"><div><h3 className="font-semibold">{customer.name}</h3><p className={`mt-1 text-sm ${band.color}`}>{band.label} health signal</p></div><Rating score={customer.health_score} /></div><div className="mt-4 h-2 overflow-hidden rounded-full bg-slate-800"><div className={`h-full ${band.bar}`} style={{ width: `${Math.max(0, Math.min(100, customer.health_score || 0))}%` }} /></div><p className="mt-3 text-sm text-text-secondary">Score: {customer.health_score}/100</p><p className="mt-3 border-t border-border-subtle pt-3 text-sm">{latestReason}</p><div className="mt-3 space-y-2">{detail?.interactions?.length ? detail.interactions.map((interaction) => <p key={interaction.id} className="rounded border border-border-subtle bg-bg-base p-2 text-xs text-text-secondary"><b className="text-slate-300">{interaction.event_type}:</b> {interactionSummary(interaction)}</p>) : <p className="text-xs text-text-secondary">No recorded interactions yet.</p>}</div></article>; })}</div></section>}{selected && <aside className="fixed inset-y-0 right-0 z-50 w-full max-w-md overflow-y-auto border-l border-border bg-bg-card p-7 shadow-2xl"><button onClick={() => setSelected(null)} className="text-sm text-text-secondary">Close</button><h2 className="mt-6 text-2xl font-bold">{selected.name}</h2><p className="mt-2 text-sm text-text-secondary">{selected.email || "No email"} · {selected.phone || "No phone"}</p><div className="mt-3 flex items-center gap-3"><Rating score={selected.health_score} /><span className="text-sm text-text-secondary">{selected.health_score}/100 health</span></div><form className="mt-6 border-t border-border-subtle pt-4" onSubmit={addInteraction}><h3 className="font-semibold">Record interaction</h3><select className="mt-3 w-full rounded-lg border border-border bg-bg-base p-3" value={interactionType} onChange={(event) => setInteractionType(event.target.value)}><option value="note">CRM note</option><option value="call">Customer call</option><option value="email">Customer email</option><option value="purchase">Purchase</option><option value="support_ticket">Support ticket</option></select><textarea className="mt-3 min-h-24 w-full rounded-lg border border-border bg-bg-base p-3" value={interactionDetails} onChange={(event) => setInteractionDetails(event.target.value)} placeholder="What happened? This becomes evidence for future AI analysis." /><button className="mt-3 rounded-lg bg-accent-primary px-4 py-2 text-sm">Save interaction</button></form><div className="mt-6 space-y-3"><h3 className="font-semibold">Health history</h3>{history.map((item) => <p key={item.id} className="border-t border-border-subtle pt-3 text-sm"><b>{item.health_score}</b> {item.reason}</p>)}{!history.length && <p className="text-sm text-text-secondary">No health history yet.</p>}<h3 className="pt-3 font-semibold">Interactions</h3>{interactions.map((item) => <p key={item.id} className="border-t border-border-subtle pt-3 text-sm"><b>{item.event_type}</b> {interactionSummary(item)}</p>)}{!interactions.length && <p className="text-sm text-text-secondary">No interactions yet.</p>}</div></aside>}</>;
}
