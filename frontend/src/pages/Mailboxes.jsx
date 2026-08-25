import { useEffect, useState } from "react";
import { api } from "../api";
import { Icon } from "../icons";
import { Field, Loader, Modal, Switch, useToast } from "../components/ui";

const BLANK = {
  name: "", email_address: "", username: "",
  imap_host: "", imap_port: 993, imap_use_ssl: true,
  smtp_host: "", smtp_port: 587, smtp_use_tls: true,
  password: "", is_active: true, use_proxy: false,
  scan_spam: true, extra_folders: "",
  poll_interval_seconds: 10, reply_delay_minutes: 10,
};

// Connection presets keyed by provider. `match` autodetects from the email domain;
// `note` warns about the provider's auth quirk (app passwords, OAuth) at setup time.
const PRESETS = [
  {
    id: "gmail", label: "Gmail / Google Workspace",
    match: ["gmail.com", "googlemail.com"],
    imap_host: "imap.gmail.com", imap_port: 993, imap_use_ssl: true,
    smtp_host: "smtp.gmail.com", smtp_port: 587, smtp_use_tls: true,
    note: "Requires an App Password (Google account → Security → App passwords). Your normal password will be rejected.",
  },
  {
    id: "yahoo", label: "Yahoo Mail",
    match: ["yahoo.com", "yahoo.co", "ymail.com", "rocketmail.com"],
    imap_host: "imap.mail.yahoo.com", imap_port: 993, imap_use_ssl: true,
    smtp_host: "smtp.mail.yahoo.com", smtp_port: 465, smtp_use_tls: false,
    note: "App Password mandatory (Yahoo → Account Security → Generate app password). Yahoo throttles quickly — keep volume modest.",
  },
  {
    id: "outlook", label: "Outlook / Hotmail / Microsoft 365",
    match: ["outlook.com", "hotmail.com", "live.com", "msn.com", "office365.com"],
    imap_host: "outlook.office365.com", imap_port: 993, imap_use_ssl: true,
    smtp_host: "smtp.office365.com", smtp_port: 587, smtp_use_tls: true,
    note: "⚠ Microsoft is disabling password (basic) IMAP/SMTP auth in favour of OAuth. Password login may fail on newer accounts — this app cannot do OAuth yet.",
  },
  {
    id: "zoho", label: "Zoho Mail",
    match: ["zoho.com", "zohomail.com"],
    imap_host: "imap.zoho.com", imap_port: 993, imap_use_ssl: true,
    smtp_host: "smtp.zoho.com", smtp_port: 465, smtp_use_tls: false,
    note: "Use an app-specific password if 2FA is on. Free plans may need IMAP enabled in Zoho settings first.",
  },
  {
    id: "icloud", label: "iCloud Mail",
    match: ["icloud.com", "me.com", "mac.com"],
    imap_host: "imap.mail.me.com", imap_port: 993, imap_use_ssl: true,
    smtp_host: "smtp.mail.me.com", smtp_port: 587, smtp_use_tls: true,
    note: "App-specific password required (appleid.apple.com → Sign-In & Security).",
  },
  {
    id: "custom", label: "Other / custom (enter manually)",
    match: [],
    note: "Enter your provider's IMAP and SMTP settings. 993 = IMAP SSL; SMTP 587 = STARTTLS, 465 = SSL.",
  },
];

