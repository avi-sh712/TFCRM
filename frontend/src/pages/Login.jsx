import { ArrowRight, Check, ShieldCheck, Sparkles } from "lucide-react";
import { useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import ThemeToggle from "../components/ThemeToggle";
import { useAuth } from "../lib/auth-context";

const highlights = [
  "Bring contacts, deals, and customer history together.",
  "Turn signals into review-ready retention outreach.",
  "Keep every important campaign under human control.",
];

export default function Login() {
  const { user, login, signup } = useAuth();
  const navigate = useNavigate();
  const [mode, setMode] = useState("login");
  const [identifier, setIdentifier] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const isSignup = mode === "signup";

  if (user) return <Navigate to="/dashboard" replace />;

  async function submit(event) {
    event.preventDefault();
    if (submitting) return;
    setSubmitting(true);
    setError("");
    try {
      if (isSignup) {
        await signup({ email: identifier, username, password, company_name: companyName || null });
      } else {
        await login({ identifier, password });
      }
      navigate("/dashboard");
    } catch (cause) {
      setError(cause.message);
    } finally {
      setSubmitting(false);
    }
  }

  function switchMode() {
    setMode(isSignup ? "login" : "signup");
    setError("");
  }

  return (
    <main className="login-backdrop min-h-screen bg-bg-base p-5 md:p-8">
      <div className="mx-auto flex min-h-[calc(100vh-2.5rem)] max-w-7xl flex-col justify-between md:min-h-[calc(100vh-4rem)]">
        <header className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="grid h-10 w-10 place-items-center rounded-lg bg-accent-primary text-white shadow-glow-indigo"><Sparkles size={20} /></span>
            <div><b className="text-lg">TalentForge</b><p className="text-sm text-text-secondary">Customer success CRM</p></div>
          </div>
          <ThemeToggle />
        </header>

        <div className="grid items-center gap-10 py-10 lg:grid-cols-[minmax(0,28rem)_minmax(0,1fr)] lg:gap-20">
          <form onSubmit={submit} className="w-full rounded-lg border border-border bg-bg-card/95 p-6 shadow-2xl backdrop-blur-md sm:p-8">
            <p className="eyebrow text-indigo-400">{isSignup ? "Create workspace" : "Welcome back"}</p>
            <h1 className="mt-3 text-3xl font-bold">{isSignup ? "Build a sharper customer picture." : "Your customer work, in one place."}</h1>
            <p className="mt-3 text-sm leading-6 text-text-secondary">{isSignup ? "Start with your workspace details. You can import contacts and connect data sources after sign-up." : "Sign in to manage customer health, campaigns, and your team’s AI-assisted follow-through."}</p>

            {isSignup && <>
              <label className="mt-7 block text-sm font-medium">Workspace name<input className="mt-2 w-full rounded-lg border border-border bg-bg-base px-3 py-3 outline-none focus:border-indigo-400" placeholder="Northstar Studio" value={companyName} onChange={(event) => setCompanyName(event.target.value)} maxLength="255" /></label>
              <label className="mt-4 block text-sm font-medium">Username<input className="mt-2 w-full rounded-lg border border-border bg-bg-base px-3 py-3 outline-none focus:border-indigo-400" placeholder="yourname" value={username} onChange={(event) => setUsername(event.target.value)} minLength="3" maxLength="32" required /></label>
            </>}
            <label className={`block text-sm font-medium ${isSignup ? "mt-4" : "mt-7"}`}>{isSignup ? "Email address" : "Email address or username"}<input className="mt-2 w-full rounded-lg border border-border bg-bg-base px-3 py-3 outline-none focus:border-indigo-400" placeholder={isSignup ? "you@company.com" : "you@company.com or yourname"} type={isSignup ? "email" : "text"} value={identifier} onChange={(event) => setIdentifier(event.target.value)} required /></label>
            <label className="mt-4 block text-sm font-medium">Password<input className="mt-2 w-full rounded-lg border border-border bg-bg-base px-3 py-3 outline-none focus:border-indigo-400" placeholder="At least 12 characters" type="password" value={password} onChange={(event) => setPassword(event.target.value)} minLength="12" required /></label>
            {isSignup && <p className="mt-2 text-xs leading-5 text-text-secondary">Usernames can contain letters, numbers, dots, hyphens, and underscores.</p>}
            {error && <p className="mt-4 rounded-lg border border-rose-400/25 bg-rose-400/10 px-3 py-2 text-sm text-rose-500">{error}</p>}
            <button disabled={submitting} className="mt-6 inline-flex min-h-12 w-full items-center justify-center gap-2 rounded-lg bg-accent-primary px-5 font-medium text-white shadow-glow-indigo hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-60">
              {submitting ? "Working..." : isSignup ? "Create workspace" : "Sign in"}<ArrowRight size={17} />
            </button>
            <button className="mt-4 w-full text-sm text-text-secondary underline decoration-border underline-offset-4 hover:text-text-primary" type="button" onClick={switchMode}>
              {isSignup ? "Already have an account? Sign in" : "New to TalentForge? Create a workspace"}
            </button>
          </form>

          <section className="hidden max-w-xl text-white lg:block">
            <p className="eyebrow text-indigo-200">Retention, made operational</p>
            <h2 className="mt-4 text-5xl font-bold leading-tight">See the customer story before the renewal conversation.</h2>
            <p className="mt-5 max-w-lg text-lg leading-8 text-slate-200">TalentForge unifies CRM context, customer health, and supervised AI outreach so your team can act with confidence.</p>
            <div className="mt-9 space-y-4 border-l border-white/25 pl-5 text-slate-100">{highlights.map((highlight) => <p key={highlight} className="flex items-start gap-3"><Check size={18} className="mt-0.5 shrink-0 text-emerald-300" />{highlight}</p>)}</div>
            <div className="mt-12 flex items-center gap-3 text-sm text-slate-200"><ShieldCheck size={18} className="text-emerald-300" />Human approval stays in control of outbound campaigns.</div>
          </section>
        </div>

        <p className="text-xs text-text-secondary">Secure workspace access for customer success teams.</p>
      </div>
    </main>
  );
}
