import { useEffect, useState } from "react";
import { api } from "../api";
import { Icon } from "../icons";
import { Field, Loader, Modal, PageIntro, Switch, useToast } from "../components/ui";

// What each provider needs from the user. `fields` drives which inputs the modal
// shows, so adding a provider server-side needs one row here and nothing else.
const KINDS = {
  mailbox: {
    label: "Workspace mailbox",
    hint: "Sends through an account you already connected for auto-reply. Free, already warm, but capped low by the provider (Gmail cuts off around 500/day).",
    fields: ["mailbox", "use_proxy"],
  },
  smtp: {
    label: "External SMTP relay",
    hint: "Any provider's SMTP endpoint. Works with every service on this list — use it when you have SMTP credentials rather than an API key.",
    fields: ["from", "smtp", "auth"],
  },
  ses: {
    label: "Amazon SES",
    hint: "Cheapest at volume (~$0.10 per 1,000). Enter your SES SMTP credentials — not your AWS access key — and the region. Verify your domain and request production access first.",
    fields: ["from", "region", "auth"],
  },
  sendgrid: {
    label: "SendGrid",
    hint: "Paste an API key with Mail Send permission. No SMTP settings needed.",
    fields: ["from", "apikey"],
  },
  mailgun: {
    label: "Mailgun",
    hint: "Needs your sending domain and a private API key.",
    fields: ["from", "domain", "apikey"],
  },
  postmark: {
    label: "Postmark",
    hint: "Uses a Server API token. Campaigns are sent on the broadcast stream, which is what Postmark requires for bulk mail.",
    fields: ["from", "apikey"],
  },
};

const BLANK = {
  name: "", kind: "mailbox", mailbox: null,
  from_email: "", from_name: "", reply_to: "",
  smtp_host: "", smtp_port: 587, smtp_use_tls: true, username: "", secret: "",
  region: "", domain: "",
  daily_limit: 0, hourly_limit: 0, weight: 1,
  is_overflow: false, use_for_replies: false, reply_identity: "route",
  authorized_domains: "", use_proxy: false, is_active: true,
};

