import { useEffect, useState } from "react";
import { api } from "../api";
import { Icon } from "../icons";
import { Field, Loader, Modal, PageIntro, Switch, useToast } from "../components/ui";

// What each provider needs from the user. `fields` drives which inputs the modal
// shows, so adding a provider server-side needs one row here and nothing else.
const KINDS = {
  mailbox: {
    label: "Workspace mailbox",
    hint: "Uses one of your own email accounts — the ones under Sending → Mailboxes. Free, and already trusted because you send from it every day. The catch is the daily limit: Gmail stops you at around 500 emails a day.",
    fields: ["mailbox", "use_proxy"],
  },
  smtp: {
    label: "External SMTP relay",
    hint: "For any provider not listed here. Use this when they gave you a server address, a username and a password rather than an API key. Their help pages will list the details.",
    fields: ["from", "smtp", "auth"],
  },
  ses: {
    label: "Amazon SES",
    hint: "Amazon's email service — by far the cheapest for large volumes, around 10 cents per thousand emails. Set-up takes longer: you must prove you own your domain and ask Amazon to lift the starter limit. Use the SES SMTP username and password, not your main AWS key.",
    fields: ["from", "region", "auth"],
  },
  sendgrid: {
    label: "SendGrid",
    hint: "Create an API key in SendGrid with permission to send mail, then paste it below. Nothing else to fill in.",
    fields: ["from", "apikey"],
  },
  mailgun: {
    label: "Mailgun",
    hint: "Paste your private API key from Mailgun, and the domain you set up with them.",
    fields: ["from", "domain", "apikey"],
  },
  postmark: {
    label: "Postmark",
    hint: "Paste a Server API token from Postmark. Campaigns are sent on their broadcast stream, which is what Postmark requires for bulk email.",
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
    if (!confirm(`Delete "${row.name}"? Campaigns using it will stop sending through it.`)) return;
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
        lead="Every email you send leaves through one of the accounts or services listed here. That is either one of your own email accounts, or an outside sending service such as Amazon SES. Adding more than one matters because every email account has a daily limit — when one runs out, the app carries on with another instead of stopping."
      steps={[
        "Your own email accounts are added under Sending \u2192 Mailboxes, then chosen here.",
        "An outside service is worth adding if you send to more than a few hundred people.",
        "Tick \u201conly use when the others are full\u201d on a paid service and it stays unused until your own accounts run out for the day.",
      ]}
      />
      <div className="section-head">
        <div className="spacer" />
        <button className="btn btn-primary" onClick={() => setEditing({ ...BLANK })}>
          <Icon.plus /> Add a way to send
        </button>
      </div>

      {capacity && (
        <div className="card" style={{ padding: 16 }}>
          <div className="row" style={{ gap: 28, flexWrap: "wrap" }}>
            <div>
              <div className="page-sub">Emails you can still send today</div>
              <div style={{ fontSize: 22, fontWeight: 600 }}>
                {capacity.unlimited ? `${capacity.remaining_today.toLocaleString()}+` : capacity.remaining_today.toLocaleString()}
              </div>
            </div>
            <div>
              <div className="page-sub">Ways to send set up</div>
              <div style={{ fontSize: 22, fontWeight: 600 }}>{capacity.routes}</div>
            </div>
            {capacity.unlimited && (
              <div className="hint-inline" style={{ alignSelf: "center", maxWidth: 420 }}>
                One of these has no daily limit set, so the real ceiling is whatever your provider allows.
              </div>
            )}
          </div>
        </div>
      )}

      <div className="card">
        <table className="table">
          <thead>
            <tr>
              <th>Name</th><th>Service</th><th>Sends from</th><th>Sent today</th>
              <th>Share</th><th>When it's used</th><th>On?</th><th></th>
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
                  {s.remaining_today !== null
                    ? <span className="muted"> of {s.sent_today + s.remaining_today}</span>
                    : <span className="muted"> (no limit)</span>}
                </td>
                <td className="mono">{s.weight === 1 ? "normal" : `${s.weight}× more`}</td>
                <td>
                  <span className={`badge ${s.is_overflow ? "badge-neutral" : "badge-sent"}`}>
                    {s.is_overflow ? "only when others are full" : "used first"}
                  </span>
                  {s.use_for_replies && <div className="muted" style={{ fontSize: 11 }}>also sends auto-replies</div>}
                </td>
                <td>
                  <span className={`badge ${s.is_active ? "badge-sent" : "badge-neutral"}`}>
                    {s.is_active ? "in use" : "paused"}
                  </span>
                </td>
                <td>
                  <div className="row" style={{ justifyContent: "flex-end", gap: 6 }}>
                    <button className="btn btn-sm btn-ghost" onClick={() => test(s)} title="Send a test email to check this works">
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
                  Nothing set up yet. Start by adding one of your own mailboxes; add an outside
                  service like Amazon SES later if you need to send to more people than your
                  own account allows in a day.
                </div>
              </td></tr>
            )}
          </tbody>
        </table>
      </div>

      {editing && (
        <Modal
          wide
          title={editing.id ? "Edit a way to send" : "Add a way to send"}
          onClose={() => setEditing(null)}
          footer={<>
            <button className="btn" onClick={() => setEditing(null)}>Cancel</button>
            <button className="btn btn-primary" onClick={save} disabled={busy}>
              {busy ? "Saving…" : "Save"}
            </button>
          </>}
        >
          <div className="field-row">
            <Field label="Name this (anything you like)">
              <input className="input" value={editing.name} placeholder="Amazon SES for newsletters"
                onChange={(e) => setEditing({ ...editing, name: e.target.value })} />
            </Field>
            <Field label="What are you sending through?">
              <select className="input" value={editing.kind}
                onChange={(e) => setEditing({ ...editing, kind: e.target.value })}>
                {Object.entries(KINDS).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
              </select>
            </Field>
          </div>
          <div className="hint-inline">{KINDS[editing.kind]?.hint}</div>

          {shows("mailbox") && (
            <Field label="Which of your accounts?">
              <select className="input" value={editing.mailbox || ""}
                onChange={(e) => setEditing({ ...editing, mailbox: e.target.value ? Number(e.target.value) : null })}>
                <option value="">Select a mailbox…</option>
                {mailboxes.map((m) => <option key={m.id} value={m.id}>{m.name} — {m.email_address}</option>)}
              </select>
            </Field>
          )}

          {shows("from") && (
            <div className="field-row">
              <Field label="Address emails are sent from">
                <input className="input" value={editing.from_email} placeholder="news@your-domain.com"
                  onChange={(e) => setEditing({ ...editing, from_email: e.target.value })} />
              </Field>
              <Field label="Name people will see">
                <input className="input" value={editing.from_name} placeholder="Your Company"
                  onChange={(e) => setEditing({ ...editing, from_name: e.target.value })} />
              </Field>
            </div>
          )}

          {editing.kind !== "mailbox" && (
            <Field label="Where replies should go">
              <input className="input" value={editing.reply_to} placeholder="hello@your-domain.com"
                onChange={(e) => setEditing({ ...editing, reply_to: e.target.value })} />
              <div className="hint-inline">
                When someone replies to your campaign, their reply goes to this address. Use one of
                your own mailboxes and those replies will be answered automatically like any other.
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

          <div className="page-sub" style={{ margin: "16px 0 6px" }}>How fast should this send?</div>
          <div className="field-row">
            <Field label="Most emails per day (0 = no limit)">
              <input className="input" type="number" min="0" value={editing.daily_limit}
                onChange={(e) => setEditing({ ...editing, daily_limit: Number(e.target.value) })} />
            </Field>
            <Field label="Most emails per hour (0 = no limit)">
              <input className="input" type="number" min="0" value={editing.hourly_limit}
                onChange={(e) => setEditing({ ...editing, hourly_limit: Number(e.target.value) })} />
            </Field>
            <Field label="Share of sending">
              <input className="input" type="number" min="1" value={editing.weight}
                onChange={(e) => setEditing({ ...editing, weight: Number(e.target.value) })} />
            </Field>
          </div>
          <div className="hint-inline">
            Leave the share at 1 unless you want one of them doing more of the work. Set it to 5
            and that one sends five emails for every one the others send. Daily and hourly limits
            protect an account from being cut off for sending too much — check what your provider
            allows and stay under it.
          </div>

          <div className="row" style={{ marginTop: 16, gap: 24, flexWrap: "wrap" }}>
            <label className="row" style={{ gap: 8 }}>
              <Switch checked={editing.is_overflow}
                onChange={(v) => setEditing({ ...editing, is_overflow: v })} />
              <span className="page-sub">Only use this when the others are full</span>
            </label>
            {editing.kind !== "mailbox" && (
              <label className="row" style={{ gap: 8 }}>
                <Switch checked={editing.use_proxy}
                  onChange={(v) => setEditing({ ...editing, use_proxy: v })} />
                <span className="page-sub">Send through proxies (advanced)</span>
              </label>
            )}
            {editing.kind !== "mailbox" && (
              <label className="row" style={{ gap: 8 }}>
                <Switch checked={editing.use_for_replies}
                  onChange={(v) => setEditing({ ...editing, use_for_replies: v })} />
                <span className="page-sub">Also use this for automatic replies</span>
              </label>
            )}
            <label className="row" style={{ gap: 8 }}>
              <Switch checked={editing.is_active}
                onChange={(v) => setEditing({ ...editing, is_active: v })} />
              <span className="page-sub">Ready to use</span>
            </label>
          </div>
          <div className="hint-inline">
            Turn this on and the app leaves it alone until everything else has hit its daily limit.
            That is how you say “send from my own account first, and only use the paid service once
            it runs out”.
          </div>
          {editing.kind !== "mailbox" && editing.use_for_replies && (
            <>
              <div className="field-row" style={{ marginTop: 12 }}>
                <Field label="Who should replies appear to come from?">
                  <select className="input" value={editing.reply_identity}
                    onChange={(e) => setEditing({ ...editing, reply_identity: e.target.value })}>
                    <option value="route">This route's address, Reply-To the mailbox (safe)</option>
                    <option value="mailbox">The mailbox's own address (needs a verified domain)</option>
                  </select>
                </Field>
                <Field label="Domains this service may send for">
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