const presetForEmail = (email) => {
  const domain = (email || "").split("@")[1]?.toLowerCase() || "";
  return PRESETS.find((p) => p.match.some((d) => domain === d || domain.endsWith("." + d)));
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
  const [config, setConfig] = useState(null); // workspace defaults, for inherited timing
  const [editing, setEditing] = useState(null); // object or null
  const [busy, setBusy] = useState(false);
  const toast = useToast();

  const load = () => api.mailboxes.list().then(setRows);
  useEffect(() => { load(); api.config.get().then(setConfig); }, []);

  const save = async () => {
    setBusy(true);
    try {
      const body = { ...editing };
      delete body._preset; // UI-only field, not part of the model
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
      if (r.imap && r.smtp) toast(`✓ IMAP and SMTP OK · scanning ${(r.folders || ["INBOX"]).join(", ")}`);
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
            <tr><th>Name</th><th>Address</th><th>IMAP / SMTP</th><th>Status</th><th>Poll · Delay</th><th>Last polled</th><th></th></tr>
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
                  {m.scan_spam && <span className="badge badge-neutral" style={{ marginLeft: 6 }} title="Spam/Junk folder is scanned as well as the inbox">spam</span>}
                  {m.last_error && <span className="badge badge-failed" style={{ marginLeft: 6 }}>error</span>}
                </td>
                <td className="muted mono" title={
                  m.poll_interval_seconds == null || m.reply_delay_minutes == null
                    ? "* inherited from the workspace defaults on the Configuration page"
                    : "Set on this account"
                }>
                  {config
                    ? `${m.poll_interval_seconds ?? config.poll_interval_seconds}s · ` +
                      `${m.reply_delay_minutes ?? config.reply_delay_minutes}m` +
                      (m.poll_interval_seconds == null || m.reply_delay_minutes == null ? " *" : "")
                    : "—"}
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
            {rows.length === 0 && <tr><td colSpan={7}><div className="empty">No mailboxes yet. Add one to start syncing mail.</div></td></tr>}
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
  const setNum = (k) => (e) => {
    const raw = e.target.value;
    onChange({ ...value, [k]: raw === "" ? null : Number(raw) });
  };

  // Apply a preset's host/port/TLS. Username defaults to the email if unset.
  const applyPreset = (preset) => {
    if (!preset || preset.id === "custom") { onChange({ ...value, _preset: "custom" }); return; }
    onChange({
      ...value, _preset: preset.id,
      imap_host: preset.imap_host, imap_port: preset.imap_port, imap_use_ssl: preset.imap_use_ssl,
      smtp_host: preset.smtp_host, smtp_port: preset.smtp_port, smtp_use_tls: preset.smtp_use_tls,
      username: value.username || value.email_address,
    });
  };

  // When the email domain changes and no preset was chosen manually, autodetect one.
  const onEmail = (e) => {
    const email = e.target.value;
    const next = { ...value, email_address: email };
    const guess = presetForEmail(email);
    if (guess && value._preset !== "custom" && !value.id) {
      Object.assign(next, {
        _preset: guess.id,
        imap_host: guess.imap_host, imap_port: guess.imap_port, imap_use_ssl: guess.imap_use_ssl,
        smtp_host: guess.smtp_host, smtp_port: guess.smtp_port, smtp_use_tls: guess.smtp_use_tls,
        username: value.username || email,
      });
    }
    onChange(next);
  };

  const activePreset = PRESETS.find((p) => p.id === value._preset)
    || presetForEmail(value.email_address) || PRESETS.find((p) => p.id === "custom");

  return (
    <div>
      <Field label="Display name"><input className="input" value={value.name} onChange={set("name")} placeholder="Sales inbox" /></Field>
      <div className="field-row">
        <Field label="Email address"><input className="input" value={value.email_address} onChange={onEmail} placeholder="you@domain.com" /></Field>
        <Field label="Username"><input className="input" value={value.username} onChange={set("username")} placeholder="usually your email" /></Field>
      </div>
      <Field label="Provider">
        <select className="input" value={activePreset.id} onChange={(e) => applyPreset(PRESETS.find((p) => p.id === e.target.value))}>
          {PRESETS.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
        </select>
      </Field>
      {activePreset.note && (
        <div className="card card-pad" style={{ margin: "0 0 14px", padding: "10px 12px", borderColor: "var(--warning)" }}>
          <span className="page-sub">{activePreset.note}</span>
        </div>
      )}
      <Field label={value.id ? "Password (leave blank to keep)" : "Password / app password"}>
        <input className="input" type="password" value={value.password} onChange={set("password")} placeholder="••••••••" />
      </Field>

      <h4 style={{ margin: "10px 0 12px", color: "var(--text-muted)" }}>Incoming (IMAP)</h4>
      <div className="field-row">
        <Field label="IMAP host"><input className="input" value={value.imap_host} onChange={set("imap_host")} placeholder="imap.gmail.com" /></Field>
        <Field label="IMAP port"><input className="input" type="number" value={value.imap_port} onChange={set("imap_port")} /></Field>
      </div>
      <div className="row" style={{ marginBottom: 14 }}><Switch checked={value.imap_use_ssl} onChange={(v) => onChange({ ...value, imap_use_ssl: v })} /><span className="page-sub">Use SSL</span></div>
      <div className="row" style={{ marginBottom: 10 }}><Switch checked={value.scan_spam} onChange={(v) => onChange({ ...value, scan_spam: v })} /><span className="page-sub">Also scan Spam / Junk — catch client mail the provider misfiled</span></div>
      <Field label="Extra folders to scan (optional)">
        <input className="input" value={value.extra_folders || ""} onChange={set("extra_folders")}
          placeholder="Promotions, Archive" />
      </Field>
      <div className="hint-inline" style={{ marginBottom: 14 }}>
        The inbox is always scanned. The Spam folder is found automatically, whatever your provider
        calls it. Comma-separate any extras, using the exact folder names your provider shows.
      </div>

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

      <h4 style={{ margin: "10px 0 12px", color: "var(--text-muted)" }}>Timing for this account</h4>
      <div className="field-row">
        <Field label="Poll every (seconds)">
          <input className="input" type="number" min="10" placeholder="workspace default"
            value={value.poll_interval_seconds ?? ""} onChange={setNum("poll_interval_seconds")} />
        </Field>
        <Field label="Reply delay (minutes)">
          <input className="input" type="number" min="0" placeholder="workspace default"
            value={value.reply_delay_minutes ?? ""} onChange={setNum("reply_delay_minutes")} />
        </Field>
      </div>
      <div className="hint-inline" style={{ marginBottom: 14 }}>
        Leave either blank to follow the workspace defaults on the Configuration page.
        Polling faster than 30s on Gmail or Outlook risks rate-limiting.
      </div>

      <div className="row"><Switch checked={value.is_active} onChange={(v) => onChange({ ...value, is_active: v })} /><span className="page-sub">Active — include in polling</span></div>
    </div>
  );
}
