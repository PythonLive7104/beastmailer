import { useEffect, useState } from "react";
import { api } from "../api";
import { Icon } from "../icons";
import { Field, Loader, Modal, Switch, useToast } from "../components/ui";

const BLANK = {
  name: "", email_address: "", username: "",
  imap_host: "", imap_port: 993, imap_use_ssl: true,
  smtp_host: "", smtp_port: 587, smtp_use_tls: true,
  password: "", is_active: true, use_proxy: false,
};

// Hosted mail providers where the recipient sees the provider's IP (not yours),
// and where logging in from rotating IPs tends to trip anti-fraud. Proxying these
// rarely helps and can cause lockouts — so we warn when proxy is enabled on one.
const HOSTED_SMTP = ["gmail", "googlemail", "google.com", "outlook", "office365", "hotmail",
  "live.com", "yahoo", "aol.com", "icloud", "me.com", "zoho", "sendgrid",
  "mailgun", "amazonaws", "postmarkapp", "sparkpostmail", "mandrillapp", "protonmail"];
const isHostedProvider = (host) => {
  const h = (host || "").toLowerCase();
  return HOSTED_SMTP.some((p) => h.includes(p));
};

export default function Mailboxes() {
  const [rows, setRows] = useState(null);
  const [editing, setEditing] = useState(null); // object or null
  const [busy, setBusy] = useState(false);
  const toast = useToast();

  const load = () => api.mailboxes.list().then(setRows);
  useEffect(() => { load(); }, []);

  const save = async () => {
    setBusy(true);
    try {
      const body = { ...editing };
      if (editing.id && !body.password) delete body.password; // keep existing
      if (editing.id) await api.mailboxes.update(editing.id, body);
      else await api.mailboxes.create(body);
      toast("Mailbox saved");
      setEditing(null);
      load();
    } catch (e) {
      toast(`Save failed: ${JSON.stringify(e.detail)}`, "err");
    } finally {
      setBusy(false);
    }
  };

  const test = async (row) => {
    toast("Testing connection…");
    try {
      const r = await api.mailboxes.test(row.id);
      if (r.imap && r.smtp) toast("✓ IMAP and SMTP OK");
      else toast(r.error || "Connection failed", "err");
    } catch { toast("Connection test failed", "err"); }
  };

  const poll = async (row) => {
    try {
      const r = await api.mailboxes.poll(row.id);
      r.ok ? toast(`Polled · ${r.ingested} new`) : toast(r.error, "err");
      load();
    } catch { toast("Poll failed", "err"); }
  };

  const remove = async (row) => {
    if (!confirm(`Delete mailbox "${row.name}"?`)) return;
    await api.mailboxes.remove(row.id);
    toast("Mailbox deleted");
    load();
  };

  if (!rows) return <Loader />;

  return (
    <div className="grid">
      <div className="section-head">
        <span className="page-sub">{rows.length} mailbox{rows.length !== 1 ? "es" : ""} configured</span>
        <button className="btn btn-primary" onClick={() => setEditing({ ...BLANK })}><Icon.plus /> Add mailbox</button>
      </div>

      <div className="card">
        <table className="table">
          <thead>
            <tr><th>Name</th><th>Address</th><th>IMAP / SMTP</th><th>Status</th><th>Last polled</th><th></th></tr>
          </thead>
          <tbody>
            {rows.map((m) => (
              <tr key={m.id}>
                <td className="subj">{m.name}</td>
                <td className="muted">{m.email_address}</td>
                <td className="muted">{m.imap_host} · {m.smtp_host}</td>
                <td>
                  <span className={`badge ${m.is_active ? "badge-sent" : "badge-neutral"}`}>{m.is_active ? "active" : "paused"}</span>
                  {m.use_proxy && <span className="badge badge-received" style={{ marginLeft: 6 }} title="Outgoing SMTP routed through the proxy pool"><Icon.proxy /> proxy</span>}
                  {m.last_error && <span className="badge badge-failed" style={{ marginLeft: 6 }}>error</span>}
                </td>
                <td className="mono">{m.last_polled_at ? new Date(m.last_polled_at).toLocaleString() : "never"}</td>
                <td>
                  <div className="row" style={{ justifyContent: "flex-end", gap: 6 }}>
                    <button className="btn btn-sm" onClick={() => test(m)}><Icon.check /> Test</button>
                    <button className="btn btn-sm" onClick={() => poll(m)}><Icon.refresh /> Poll</button>
                    <button className="btn btn-sm btn-ghost" onClick={() => setEditing({ ...m, password: "" })}><Icon.edit /></button>
                    <button className="btn btn-sm btn-danger" onClick={() => remove(m)}><Icon.trash /></button>
                  </div>
                </td>
              </tr>
            ))}
            {rows.length === 0 && <tr><td colSpan={6}><div className="empty">No mailboxes yet. Add one to start syncing mail.</div></td></tr>}
          </tbody>
        </table>
      </div>

      {editing && (
        <Modal
          title={editing.id ? "Edit mailbox" : "Add mailbox"}
          onClose={() => setEditing(null)}
          footer={<>
            <button className="btn" onClick={() => setEditing(null)}>Cancel</button>
            <button className="btn btn-primary" onClick={save} disabled={busy}>{busy ? "Saving…" : "Save mailbox"}</button>
          </>}
        >
          <MailboxForm value={editing} onChange={setEditing} />
        </Modal>
      )}
    </div>
  );
}

