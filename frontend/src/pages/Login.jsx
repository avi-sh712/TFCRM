import { useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { useAuth } from "../lib/auth-context";

export default function Login() {
  const { user, login, signup } = useAuth();
  const navigate = useNavigate();
  const [mode, setMode] = useState("login");
  const [email, setEmail] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [error, setError] = useState("");
  const isSignup = mode === "signup";

  if (user) return <Navigate to="/dashboard" replace />;

  async function submit(event) {
    event.preventDefault();
    setError("");
    try {
      if (isSignup) {
        await signup({ email, username, password, company_name: companyName || null });
      } else {
        await login({ identifier: email, password });
      }
      navigate("/dashboard");
    } catch (cause) {
      setError(cause.message);
    }
  }

  return <main className="grid min-h-screen place-items-center bg-bg-base p-6"><form onSubmit={submit} className="w-full max-w-md rounded-lg border border-border bg-bg-card p-8"><h1 className="text-3xl font-bold">TalentForge</h1><p className="mt-2 text-sm text-text-secondary">{isSignup ? "Create your CRM workspace." : "Sign in to your CRM workspace."}</p>{isSignup && <><input className="mt-6 w-full rounded-lg border border-border bg-bg-base p-3" placeholder="Company name (optional)" value={companyName} onChange={(e) => setCompanyName(e.target.value)} maxLength="255" /><input className="mt-3 w-full rounded-lg border border-border bg-bg-base p-3" placeholder="Username" value={username} onChange={(e) => setUsername(e.target.value)} minLength="3" maxLength="32" required /></>}<input className="w-full rounded-lg border border-border bg-bg-base p-3" style={{ marginTop: isSignup ? "0.75rem" : "1.5rem" }} placeholder={isSignup ? "Email" : "Email or username"} type={isSignup ? "email" : "text"} value={email} onChange={(e) => setEmail(e.target.value)} required /><input className="mt-3 w-full rounded-lg border border-border bg-bg-base p-3" placeholder="Password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} minLength="12" required />{isSignup && <p className="mt-2 text-xs text-text-secondary">Username: 3-32 letters, numbers, dots, hyphens, or underscores. Password: at least 12 characters.</p>}{error && <p className="mt-3 text-sm text-rose-300">{error}</p>}<button className="mt-5 w-full rounded-lg bg-accent-primary p-3">{isSignup ? "Create workspace" : "Sign in"}</button><button className="mt-3 w-full text-sm text-text-secondary underline" type="button" onClick={() => { setMode(isSignup ? "login" : "signup"); setError(""); }}>{isSignup ? "Already have an account? Sign in" : "New here? Create a workspace"}</button></form></main>;
}
