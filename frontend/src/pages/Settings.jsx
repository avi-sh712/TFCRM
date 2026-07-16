import { useState } from "react";
import { LoaderCircle } from "lucide-react";
import { useAuth } from "../lib/auth-context";

export default function Settings() {
  const { user, updateProfile } = useAuth();
  const [email, setEmail] = useState(user?.email || "");
  const [username, setUsername] = useState(user?.username || "");
  const [companyName, setCompanyName] = useState(user?.company_name || "");
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [saving, setSaving] = useState(false);

  async function save(event) {
    event.preventDefault();
    setSaving(true);
    setError("");
    setNotice("");
    try {
      await updateProfile({ email, username: username || undefined, company_name: companyName || null, ...(newPassword ? { current_password: currentPassword, new_password: newPassword } : {}) });
      setCurrentPassword("");
      setNewPassword("");
      setNotice("Profile updated.");
    } catch (cause) {
      setError(cause.message);
    } finally {
      setSaving(false);
    }
  }

  return <><h1 className="text-3xl font-bold">Profile settings</h1><p className="mt-2 text-sm text-text-secondary">Update your workspace name, username, sign-in email, or password.</p>{error && <p className="mt-3 text-sm text-rose-300">{error}</p>}{notice && <p className="mt-3 text-sm text-emerald-300">{notice}</p>}<form onSubmit={save} className="glass-card mt-7 max-w-2xl rounded-lg"><label className="block text-sm">Workspace name<input className="mt-2 w-full rounded-lg border border-border bg-bg-base p-3" value={companyName} onChange={(event) => setCompanyName(event.target.value)} maxLength="255" /></label><label className="mt-5 block text-sm">Username<input className="mt-2 w-full rounded-lg border border-border bg-bg-base p-3" value={username} onChange={(event) => setUsername(event.target.value)} minLength="3" maxLength="32" /></label><label className="mt-5 block text-sm">Sign-in email<input className="mt-2 w-full rounded-lg border border-border bg-bg-base p-3" type="email" value={email} onChange={(event) => setEmail(event.target.value)} required /></label><div className="mt-7 border-t border-border-subtle pt-5"><h2 className="text-lg font-semibold">Change password</h2><label className="mt-3 block text-sm">Current password<input className="mt-2 w-full rounded-lg border border-border bg-bg-base p-3" type="password" value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} /></label><label className="mt-4 block text-sm">New password<input className="mt-2 w-full rounded-lg border border-border bg-bg-base p-3" type="password" minLength="12" value={newPassword} onChange={(event) => setNewPassword(event.target.value)} /></label></div><button disabled={saving} className="mt-7 inline-flex min-h-11 items-center gap-2 rounded-lg bg-accent-primary px-5 disabled:opacity-60">{saving && <LoaderCircle size={16} className="animate-spin" />}{saving ? "Saving..." : "Save settings"}</button></form></>;
}
