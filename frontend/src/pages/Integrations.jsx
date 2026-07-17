import { Copy, Database, LoaderCircle, ShoppingBag, Trash2, Webhook, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api, apiBaseUrl } from "../lib/api";
import { useAuth } from "../lib/auth-context";

function BusyButton({ busy, children, className = "", ...props }) {
  return <button disabled={busy} className={`inline-flex min-h-11 items-center justify-center gap-2 rounded-lg px-5 transition-opacity disabled:cursor-not-allowed disabled:opacity-60 ${className}`} {...props}>{busy && <LoaderCircle size={16} className="animate-spin" />}{children}</button>;
}

function ConnectionPanel({ source, endpoint, onDismiss }) {
  const secret = source?.config?.webhook_secret;
  if (!source || !secret) return null;
  const example = JSON.stringify({
    event_type: "order.paid",
    payload: {
      customer: { first_name: "Maya", last_name: "Chen", email: "maya@example.com", phone: "+1 555 0100", total_spent: "842.00", orders_count: 4 },
    },
  }, null, 2);
  return <section className="mt-6 rounded-lg border border-emerald-400/25 bg-emerald-400/10 p-5"><div className="flex flex-wrap items-start justify-between gap-4"><div><p className="eyebrow text-emerald-600">Store connection created</p><h3 className="mt-1 font-semibold">Use this endpoint from your store backend or automation.</h3></div><button type="button" onClick={onDismiss} title="Close connection details" className="grid h-9 w-9 place-items-center rounded-lg hover:bg-bg-hover"><X size={18} /></button></div><div className="mt-4 grid gap-4 lg:grid-cols-2"><div><p className="text-xs font-medium text-text-secondary">POST URL</p><div className="mt-2 flex gap-2"><code className="min-w-0 flex-1 break-all rounded-lg border border-border bg-bg-base p-3 text-xs">{endpoint}</code><button type="button" title="Copy endpoint" onClick={() => navigator.clipboard.writeText(endpoint)} className="grid h-10 w-10 place-items-center rounded-lg border border-border bg-bg-card"><Copy size={16} /></button></div></div><div><p className="text-xs font-medium text-text-secondary">HMAC secret</p><div className="mt-2 flex gap-2"><code className="min-w-0 flex-1 break-all rounded-lg border border-border bg-bg-base p-3 text-xs">{secret}</code><button type="button" title="Copy HMAC secret" onClick={() => navigator.clipboard.writeText(secret)} className="grid h-10 w-10 place-items-center rounded-lg border border-border bg-bg-card"><Copy size={16} /></button></div></div></div><p className="mt-4 text-sm text-text-secondary">Sign the raw JSON body with HMAC-SHA256 and send it in the <code>X-TalentForge-Webhook-Signature</code> header. TalentForge upserts customers by email and records the event as CRM history.</p><details className="mt-4 rounded-lg border border-border bg-bg-base/70 p-3"><summary className="cursor-pointer text-sm font-medium">Example order event</summary><pre className="mt-3 overflow-x-auto text-xs text-text-secondary">{example}</pre></details></section>;
}

