import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth";
import { Icon } from "../icons";
import { useTheme } from "../theme";
import { Field, useToast } from "../components/ui";

export default function Auth({ mode = "login" }) {
  const [tab, setTab] = useState(mode);
  const [form, setForm] = useState({ username: "", email: "", password: "" });
  const [busy, setBusy] = useState(false);
  const { login, register } = useAuth();
  const { theme, toggle } = useTheme();
  const nav = useNavigate();
  const toast = useToast();

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      if (tab === "login") await login(form.username, form.password);
      else await register(form.username, form.email, form.password);
      nav("/");
    } catch (err) {
      toast(err.detail?.error || "Something went wrong", "err");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="auth-screen">
      <button className="btn icon-btn auth-theme" onClick={toggle} title="Toggle theme">
        {theme === "dark" ? <Icon.sun /> : <Icon.moon />}
      </button>

      <div className="auth-brand-side">
        <div className="brand" style={{ padding: 0 }}>
          <div className="brand-logo" style={{ width: 46, height: 46 }}><Icon.mailbox /></div>
          <div>
            <div className="brand-name" style={{ fontSize: 18 }}>BeastMailer <span className="nowrap">Auto-Reply</span></div>
            <div className="brand-sub">Admin Panel</div>
          </div>
        </div>
        <h1 className="auth-headline">Your inbox, on autopilot.</h1>
        <p className="auth-tagline">
          Connect all your mailboxes, watch replies land, and let subject-based rules answer
          for you — from one dashboard.
        </p>
        <ul className="auth-points">
          <li><Icon.check /> Auto-reply by subject rules</li>
          <li><Icon.check /> IMAP + SMTP, credentials encrypted</li>
          <li><Icon.check /> Live sent / received activity feed</li>
        </ul>
      </div>

      <div className="auth-form-side">
        <div className="auth-card">
          <div className="auth-tabs">
            <button className={tab === "login" ? "active" : ""} onClick={() => setTab("login")}>Log in</button>
            <button className={tab === "signup" ? "active" : ""} onClick={() => setTab("signup")}>Sign up</button>
          </div>
          <h2 style={{ marginBottom: 4 }}>{tab === "login" ? "Welcome back" : "Create your account"}</h2>
          <p className="page-sub" style={{ marginBottom: 20 }}>
            {tab === "login" ? "Log in to reach your dashboard." : "Get started in a few seconds."}
          </p>

          <form onSubmit={submit}>
            <Field label="Username"><input className="input" value={form.username} onChange={set("username")} autoFocus required /></Field>
            {tab === "signup" && (
              <Field label="Email"><input className="input" type="email" value={form.email} onChange={set("email")} /></Field>
            )}
            <Field label="Password">
              <input className="input" type="password" value={form.password} onChange={set("password")}
                placeholder={tab === "signup" ? "At least 8 characters" : ""} required />
            </Field>
            <button className="btn btn-primary" style={{ width: "100%", justifyContent: "center", marginTop: 6 }} disabled={busy}>
              {busy ? "Please wait…" : tab === "login" ? "Log in" : "Create account"}
            </button>
          </form>

          <div className="auth-switch">
            {tab === "login" ? (
              <>New here? <a onClick={() => setTab("signup")}>Create an account</a></>
            ) : (
              <>Already have an account? <a onClick={() => setTab("login")}>Log in</a></>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