export default function Senders() {
  const [rows, setRows] = useState(null);
  const [mailboxes, setMailboxes] = useState([]);
  const [capacity, setCapacity] = useState(null);
  const [editing, setEditing] = useState(null);
  const [busy, setBusy] = useState(false);
  const toast = useToast();

  const load = () => {
    api.senders.list().then(setRows);
    api.senders.capacity().then(setCapacity);
  };
  useEffect(() => {
    load();
    api.mailboxes.list().then(setMailboxes);
  }, []);

  const save = async () => {
    setBusy(true);
    try {
      const body = { ...editing };
      if (!body.secret) delete body.secret; // blank means "keep the stored credential"
      if (body.kind !== "mailbox") body.mailbox = null;
      if (editing.id) await api.senders.update(editing.id, body);
      else await api.senders.create(body);
      toast("Route saved");
      setEditing(null);
      load();
    } catch (e) {
      toast(`Save failed: ${JSON.stringify(e.detail)}`, "err");
    } finally { setBusy(false); }
  };

  const remove = async (row) => {
    if (!confirm(`Delete sending route "${row.name}"?`)) return;
    await api.senders.remove(row.id);
    toast("Deleted");
    load();
  };

  const test = async (row) => {
    const to = prompt("Send a test email to which address?", row.sender_email || "");
    if (!to) return;
    toast("Sending test…");
    const r = await api.senders.test(row.id, to);
    toast(r.ok ? r.detail : `Test failed: ${r.error}`, r.ok ? "ok" : "err");
    load();
  };

  if (!rows) return <Loader />;

  const shows = (key) => KINDS[editing?.kind]?.fields.includes(key);

  return (
    <div className="grid">
      <PageIntro
        id="senders"
        lead="The ways this app can send email for you. That is either one of your own email accounts, or an outside sending service such as Amazon SES or Mailgun. Adding more than one matters because every email account has a daily limit — when one runs out, the app automatically continues with another instead of stopping."
      steps={[
        "Your own email accounts are added under Sending \u2192 Mailboxes, then picked here.",
        "An outside service is worth adding if you send to more than a few hundred people.",
        "Mark a service as \u201coverflow\u201d and it is only used once your own accounts hit their daily limit.",
      ]}
      />
      <div className="section-head">
        <div className="spacer" />
        <button className="btn btn-primary" onClick={() => setEditing({ ...BLANK })}>
          <Icon.plus /> New route
        </button>
      </div>

      {capacity && (
        <div className="card" style={{ padding: 16 }}>
          <div className="row" style={{ gap: 28, flexWrap: "wrap" }}>
            <div>
              <div className="page-sub">Remaining today</div>
              <div style={{ fontSize: 22, fontWeight: 600 }}>
                {capacity.unlimited ? `${capacity.remaining_today.toLocaleString()}+` : capacity.remaining_today.toLocaleString()}
              </div>
            </div>
            <div>
              <div className="page-sub">Active routes</div>
              <div style={{ fontSize: 22, fontWeight: 600 }}>{capacity.routes}</div>
            </div>
            {capacity.unlimited && (
              <div className="hint-inline" style={{ alignSelf: "center", maxWidth: 420 }}>
                One or more routes have no daily cap, so the real ceiling is your provider's plan limit.
              </div>
            )}
          </div>
        </div>
      )}

      <div className="card">
        <table className="table">
          <thead>
            <tr>
              <th>Route</th><th>Type</th><th>Sends as</th><th>Today</th>
              <th>Weight</th><th>Role</th><th>Status</th><th></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((s) => (
              <tr key={s.id}>
                <td className="subj">
                  {s.name}
                  {s.last_error && <div className="muted" style={{ color: "var(--danger)" }}>{s.last_error.slice(0, 90)}</div>}
                </td>
                <td className="muted">{s.kind_display}</td>
                <td className="mono muted">{s.sender_email || "—"}</td>
                <td className="mono">
                  {s.sent_today}
                  {s.remaining_today !== null && <span className="muted"> / {s.sent_today + s.remaining_today}</span>}
                </td>
                <td className="mono">{s.weight}×</td>
                <td>
                  <span className={`badge ${s.is_overflow ? "badge-neutral" : "badge-sent"}`}>
                    {s.is_overflow ? "overflow" : "primary"}
                  </span>
                  {s.use_for_replies && <div className="muted" style={{ fontSize: 11 }}>+ auto-replies</div>}
                </td>
                <td>
                  <span className={`badge ${s.is_active ? "badge-sent" : "badge-neutral"}`}>
                    {s.is_active ? "active" : "off"}
                  </span>
                </td>
                <td>
                  <div className="row" style={{ justifyContent: "flex-end", gap: 6 }}>
                    <button className="btn btn-sm btn-ghost" onClick={() => test(s)} title="Send a test email">
                      <Icon.play />
                    </button>
                    <button className="btn btn-sm btn-ghost" onClick={() => setEditing({ ...s, secret: "" })}>
                      <Icon.edit />
                    </button>
                    <button className="btn btn-sm btn-danger" onClick={() => remove(s)}><Icon.trash /></button>
                  </div>
                </td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr><td colSpan={8}>
                <div className="empty">
                  No sending routes yet. Add one mailbox to start, then an external provider
                  for volume — campaigns can use both at once.
                </div>
              </td></tr>
            )}
          </tbody>
        </table>
      </div>

      {editing && (
        <Modal
          wide
          title={editing.id ? "Edit sending route" : "New sending route"}
          onClose={() => setEditing(null)}
          footer={<>
            <button className="btn" onClick={() => setEditing(null)}>Cancel</button>
            <button className="btn btn-primary" onClick={save} disabled={busy}>
              {busy ? "Saving…" : "Save"}
            </button>
          </>}
        >
          <div className="field-row">
            <Field label="Route name">
              <input className="input" value={editing.name} placeholder="SES bulk"
                onChange={(e) => setEditing({ ...editing, name: e.target.value })} />
            </Field>
            <Field label="Type">
              <select className="input" value={editing.kind}
                onChange={(e) => setEditing({ ...editing, kind: e.target.value })}>
                {Object.entries(KINDS).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
              </select>
            </Field>
          </div>
          <div className="hint-inline">{KINDS[editing.kind]?.hint}</div>

          {shows("mailbox") && (
            <Field label="Mailbox">
              <select className="input" value={editing.mailbox || ""}
                onChange={(e) => setEditing({ ...editing, mailbox: e.target.value ? Number(e.target.value) : null })}>
                <option value="">Select a mailbox…</option>
                {mailboxes.map((m) => <option key={m.id} value={m.id}>{m.name} — {m.email_address}</option>)}
              </select>
            </Field>
          )}

          {shows("from") && (
            <div className="field-row">
              <Field label="From address">
                <input className="input" value={editing.from_email} placeholder="news@your-domain.com"
                  onChange={(e) => setEditing({ ...editing, from_email: e.target.value })} />
              </Field>
              <Field label="From name">
                <input className="input" value={editing.from_name} placeholder="Your Company"
                  onChange={(e) => setEditing({ ...editing, from_name: e.target.value })} />
              </Field>
            </div>
          )}

          {editing.kind !== "mailbox" && (
            <Field label="Reply-To">
              <input className="input" value={editing.reply_to} placeholder="hello@your-domain.com"
                onChange={(e) => setEditing({ ...editing, reply_to: e.target.value })} />
              <div className="hint-inline">
                Point this at a mailbox the engine polls and replies to your campaign flow straight
                back into the auto-reply rules.
              </div>
            </Field>
          )}

          {shows("region") && (
            <Field label="SES region">
              <input className="input" value={editing.region} placeholder="eu-west-1"
                onChange={(e) => setEditing({ ...editing, region: e.target.value })} />
            </Field>
          )}

          {shows("domain") && (
            <Field label="Mailgun sending domain">
              <input className="input" value={editing.domain} placeholder="mg.your-domain.com"
                onChange={(e) => setEditing({ ...editing, domain: e.target.value })} />
            </Field>
          )}

          {shows("smtp") && (
            <div className="field-row">
              <Field label="SMTP host">
                <input className="input" value={editing.smtp_host} placeholder="smtp.provider.com"
                  onChange={(e) => setEditing({ ...editing, smtp_host: e.target.value })} />
              </Field>
              <Field label="Port">
                <input className="input" type="number" value={editing.smtp_port}
                  onChange={(e) => setEditing({ ...editing, smtp_port: Number(e.target.value) })} />
              </Field>
            </div>
          )}

          {(shows("auth") || shows("smtp")) && (
            <div className="field-row">
              <Field label="Username">
                <input className="input" value={editing.username}
                  onChange={(e) => setEditing({ ...editing, username: e.target.value })} />
              </Field>
              <Field label={editing.has_secret ? "Password (leave blank to keep)" : "Password"}>
                <input className="input" type="password" value={editing.secret}
                  onChange={(e) => setEditing({ ...editing, secret: e.target.value })} />
              </Field>
            </div>
          )}

          {shows("apikey") && (
            <Field label={editing.has_secret ? "API key (leave blank to keep)" : "API key"}>
              <input className="input" type="password" value={editing.secret} placeholder="SG.xxxx / key-xxxx"
                onChange={(e) => setEditing({ ...editing, secret: e.target.value })} />
            </Field>
          )}

          <div className="page-sub" style={{ margin: "16px 0 6px" }}>Pacing</div>
          <div className="field-row">
            <Field label="Daily limit (0 = unlimited)">
              <input className="input" type="number" min="0" value={editing.daily_limit}
                onChange={(e) => setEditing({ ...editing, daily_limit: Number(e.target.value) })} />
            </Field>
            <Field label="Hourly limit (0 = unlimited)">
              <input className="input" type="number" min="0" value={editing.hourly_limit}
                onChange={(e) => setEditing({ ...editing, hourly_limit: Number(e.target.value) })} />
            </Field>
            <Field label="Weight">
              <input className="input" type="number" min="1" value={editing.weight}
                onChange={(e) => setEditing({ ...editing, weight: Number(e.target.value) })} />
            </Field>
          </div>
          <div className="hint-inline">
            Weight sets the share of sends this route takes: a weight-5 provider absorbs five
            emails for every one a weight-1 mailbox sends.
          </div>

          <div className="row" style={{ marginTop: 16, gap: 24, flexWrap: "wrap" }}>
            <label className="row" style={{ gap: 8 }}>
              <Switch checked={editing.is_overflow}
                onChange={(v) => setEditing({ ...editing, is_overflow: v })} />
              <span className="page-sub">Overflow only</span>
            </label>
            {editing.kind !== "mailbox" && (
              <label className="row" style={{ gap: 8 }}>
                <Switch checked={editing.use_proxy}
                  onChange={(v) => setEditing({ ...editing, use_proxy: v })} />
                <span className="page-sub">Route through proxies</span>
              </label>
            )}
            {editing.kind !== "mailbox" && (
              <label className="row" style={{ gap: 8 }}>
                <Switch checked={editing.use_for_replies}
                  onChange={(v) => setEditing({ ...editing, use_for_replies: v })} />
                <span className="page-sub">Use for auto-replies too</span>
              </label>
            )}
            <label className="row" style={{ gap: 8 }}>
              <Switch checked={editing.is_active}
                onChange={(v) => setEditing({ ...editing, is_active: v })} />
              <span className="page-sub">Active</span>
            </label>
          </div>
          <div className="hint-inline">
            An overflow route sits idle until every primary route has hit its cap — the way to say
            "use the mailboxes first, then fall back to the provider".
          </div>
          {editing.kind !== "mailbox" && editing.use_for_replies && (
            <>
              <div className="field-row" style={{ marginTop: 12 }}>
                <Field label="Send borrowed replies as">
                  <select className="input" value={editing.reply_identity}
                    onChange={(e) => setEditing({ ...editing, reply_identity: e.target.value })}>
                    <option value="route">This route's address, Reply-To the mailbox (safe)</option>
                    <option value="mailbox">The mailbox's own address (needs a verified domain)</option>
                  </select>
                </Field>
                <Field label="Authorised domains">
                  <input className="input" value={editing.authorized_domains}
                    placeholder={editing.from_email ? editing.from_email.split("@")[1] : "your-domain.com"}
                    disabled={editing.reply_identity === "route"}
                    onChange={(e) => setEditing({ ...editing, authorized_domains: e.target.value })} />
                </Field>
              </div>
              <div className="hint-inline">
                {editing.reply_identity === "mailbox" ? (
                  <>Replies keep the mailbox's From address, so this provider must be verified
                  for that domain — SPF and DKIM must cover it. Blank authorised domains means
                  the From address's own domain. A mailbox on free Gmail or Outlook can never
                  be covered this way; switch to the other option for those.</>
                ) : (
                  <>Replies go out as <b>{editing.from_email || "this route's address"}</b> with the
                  mailbox in Reply-To, so they always authenticate — this is how a free Gmail or
                  Outlook mailbox keeps replying after it hits its daily cap. The trade-off is that
                  the recipient sees a different sender address than the one they wrote to.</>
                )}
              </div>
            </>
          )}
        </Modal>
      )}
    </div>
  );
}
