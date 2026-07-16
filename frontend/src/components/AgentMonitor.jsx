import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  Bot,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  CircleDot,
  Clock3,
  Database,
  ExternalLink,
  FileJson2,
  LoaderCircle,
  Send,
  Sparkles,
  WandSparkles,
} from "lucide-react";

const DEFAULT_API_BASE_URL = import.meta.env.VITE_API_URL || window.location.origin;

function apiUrl(path, apiBaseUrl) {
  return new URL(path, apiBaseUrl || DEFAULT_API_BASE_URL).toString();
}

function websocketUrl(sessionId, accessToken, apiBaseUrl) {
  const url = new URL(apiBaseUrl || DEFAULT_API_BASE_URL);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  url.pathname = `/ws/agent/stream/${encodeURIComponent(sessionId)}`;
  url.search = "";
  if (accessToken) {
    url.searchParams.set("access_token", accessToken);
  }
  return url.toString();
}

function formatTime(timestamp) {
  if (!timestamp) return "Now";
  const date = new Date(timestamp);
  return Number.isNaN(date.getTime())
    ? "Now"
    : date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function traceStyle(trace) {
  const text = `${trace.type} ${JSON.stringify(trace.payload || {})}`.toLowerCase();
  if (text.includes("error") || text.includes("retry") || text.includes("failed")) {
    return {
      icon: AlertTriangle,
      dot: "bg-orange-400 shadow-[0_0_12px_3px_rgba(251,146,60,0.42)]",
      label: "text-orange-200",
    };
  }
  if (text.includes("draft") || text.includes("complete") || text.includes("sent")) {
    return {
      icon: CheckCircle2,
      dot: "bg-emerald-400 shadow-[0_0_12px_3px_rgba(52,211,153,0.38)]",
      label: "text-emerald-200",
    };
  }
  if (text.includes("database") || text.includes("tool") || text.includes("mcp")) {
    return {
      icon: Database,
      dot: "bg-cyan-400 shadow-[0_0_12px_3px_rgba(34,211,238,0.38)]",
      label: "text-cyan-200",
    };
  }
  return {
    icon: Bot,
    dot: "animate-pulse-glow bg-violet-400 shadow-[0_0_12px_3px_rgba(167,139,250,0.42)]",
    label: "text-violet-200",
  };
}

function traceTitle(trace) {
  const labels = {
    agent_stream_connected: "Secure agent stream connected",
    node_entry: "Graph node entered",
    database_read: "Customer history read",
    model_call: "Reasoning model invoked",
    tool_error: "Read-only tool retry required",
    draft_complete: "Outreach draft completed",
  };
  return labels[trace.type] || String(trace.type || "Agent update").replaceAll("_", " ");
}

function InspectableBlock({ title, value }) {
  const [open, setOpen] = useState(false);
  const rendered = typeof value === "string" ? value : JSON.stringify(value, null, 2);

  return (
    <div className="overflow-hidden rounded-xl border border-slate-800 bg-slate-950">
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        className="flex w-full items-center justify-between gap-3 border-b border-slate-800/80 px-3 py-2 text-left text-xs text-slate-400 transition-colors hover:bg-slate-900"
      >
        <span className="flex min-w-0 items-center gap-2"><FileJson2 size={14} className="shrink-0 text-slate-500" /><span className="truncate">{title}</span></span>
        {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
      </button>
      {open && <pre className="max-h-52 overflow-auto p-3 font-mono text-[11px] leading-5 text-slate-400">{rendered}</pre>}
    </div>
  );
}

function TimelineStep({ trace, isLast }) {
  const style = traceStyle(trace);
  const Icon = style.icon;
  const payload = trace.payload || {};
  const inspectable = payload.tool_result || payload.analysis || payload.raw || payload;

  return (
    <div className="relative flex gap-4 pb-6 last:pb-0">
      {!isLast && <span className="absolute left-[7px] top-5 h-[calc(100%-12px)] w-px bg-slate-800" />}
      <span className={`relative z-10 mt-1.5 h-4 w-4 shrink-0 rounded-full border-4 border-slate-950 ${style.dot}`} />
      <div className="min-w-0 flex-1">
        <div className="flex items-start justify-between gap-3">
          <div className="flex min-w-0 items-center gap-2">
            <Icon size={15} className={style.label} />
            <p className={`truncate text-sm font-medium capitalize ${style.label}`}>{traceTitle(trace)}</p>
          </div>
          <span className="shrink-0 text-[11px] text-slate-600">{formatTime(trace.timestamp)}</span>
        </div>
        <p className="mt-1 text-xs leading-5 text-slate-500">{payload.message || payload.node_name || "Live orchestration trace received."}</p>
        {Object.keys(payload).length > 0 && <div className="mt-3"><InspectableBlock title="Trace payload" value={inspectable} /></div>}
      </div>
    </div>
  );
}

export default function AgentMonitor({
  sessionId,
  campaignId,
  accessToken,
  initialDraft = "",
  apiBaseUrl,
  onDraftChange,
  onReviewComplete,
}) {
  const [traces, setTraces] = useState([]);
  const [draft, setDraft] = useState(initialDraft);
  const [connectionState, setConnectionState] = useState("connecting");
  const [dispatchState, setDispatchState] = useState("idle");
  const [dispatchError, setDispatchError] = useState("");
  const reconnectTimer = useRef(null);
  const socketRef = useRef(null);
  const shouldReconnect = useRef(true);

  useEffect(() => {
    setDraft(initialDraft);
  }, [initialDraft]);

  useEffect(() => {
    if (!sessionId) {
      setConnectionState("idle");
      return undefined;
    }

    shouldReconnect.current = true;
    const connect = () => {
      setConnectionState("connecting");
      const socket = new WebSocket(websocketUrl(sessionId, accessToken, apiBaseUrl));
      socketRef.current = socket;

      socket.onopen = () => {
        setConnectionState("live");
        socket.send(JSON.stringify({ type: "ping" }));
      };
      socket.onmessage = (event) => {
        try {
          const update = JSON.parse(event.data);
          if (update.type !== "pong") {
            setTraces((current) => [...current.slice(-99), { ...update, id: crypto.randomUUID() }]);
          }
        } catch {
          setTraces((current) => [...current.slice(-99), {
            id: crypto.randomUUID(),
            type: "stream_message",
            timestamp: new Date().toISOString(),
            payload: { raw: event.data },
          }]);
        }
      };
      socket.onclose = () => {
        setConnectionState("offline");
        if (shouldReconnect.current) {
          reconnectTimer.current = window.setTimeout(connect, 3000);
        }
      };
      socket.onerror = () => socket.close();
    };

    connect();
    return () => {
      shouldReconnect.current = false;
      window.clearTimeout(reconnectTimer.current);
      socketRef.current?.close();
    };
  }, [accessToken, apiBaseUrl, sessionId]);

  const connectionLabel = useMemo(() => {
    if (connectionState === "live") return "Live stream";
    if (connectionState === "connecting") return "Connecting";
    if (connectionState === "offline") return "Reconnecting";
    return "Awaiting session";
  }, [connectionState]);

  const updateDraft = useCallback((event) => {
    const nextDraft = event.target.value;
    setDraft(nextDraft);
    onDraftChange?.(nextDraft);
  }, [onDraftChange]);

  const submitReview = useCallback(async (status) => {
    if (!campaignId || dispatchState !== "idle") return;
    setDispatchError("");
    setDispatchState(status);
    try {
      const response = await fetch(
        apiUrl(`/api/campaigns/${encodeURIComponent(campaignId)}/review`, apiBaseUrl),
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
          },
          body: JSON.stringify({ status, draft_content: draft.trim() || undefined }),
        },
      );
      if (!response.ok) {
        const result = await response.json().catch(() => ({}));
        throw new Error(result.detail || "Campaign review could not be completed.");
      }
      onReviewComplete?.(await response.json());
    } catch (error) {
      setDispatchError(error instanceof Error ? error.message : "Campaign review could not be completed.");
    } finally {
      setDispatchState("idle");
    }
  }, [accessToken, apiBaseUrl, campaignId, dispatchState, draft, onReviewComplete]);

  const isDispatching = dispatchState !== "idle";

  return (
    <section className="grid min-h-[calc(100vh-11rem)] gap-6 xl:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
      <div className="glass-card flex min-h-[32rem] flex-col rounded-2xl p-5">
        <div className="flex items-start justify-between gap-4 border-b border-slate-800/80 pb-4">
          <div>
            <p className="flex items-center gap-2 text-sm font-medium text-slate-100"><Bot size={17} className="text-violet-300" /> Agent execution trace</p>
            <p className="mt-1 text-xs text-slate-500">Session {sessionId || "not selected"}</p>
          </div>
          <span className={`flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] ${connectionState === "live" ? "border-emerald-400/20 bg-emerald-400/10 text-emerald-300" : "border-slate-700 bg-slate-900 text-slate-400"}`}>
            <CircleDot size={12} className={connectionState === "live" ? "animate-pulse-glow" : ""} /> {connectionLabel}
          </span>
        </div>

        <div className="mt-5 min-h-0 flex-1 overflow-y-auto pr-2">
          {traces.length ? traces.map((trace, index) => <TimelineStep key={trace.id} trace={trace} isLast={index === traces.length - 1} />) : (
            <div className="flex h-full min-h-72 flex-col items-center justify-center text-center">
              <span className="rounded-xl border border-violet-400/15 bg-violet-400/5 p-3 text-violet-300"><Sparkles size={20} /></span>
              <p className="mt-4 text-sm text-slate-400">Waiting for agent activity</p>
              <p className="mt-1 max-w-xs text-xs leading-5 text-slate-600">Incoming routing, read-only tool, and drafting traces will appear here.</p>
            </div>
          )}
        </div>
      </div>

      <div className="glass-card flex min-h-[32rem] flex-col rounded-2xl p-5">
        <div className="flex items-start justify-between gap-4 border-b border-slate-800/80 pb-4">
          <div>
            <p className="flex items-center gap-2 text-sm font-medium text-slate-100"><WandSparkles size={17} className="text-indigo-300" /> Staged outreach draft</p>
            <p className="mt-1 text-xs text-slate-500">Operator edits are included in the approval request.</p>
          </div>
          <span className="flex items-center gap-1.5 text-xs text-slate-600"><Clock3 size={13} /> Pending review</span>
        </div>

        <label className="mt-5 flex min-h-0 flex-1 flex-col">
          <span className="sr-only">Outreach draft editor</span>
          <textarea
            value={draft}
            onChange={updateDraft}
            placeholder="The staged customer outreach draft will appear here."
            className="min-h-72 flex-1 resize-none rounded-xl border border-slate-800 bg-slate-950 p-4 text-sm leading-6 text-slate-300 outline-none transition-colors placeholder:text-slate-700 focus:border-indigo-400/50 focus:ring-2 focus:ring-indigo-400/10"
          />
        </label>

        {dispatchError && <p className="mt-3 rounded-lg border border-orange-400/20 bg-orange-400/10 px-3 py-2 text-xs text-orange-200">{dispatchError}</p>}

        <div className="mt-5 grid gap-3 sm:grid-cols-2">
          <button
            type="button"
            disabled={!campaignId || isDispatching}
            onClick={() => submitReview("approved")}
            className="flex min-h-11 items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-indigo-500 to-violet-500 px-4 text-sm font-medium text-white shadow-glow-indigo transition-all hover:scale-[1.02] hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {dispatchState === "approved" ? <LoaderCircle size={16} className="animate-spin" /> : <Send size={16} />} Approve & Dispatch Outreach
          </button>
          <button
            type="button"
            disabled={!campaignId || isDispatching}
            onClick={() => submitReview("rejected")}
            className="flex min-h-11 items-center justify-center gap-2 rounded-xl border border-slate-800 px-4 text-sm font-medium text-slate-300 transition-all hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {dispatchState === "rejected" ? <LoaderCircle size={16} className="animate-spin" /> : <ExternalLink size={16} />} Escalate / Redraft Incident
          </button>
        </div>
      </div>
    </section>
  );
}
