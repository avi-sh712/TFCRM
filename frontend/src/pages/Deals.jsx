import { useEffect, useMemo, useState } from "react";
import { api } from "../lib/api";

const stages = [
  ["new", "New lead"],
  ["contacted", "Contacted"],
  ["qualified", "Qualified"],
  ["proposal", "Proposal"],
  ["closed_won", "Closed won"],
  ["closed_lost", "Closed lost"],
];

const money = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });

export default function Deals() {
  const [deals, setDeals] = useState([]);
  const [customers, setCustomers] = useState([]);
  const [customerId, setCustomerId] = useState("");
  const [name, setName] = useState("");
  const [value, setValue] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  const groupedDeals = useMemo(() => Object.fromEntries(stages.map(([stage]) => [stage, deals.filter((deal) => deal.stage === stage)])), [deals]);

  async function load() {
    try {
      const [dealResult, customerResult] = await Promise.all([api("/api/deals"), api("/api/customers?limit=100")]);
      setDeals(dealResult || []);
      setCustomers(customerResult.items || []);
    } catch (cause) {
      setError(cause.message);
    }
  }

  useEffect(() => { load(); }, []);

  async function createDeal(event) {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      await api("/api/deals", {
        method: "POST",
        body: JSON.stringify({ customer_id: customerId, name, value: Number(value || 0) }),
      });
      setName("");
      setValue("");
      await load();
    } catch (cause) {
      setError(cause.message);
    } finally {
      setSaving(false);
    }
  }

  async function moveDeal(deal, stage) {
    try {
      const updated = await api(`/api/deals/${deal.id}`, { method: "PATCH", body: JSON.stringify({ stage }) });
      setDeals((current) => current.map((item) => item.id === updated.id ? updated : item));
    } catch (cause) {
      setError(cause.message);
    }
  }

  return <><div className="flex flex-wrap items-end justify-between gap-4"><div><h1 className="text-3xl font-bold">Deals pipeline</h1><p className="mt-2 text-sm text-text-secondary">Move opportunities from first contact to a closed outcome.</p></div></div>{error && <p className="mt-3 text-sm text-rose-300">{error}</p>}<form onSubmit={createDeal} className="glass-card mt-7 grid gap-3 rounded-lg md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_9rem_auto]"><select value={customerId} onChange={(event) => setCustomerId(event.target.value)} className="rounded-lg border border-border bg-bg-base p-3" required><option value="">Choose a customer</option>{customers.map((customer) => <option key={customer.customer_id} value={customer.customer_id}>{customer.name}</option>)}</select><input value={name} onChange={(event) => setName(event.target.value)} className="rounded-lg border border-border bg-bg-base p-3" placeholder="Deal name" required /><input value={value} onChange={(event) => setValue(event.target.value)} className="rounded-lg border border-border bg-bg-base p-3" placeholder="Value" type="number" min="0" step="1" /><button disabled={saving || !customers.length} className="rounded-lg bg-accent-primary px-5 py-3 disabled:cursor-not-allowed disabled:opacity-50">{saving ? "Creating..." : "Create deal"}</button></form>{!customers.length && <p className="mt-3 text-sm text-text-secondary">Add or import a customer before creating a deal.</p>}<section className="mt-7 grid gap-4 xl:grid-cols-3">{stages.map(([stage, label]) => <div key={stage} className="min-h-48 rounded-lg border border-border-subtle bg-bg-surface p-4"><div className="flex items-center justify-between"><h2 className="font-semibold">{label}</h2><span className="text-sm text-text-secondary">{groupedDeals[stage].length}</span></div><div className="mt-4 space-y-3">{groupedDeals[stage].map((deal) => <article key={deal.id} className="rounded-lg border border-border bg-bg-card p-4"><p className="font-medium">{deal.name}</p><p className="mt-1 text-sm text-text-secondary">{money.format(deal.value || 0)}</p><select value={deal.stage} onChange={(event) => moveDeal(deal, event.target.value)} className="mt-4 w-full rounded-lg border border-border bg-bg-base p-2 text-sm">{stages.map(([nextStage, nextLabel]) => <option key={nextStage} value={nextStage}>{nextLabel}</option>)}</select></article>)}{!groupedDeals[stage].length && <p className="py-6 text-center text-sm text-text-secondary">No deals</p>}</div></div>)}</section></>;
}
