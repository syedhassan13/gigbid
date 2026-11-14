import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, errText, setToken } from "../lib/api/client";

export default function Login() {
  const nav = useNavigate();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(e: React.FormEvent) {
    e.preventDefault(); setBusy(true); setErr("");
    const { data, error } = mode === "login"
      ? await api.POST("/api/auth/login", { body: { email, password } })
      : await api.POST("/api/auth/register", { body: { email, password } });
    setBusy(false);
    if (error || !data) return setErr(errText(error) || "Sign-in failed");
    setToken(data.token);
    nav(data.user.persona ? "/inbox" : "/onboarding");
  }
  return (
    <main style={{ maxWidth: 420, margin: "10vh auto", padding: 16 }}>
      <div className="panel">
        <h1>GigBid</h1>
        <p className="muted small">Your multi-agent freelancer copilot. Nothing reaches a client until you approve it.</p>
        <form onSubmit={submit}>
          <label htmlFor="email">Email</label>
          <input id="email" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
          <label htmlFor="password">Password</label>
          <input id="password" type="password" autoComplete={mode === "login" ? "current-password" : "new-password"} required minLength={8}
            value={password} onChange={(e) => setPassword(e.target.value)} />
          {err && <div className="banner bad" role="alert" style={{ marginTop: 10 }}>{err}</div>}
          <div className="row" style={{ marginTop: 14 }}>
            <button className="btn primary" disabled={busy} type="submit">{mode === "login" ? "Sign in" : "Create account"}</button>
            <button className="btn" type="button" onClick={() => setMode(mode === "login" ? "register" : "login")}>
              {mode === "login" ? "New here? Register" : "Have an account? Sign in"}
            </button>
          </div>
        </form>
      </div>
    </main>
  );
}
