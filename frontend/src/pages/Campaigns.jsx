import { LoaderCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth-context";

function label(status) { return String(status || "draft").replaceAll("_", " "); }

export default function Campaigns() {
  const { user } = useAuth();
  const [items, setItems] = useState([]);
  const [customers, setCustomers] = useState([]);
  const [recipientIds, setRecipientIds] = useState([]);
  const [name, setName] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [saving, setSaving] = useState(false);

  const load = () => Promise.all([api("/api/campaigns"), api("/api/customers?limit=100")]).then(([campaigns, customerResult]) => { setItems(campaigns || []); setCustomers(customerResult.items || []); }).catch((cause) => setError(cause.message));
  useEffect(() => { load(); }, []);
  const toggleRecipient = (customerId) => setRecipientIds((current) => current.includes(customerId) ? current.filter((id) => id !== customerId) : [...current, customerId]);

  async function createCampaign(event) {
    event.preventDefault();
    if (saving) return;
    setSaving(true); setError(""); setNotice("");
    try {
      await api("/api/campaigns", { method: "POST", body: JSON.stringify({ name, message_template: message || null, target_segment: { customer_ids: recipientIds } }) });
      setName(""); setMessage(""); setRecipientIds([]); setNotice("Campaign draft created."); await load();
    } catch (cause) { setError(cause.message); } finally { setSaving(false); }
  }
  async function requestReview(campaign) { try { await api(`/api/campaigns/${campaign.id}`, { method: "PATCH", body: JSON.stringify({ status: "pending_review" }) }); setNotice("Campaign sent for human review."); await load(); } catch (cause) { setError(cause.message); } }
  async function decide(campaign, action) { try { await api(`/api/campaigns/${campaign.id}/${action}`, { method: "PATCH" }); setNotice(action === "approve" ? "Campaign approved and dispatch started." : "Campaign returned to draft."); await load(); } catch (cause) { setError(cause.message); } }
  const canReview = user?.role === "admin" || user?.role === "csm";

  return <><div><h1 className="text-3xl font-bold">Campaigns</h1><p className="mt-2 text-sm text-text-secondary">Choose one or more customers, create one message, then send only after human approval.</p></div>{error && <p className="mt-3 text-sm text-rose-300">{error}</p>}{notice && <p className="mt-3 text-sm text-emerald-300">{notice}</p>}<form onSubmit={createCampaign} className="glass-card mt-7 grid gap-4 rounded-lg"><input className="rounded-lg border border-border bg-bg-base p-3" value={name} onChange={(event) => setName(event.target.value)} placeholder="Campaign name" required /><textarea className="min-h-32 rounded-lg border border-border bg-bg-base p-3" value={message} onChange={(event) => setMessage(event.target.value)} placeholder="Message template" required /><div><p className="text-sm font-medium">Recipients ({recipientIds.length})</p><div className="mt-3 grid max-h-48 gap-2 overflow-y-auto sm:grid-cols-2">{customers.map((customer) => <label key={customer.customer_id} className="flex items-center gap-2 rounded border border-border-subtle bg-bg-base p-2 text-sm"><input type="checkbox" checked={recipientIds.includes(customer.customer_id)} onChange={() => toggleRecipient(customer.customer_id)} />{customer.name}<span className="ml-auto text-xs text-text-secondary">{customer.email || "No email"}</span></label>)}{!customers.length && <p className="text-sm text-text-secondary">Add or import customers first.</p>}</div></div><div><button disabled={saving || !recipientIds.length} className="inline-flex min-h-11 items-center gap-2 rounded-lg bg-accent-primary px-5 disabled:opacity-60">{saving && <LoaderCircle size={16} className="animate-spin" />}{saving ? "Creating draft..." : "Create draft"}</button></div></form><section className="glass-card mt-7 rounded-lg"><h2 className="text-xl font-semibold">Campaign workspace</h2>{items.map((item) => <article key={item.id} className="border-t border-border-subtle py-4"><div className="flex flex-wrap items-center justify-between gap-3"><b>{item.name}</b><span className="rounded-full border border-border px-2.5 py-1 text-xs capitalize text-text-secondary">{label(item.status)}</span></div><p className="mt-2 whitespace-pre-wrap text-sm text-text-secondary">{item.message_template || "No message template yet."}</p><p className="mt-2 text-xs text-text-secondary">Recipients: {item.target_segment?.customer_ids?.length || 0} · Sent: {item.sent_count || 0}</p><div className="mt-4 flex flex-wrap gap-3">{item.status === "draft" && <button onClick={() => requestReview(item)} className="rounded-lg border border-indigo-400/30 px-3 py-2 text-sm text-indigo-200">Request review</button>}{item.status === "pending_review" && (canReview ? <><button onClick={() => decide(item, "approve")} className="rounded-lg bg-emerald-500/15 px-3 py-2 text-sm text-emerald-200">Approve & dispatch</button><button onClick={() => decide(item, "reject")} className="rounded-lg border border-rose-400/30 px-3 py-2 text-sm text-rose-200">Return to draft</button></> : <p className="text-sm text-text-secondary">Awaiting CSM or admin approval.</p>)}</div></article>)}{!items.length && <p className="py-8 text-center text-sm text-text-secondary">No campaigns yet. Create a draft above to start an approval workflow.</p>}</section></>;
}