function MailboxForm({ value, onChange }) {
  const set = (k) => (e) => onChange({ ...value, [k]: e?.target ? e.target.value : e });
  return (
    <div>
      <Field label="Display name"><input className="input" value={value.name} onChange={set("name")} placeholder="Sales inbox" /></Field>
      <div className="field-row">
        <Field label="Email address"><input className="input" value={value.email_address} onChange={set("email_address")} placeholder="you@domain.com" /></Field>
        <Field label="Username"><input className="input" value={value.username} onChange={set("username")} placeholder="usually your email" /></Field>
      </div>
      <Field label={value.id ? "Password (leave blank to keep)" : "Password / app password"}>
        <input className="input" type="password" value={value.password} onChange={set("password")} placeholder="••••••••" />
      </Field>

      <h4 style={{ margin: "10px 0 12px", color: "var(--text-muted)" }}>Incoming (IMAP)</h4>
      <div className="field-row">
        <Field label="IMAP host"><input className="input" value={value.imap_host} onChange={set("imap_host")} placeholder="imap.gmail.com" /></Field>
        <Field label="IMAP port"><input className="input" type="number" value={value.imap_port} onChange={set("imap_port")} /></Field>
      </div>
      <div className="row" style={{ marginBottom: 14 }}><Switch checked={value.imap_use_ssl} onChange={(v) => onChange({ ...value, imap_use_ssl: v })} /><span className="page-sub">Use SSL</span></div>

      <h4 style={{ margin: "10px 0 12px", color: "var(--text-muted)" }}>Outgoing (SMTP)</h4>
      <div className="field-row">
        <Field label="SMTP host"><input className="input" value={value.smtp_host} onChange={set("smtp_host")} placeholder="smtp.gmail.com" /></Field>
        <Field label="SMTP port"><input className="input" type="number" value={value.smtp_port} onChange={set("smtp_port")} /></Field>
      </div>
      <div className="row" style={{ marginBottom: 14 }}><Switch checked={value.smtp_use_tls} onChange={(v) => onChange({ ...value, smtp_use_tls: v })} /><span className="page-sub">Use STARTTLS</span></div>
      <div className="row" style={{ marginBottom: value.use_proxy && isHostedProvider(value.smtp_host) ? 8 : 14 }}><Switch checked={value.use_proxy} onChange={(v) => onChange({ ...value, use_proxy: v })} /><span className="page-sub">Send via proxy — route SMTP through a random proxy from the pool</span></div>
      {value.use_proxy && isHostedProvider(value.smtp_host) && (
        <div className="card card-pad" style={{ marginBottom: 14, padding: "10px 12px", borderColor: "var(--warning)" }}>
          <span className="page-sub">
            ⚠ <b>{value.smtp_host}</b> looks like a hosted provider. Recipients see the provider’s IP, not the proxy’s,
            so this won’t improve deliverability — and logging in from rotating IPs can trigger the provider’s anti-fraud
            (account lockouts). Proxies help most with your own SMTP relay.
          </span>
        </div>
      )}

      <div className="row"><Switch checked={value.is_active} onChange={(v) => onChange({ ...value, is_active: v })} /><span className="page-sub">Active — include in polling</span></div>
    </div>
  );
}