export default function Integrations() {
  const { user } = useAuth();
  const [items, setItems] = useState([]);
  const [importJobs, setImportJobs] = useState([]);
  const [file, setFile] = useState(null);
  const [name, setName] = useState("");
  const [serverUrl, setServerUrl] = useState("");
  const [connection, setConnection] = useState(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [uploading, setUploading] = useState(false);
  const [registering, setRegistering] = useState(false);
  const [creatingWebhook, setCreatingWebhook] = useState(false);
  const [creatingStore, setCreatingStore] = useState(false);
  const [cancellingId, setCancellingId] = useState("");
  const [deletingId, setDeletingId] = useState("");
  const endpoint = `${apiBaseUrl || window.location.origin}/api/integrations/webhook/${user?.id || "your-workspace-id"}`;

  const load = async () => {
    try {
      const [sources, jobs] = await Promise.all([api("/api/integrations"), api("/api/integrations/csv-jobs")]);
      setItems(sources || []);
      setImportJobs(jobs || []);
    } catch { /* Action failures are surfaced where the action occurs. */ }
  };

  useEffect(() => { load(); const id = setInterval(load, 5000); return () => clearInterval(id); }, []);
  const storeSources = useMemo(() => items.filter((item) => item.type === "commerce_webhook"), [items]);
  const eventSources = useMemo(() => items.filter((item) => item.type === "api_webhook"), [items]);

  async function uploadCsv(event) {
    event.preventDefault();
    if (!file || uploading) return;
    setUploading(true); setError(""); setNotice("");
    try {
      const form = new FormData(); form.append("file", file);
      const result = await api("/api/integrations/csv-upload", { method: "POST", body: form });
      setNotice(`Import ${String(result.id).slice(0, 8)} is queued and continues in the background.`);
      setFile(null); event.currentTarget.reset(); await load(); setError("");
    } catch (cause) { setError(cause.message); } finally { setUploading(false); }
  }

  async function cancelImport(jobId) {
    if (cancellingId) return;
    setCancellingId(jobId); setError("");
    try { await api(`/api/integrations/csv-jobs/${jobId}/cancel`, { method: "POST" }); setNotice("Import cancelled."); await load(); setError(""); } catch (cause) { setError(cause.message); } finally { setCancellingId(""); }
  }

  async function registerConnector(event) {
    event.preventDefault();
    if (registering) return;
    setRegistering(true); setError(""); setNotice("");
    try { await api("/api/integrations/mcp-connector", { method: "POST", body: JSON.stringify({ name, server_url: serverUrl, allowed_tools: [] }) }); setName(""); setServerUrl(""); setNotice("Read-only data connector registered."); await load(); } catch (cause) { setError(cause.message); } finally { setRegistering(false); }
  }

  async function createConnection(path, setBusy, message) {
    setBusy(true); setError(""); setNotice("");
    try { const created = await api(path, { method: "POST" }); setConnection(created); setNotice(message); await load(); setError(""); } catch (cause) { setError(cause.message); } finally { setBusy(false); }
  }

  async function deleteSource(sourceId) {
    if (deletingId || !window.confirm("Delete this integration? New events from it will be rejected.")) return;
    setDeletingId(sourceId); setError("");
    try { await api(`/api/integrations/${sourceId}`, { method: "DELETE" }); if (connection?.id === sourceId) setConnection(null); setNotice("Integration deleted."); await load(); setError(""); } catch (cause) { setError(cause.message); } finally { setDeletingId(""); }
  }

  return <>
    <div className="flex flex-wrap items-end justify-between gap-4"><div><p className="eyebrow text-cyan-600">Connected data</p><h1 className="mt-2 text-3xl font-bold">Bring your customer story together.</h1><p className="mt-2 text-sm text-text-secondary">Import historical contacts or stream purchase and product events into the same customer timeline your team and AI use.</p></div><span className="rounded-lg border border-border bg-bg-card px-3 py-2 text-sm text-text-secondary">{items.length} active connection{items.length === 1 ? "" : "s"}</span></div>
    {error && <p className="mt-5 rounded-lg border border-rose-400/25 bg-rose-400/10 px-4 py-3 text-sm text-rose-500">{error}</p>}
    {notice && <p className="mt-5 rounded-lg border border-emerald-400/25 bg-emerald-400/10 px-4 py-3 text-sm text-emerald-600">{notice}</p>}

    <div className="mt-7 grid gap-6 xl:grid-cols-3">
      <section className="glass-card rounded-lg xl:col-span-1"><div className="flex items-start justify-between"><div><p className="eyebrow">Historical data</p><h2 className="mt-1 text-xl font-semibold">Contacts or store export</h2></div><Database className="text-cyan-500" size={21} /></div><p className="mt-3 text-sm text-text-secondary">Use a standard CRM export or commerce export with customer, email, total spend, and order count columns.</p><form className="mt-5 space-y-3" onSubmit={uploadCsv}><input className="block w-full text-sm text-text-secondary" type="file" accept=".csv" onChange={(event) => setFile(event.target.files?.[0] || null)} disabled={uploading} required /><BusyButton busy={uploading} className="w-full bg-accent-primary text-white" type="submit">{uploading ? "Uploading export..." : "Import customer data"}</BusyButton></form></section>

      <section className="glass-card rounded-lg xl:col-span-1"><div className="flex items-start justify-between"><div><p className="eyebrow">Live store sync</p><h2 className="mt-1 text-xl font-semibold">Store customer events</h2></div><ShoppingBag className="text-emerald-500" size={21} /></div><p className="mt-3 text-sm text-text-secondary">Create a signed endpoint for your store backend, Zapier, Make, or custom app. Customer and order events update the CRM without sharing your store admin password.</p><BusyButton busy={creatingStore} type="button" onClick={() => createConnection("/api/integrations/commerce-webhook-source", setCreatingStore, "Store sync connection created. Copy the endpoint and secret now.")} className="mt-5 w-full bg-emerald-600 text-white hover:bg-emerald-700">{creatingStore ? "Creating connection..." : "Create store endpoint"}</BusyButton></section>

      <section className="glass-card rounded-lg xl:col-span-1"><div className="flex items-start justify-between"><div><p className="eyebrow">Product telemetry</p><h2 className="mt-1 text-xl font-semibold">App event webhook</h2></div><Webhook className="text-violet-500" size={21} /></div><p className="mt-3 text-sm text-text-secondary">Send product activity, support signals, and cancellation events into customer history for retention analysis.</p><BusyButton busy={creatingWebhook} type="button" onClick={() => createConnection("/api/integrations/webhook-source", setCreatingWebhook, "Product event webhook created. Copy the endpoint and secret now.")} className="mt-5 w-full border border-violet-400/30 text-violet-600 hover:bg-violet-400/10">{creatingWebhook ? "Creating webhook..." : "Create event webhook"}</BusyButton></section>
    </div>

    <ConnectionPanel source={connection} endpoint={endpoint} onDismiss={() => setConnection(null)} />

    <div className="mt-7 grid gap-6 xl:grid-cols-[minmax(0,1.2fr)_minmax(18rem,0.8fr)]">
      <section className="glass-card rounded-lg"><div className="flex items-center justify-between"><div><p className="eyebrow">Background work</p><h2 className="mt-1 text-xl font-semibold">Recent customer imports</h2></div><span className="text-sm text-text-secondary">{importJobs.length} jobs</span></div><div className="mt-5 space-y-3">{importJobs.slice(0, 6).map((job) => <div key={job.id} className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border-subtle bg-bg-base/55 p-3 text-sm"><span className="min-w-0 truncate font-medium">{job.filename}</span><div className="flex items-center gap-3"><span className={job.status === "complete" ? "text-emerald-600" : ["failed", "cancelled"].includes(job.status) ? "text-rose-500" : "inline-flex items-center gap-1 text-amber-500"}>{["queued", "running"].includes(job.status) && <LoaderCircle size={13} className="animate-spin" />}{job.status === "complete" ? `${job.rows_imported} imported` : job.status}</span>{["queued", "running"].includes(job.status) && <button type="button" onClick={() => cancelImport(job.id)} disabled={Boolean(cancellingId)} className="grid h-8 w-8 place-items-center rounded-lg border border-border text-rose-500 disabled:opacity-60" title="Cancel import">{cancellingId === job.id ? <LoaderCircle size={13} className="animate-spin" /> : <X size={14} />}</button>}</div></div>)}{!importJobs.length && <p className="py-7 text-sm text-text-secondary">No imports yet. Upload a CRM or store customer export to begin.</p>}</div></section>

      <section className="glass-card rounded-lg"><p className="eyebrow">Read-only intelligence</p><h2 className="mt-1 text-xl font-semibold">MCP connector</h2><p className="mt-3 text-sm text-text-secondary">Register approved read-only data access for deeper customer investigations.</p><form className="mt-5 space-y-3" onSubmit={registerConnector}><input className="w-full rounded-lg border border-border bg-bg-base p-3" placeholder="Connection name" value={name} onChange={(event) => setName(event.target.value)} disabled={registering} required /><input className="w-full rounded-lg border border-border bg-bg-base p-3" placeholder="MCP server URL" value={serverUrl} onChange={(event) => setServerUrl(event.target.value)} disabled={registering} required /><BusyButton busy={registering} className="w-full bg-accent-primary text-white" type="submit">{registering ? "Registering..." : "Register connector"}</BusyButton></form></section>
    </div>

    <section className="glass-card mt-7 rounded-lg"><div className="flex flex-wrap items-center justify-between gap-4"><div><p className="eyebrow">Connections</p><h2 className="mt-1 text-xl font-semibold">Data sources in this workspace</h2></div><span className="text-sm text-text-secondary">Store: {storeSources.length} | Product events: {eventSources.length}</span></div><div className="mt-5 grid gap-3 md:grid-cols-2">{items.map((item) => <article key={item.id} className="flex items-center justify-between gap-3 rounded-lg border border-border-subtle bg-bg-base/55 p-4"><div className="min-w-0"><p className="truncate font-medium">{item.name}</p><p className="mt-1 text-xs text-text-secondary">{item.type.replaceAll("_", " ")} | {item.status}{item.last_sync ? ` | synced ${new Date(item.last_sync).toLocaleString()}` : ""}</p></div><button type="button" onClick={() => deleteSource(item.id)} disabled={Boolean(deletingId)} title="Delete connection" className="grid h-9 w-9 shrink-0 place-items-center rounded-lg border border-rose-400/30 text-rose-500 disabled:opacity-60">{deletingId === item.id ? <LoaderCircle size={14} className="animate-spin" /> : <Trash2 size={16} />}</button></article>)}{!items.length && <p className="py-5 text-sm text-text-secondary">No data sources connected yet.</p>}</div></section>
  </>;
}
