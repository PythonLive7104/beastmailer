import { useEffect, useState } from "react";
import { api } from "../api";
import { Icon } from "../icons";
import { Field, Loader, Modal, Switch, useToast } from "../components/ui";

// Campaign-only tags. Everything the auto-reply palette offers still works here —
// these are the ones that mean something to a bulk send.
const TAGS = [
  ["first_name", "The contact's first name, or 'there' when the import had none."],
  ["last_name", "The contact's surname."],
  ["full_name", "First and last together, falling back to the address."],
  ["email", "The contact's email address."],
  ["company", "The company from the import."],
  ["campaign_name", "This campaign's name."],
  ["unsubscribe_link", "A ready-made <a> unsubscribe link. Put this in your footer."],
  ["unsubscribe_url", "The bare unsubscribe URL, for styling the link yourself."],
  ["date", "Today's date, written out in full."],
  ["ran_hex_8", "8 random characters, different in every email."],
];

const BLANK = {
  name: "", subject: "", is_html: true, preheader: "",
  body: '<p>Hi {{first_name}},</p>\n<p></p>\n<p style="font-size:12px;color:#888">{{unsubscribe_link}}</p>',
  lists: [], senders: [], per_tick_limit: 25, track_opens: true, track_clicks: true,
  scheduled_for: null,
};

const STATUS_BADGE = {
  draft: "badge-neutral", scheduled: "badge-scheduled", sending: "badge-scheduled",
  paused: "badge-neutral", sent: "badge-sent", failed: "badge-failed",
};

function Stat({ label, value, of, tone }) {
  const pct = of > 0 ? Math.round((value / of) * 1000) / 10 : null;
  return (
    <div style={{ minWidth: 92 }}>
      <div className="page-sub">{label}</div>
      <div style={{ fontSize: 21, fontWeight: 600, color: tone }}>{value.toLocaleString()}</div>
      {pct !== null && <div className="muted" style={{ fontSize: 11 }}>{pct}%</div>}
    </div>
  );
}

export default function Campaigns() {
  const [rows, setRows] = useState(null);
  const [lists, setLists] = useState([]);
  const [senders, setSenders] = useState([]);
  const [editing, setEditing] = useState(null);
  const [report, setReport] = useState(null);
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(false);
  const toast = useToast();

  const load = () => api.campaigns.list().then(setRows);
  useEffect(() => {
    load();
    api.contactLists.list().then(setLists);
    api.senders.list().then(setSenders);
  }, []);

  // A sending campaign changes under us as the engine ticks, so poll while any is live.
  useEffect(() => {
    if (!rows?.some((c) => c.status === "sending")) return;
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, [rows]);

  const save = async () => {
    setBusy(true);
    try {
      const body = { ...editing, scheduled_for: editing.scheduled_for || null };
      if (editing.id) await api.campaigns.update(editing.id, body);
      else await api.campaigns.create(body);
      toast("Campaign saved");
      setEditing(null);
      load();
    } catch (e) { toast(`Save failed: ${JSON.stringify(e.detail)}`, "err"); }
    finally { setBusy(false); }
  };

  const act = async (fn, row, okMessage) => {
    try {
      const r = await fn(row.id);
      toast(okMessage || `Campaign ${r.status}`);
      load();
      if (report?.id === row.id) openReport({ ...row, ...r });
    } catch (e) { toast(e.detail?.detail || "Action failed", "err"); }
  };

  const start = async (row) => {
    if (!confirm(`Start "${row.name}"? This sends to ${row.audience_size} contact(s).`)) return;
    act(api.campaigns.start, row, "Campaign queued");
  };

  const remove = async (row) => {
    if (!confirm(`Delete campaign "${row.name}"? Its report goes too.`)) return;
    await api.campaigns.remove(row.id);
    toast("Deleted");
    load();
  };

  const testSend = async (row) => {
    const to = prompt("Send a test copy to which address?");
    if (!to) return;
    try {
      const r = await api.campaigns.testSend(row.id, to);
      toast(r.detail);
    } catch (e) { toast(e.detail?.error || e.detail?.detail || "Test failed", "err"); }
  };

  const openPreview = async (row) => {
    const r = await api.campaigns.preview(row.id);
    setPreview({ ...r, name: row.name });
  };

  const openReport = async (row) => {
    const recipients = await api.campaigns.recipients(row.id);
    setReport({ ...row, recipients });
  };

  const toggleIn = (key, id) => setEditing((c) => ({
    ...c,
    [key]: c[key].includes(id) ? c[key].filter((x) => x !== id) : [...c[key], id],
  }));

  const insertTag = (tag) => setEditing((c) => ({ ...c, body: `${c.body}{{${tag}}}` }));

  if (!rows) return <Loader />;

  const activeSenders = senders.filter((s) => s.is_active);

  return (
    <div className="grid">
      <div className="section-head">
        <span className="page-sub">
          Bulk sends to your contact lists, paced across your sending routes.
        </span>
        <button className="btn btn-primary" onClick={() => setEditing({ ...BLANK })}>
          <Icon.plus /> New campaign
        </button>
      </div>

      {activeSenders.length === 0 && (
        <div className="card" style={{ padding: 16 }}>
          <div className="hint-inline">
            No active sending routes yet — a campaign has nothing to send through.
            Add one on the <b>Sending routes</b> page first.
          </div>
        </div>
      )}

      <div className="card">
        <table className="table">
          <thead>
            <tr><th>Campaign</th><th>Audience</th><th>Progress</th><th>Opens</th><th>Clicks</th><th>Status</th><th></th></tr>
          </thead>
          <tbody>
            {rows.map((c) => {
              const s = c.stats;
              const done = s.total - s.pending;
              return (
                <tr key={c.id}>
                  <td className="subj">
                    {c.name}
                    <div className="muted">{c.subject}</div>
                  </td>
                  <td className="mono">{c.audience_size}</td>
                  <td className="mono">
                    {s.total > 0 ? `${done} / ${s.total}` : <span className="muted">—</span>}
                    {s.failed > 0 && <div className="muted" style={{ color: "var(--danger)" }}>{s.failed} failed</div>}
                  </td>
                  <td className="mono">{s.opened || <span className="muted">—</span>}</td>
                  <td className="mono">{s.clicked || <span className="muted">—</span>}</td>
                  <td><span className={`badge ${STATUS_BADGE[c.status]}`}>{c.status}</span></td>
                  <td>
                    <div className="row" style={{ justifyContent: "flex-end", gap: 6 }}>
                      {(c.status === "draft" || c.status === "failed") && (
                        <button className="btn btn-sm btn-primary" onClick={() => start(c)} title="Start sending">
                          <Icon.play /> Send
                        </button>
                      )}
                      {(c.status === "sending" || c.status === "scheduled") && (
                        <button className="btn btn-sm" onClick={() => act(api.campaigns.pause, c)}>Pause</button>
                      )}
                      {c.status === "paused" && (
                        <button className="btn btn-sm btn-primary" onClick={() => act(api.campaigns.resume, c)}>Resume</button>
                      )}
                      {c.status === "sending" && (
                        <button className="btn btn-sm" onClick={() => act(api.campaigns.sendNow, c, "Batch sent")} title="Send a batch now">
                          Send batch
                        </button>
                      )}
                      <button className="btn btn-sm btn-ghost" onClick={() => openReport(c)} title="Report">
                        <Icon.book />
                      </button>
                      <button className="btn btn-sm btn-ghost" onClick={() => openPreview(c)} title="Preview">
                        <Icon.sparkle />
                      </button>
                      <button className="btn btn-sm btn-ghost" onClick={() => testSend(c)} title="Send a test">
                        <Icon.reply />
                      </button>
                      <button className="btn btn-sm btn-ghost" onClick={() => setEditing({ ...c })}><Icon.edit /></button>
                      <button className="btn btn-sm btn-danger" onClick={() => remove(c)}><Icon.trash /></button>
                    </div>
                  </td>
                </tr>
              );
            })}
            {rows.length === 0 && (
              <tr><td colSpan={7}><div className="empty">No campaigns yet.</div></td></tr>
            )}
          </tbody>
        </table>
      </div>

      {editing && (
        <Modal wide title={editing.id ? "Edit campaign" : "New campaign"} onClose={() => setEditing(null)}
          footer={<>
            <button className="btn" onClick={() => setEditing(null)}>Cancel</button>
            <button className="btn btn-primary" onClick={save} disabled={busy}>{busy ? "Saving…" : "Save"}</button>
          </>}>
          <div className="field-row">
            <Field label="Campaign name">
              <input className="input" value={editing.name} placeholder="August newsletter"
                onChange={(e) => setEditing({ ...editing, name: e.target.value })} />
            </Field>
            <Field label="Subject">
              <input className="input" value={editing.subject} placeholder="{{first_name}}, your August update"
                onChange={(e) => setEditing({ ...editing, subject: e.target.value })} />
            </Field>
          </div>

          <Field label="Preview text">
            <input className="input" value={editing.preheader}
              placeholder="Shown after the subject line in most inboxes"
              onChange={(e) => setEditing({ ...editing, preheader: e.target.value })} />
          </Field>

          <div className="row" style={{ justifyContent: "space-between", alignItems: "center", margin: "14px 0 6px" }}>
            <span className="page-sub">Body</span>
            <label className="row" style={{ gap: 8 }}>
              <Switch checked={editing.is_html} onChange={(v) => setEditing({ ...editing, is_html: v })} />
              <span className="page-sub">HTML</span>
            </label>
          </div>
          <textarea className={`textarea ${editing.is_html ? "mono" : ""}`}
            style={{ minHeight: 240, width: "100%" }} value={editing.body}
            onChange={(e) => setEditing({ ...editing, body: e.target.value })} />

          <div className="page-sub" style={{ margin: "12px 0 6px" }}>Insert a tag:</div>
          <div className="row" style={{ flexWrap: "wrap", gap: 6 }}>
            {TAGS.map(([tag, hint]) => (
              <span className="chip" key={tag} data-tip={hint} role="button" tabIndex={0}
                onClick={() => insertTag(tag)}
                onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); insertTag(tag); } }}
              >{`{{${tag}}}`}</span>
            ))}
          </div>
          <div className="hint-inline">
            Every tag from the auto-reply palette works here too. An unsubscribe link is required
            by Gmail and Yahoo for bulk mail — one is added to the headers automatically, but keep
            a visible one in the footer.
          </div>

          <div className="page-sub" style={{ margin: "16px 0 6px" }}>Send to:</div>
          <div className="row" style={{ flexWrap: "wrap", gap: 6 }}>
            {lists.map((l) => (
              <span key={l.id} role="button" tabIndex={0}
                className={`chip ${editing.lists.includes(l.id) ? "chip-on" : ""}`}
                onClick={() => toggleIn("lists", l.id)}
                onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggleIn("lists", l.id); } }}
              >{l.name} · {l.mailable_count}</span>
            ))}
            {lists.length === 0 && <span className="muted">No lists yet — create one on the Audience page.</span>}
          </div>

          <div className="page-sub" style={{ margin: "16px 0 6px" }}>Send through:</div>
          <div className="row" style={{ flexWrap: "wrap", gap: 6 }}>
            {activeSenders.map((s) => (
              <span key={s.id} role="button" tabIndex={0}
                className={`chip ${editing.senders.includes(s.id) ? "chip-on" : ""}`}
                onClick={() => toggleIn("senders", s.id)}
                onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggleIn("senders", s.id); } }}
              >{s.name}{s.is_overflow ? " (overflow)" : ""}</span>
            ))}
            {activeSenders.length === 0 && <span className="muted">No active routes — add one on Sending routes.</span>}
          </div>

          <div className="field-row" style={{ marginTop: 16 }}>
            <Field label="Schedule for (blank = send now)">
              <input className="input" type="datetime-local"
                value={editing.scheduled_for ? editing.scheduled_for.slice(0, 16) : ""}
                onChange={(e) => setEditing({ ...editing, scheduled_for: e.target.value || null })} />
            </Field>
            <Field label="Emails per engine tick">
              <input className="input" type="number" min="1" value={editing.per_tick_limit}
                onChange={(e) => setEditing({ ...editing, per_tick_limit: Number(e.target.value) })} />
            </Field>
          </div>
          <div className="hint-inline">
            The per-tick limit paces the whole campaign on top of each route's own caps — lower it
            for a slow drip that looks less like a blast.
          </div>

          <div className="row" style={{ marginTop: 16, gap: 24 }}>
            <label className="row" style={{ gap: 8 }}>
              <Switch checked={editing.track_opens} onChange={(v) => setEditing({ ...editing, track_opens: v })} />
              <span className="page-sub">Track opens</span>
            </label>
            <label className="row" style={{ gap: 8 }}>
              <Switch checked={editing.track_clicks} onChange={(v) => setEditing({ ...editing, track_clicks: v })} />
              <span className="page-sub">Track clicks</span>
            </label>
          </div>
          <div className="hint-inline">
            Open tracking uses a pixel that Apple Mail Privacy Protection and many corporate
            clients block, so treat the open rate as a floor. Click tracking is reliable.
          </div>
        </Modal>
      )}

      {report && (
        <Modal wide title={`Report · ${report.name}`} onClose={() => setReport(null)}
          footer={<button className="btn btn-primary" onClick={() => setReport(null)}>Close</button>}>
          <div className="row" style={{ gap: 26, flexWrap: "wrap", marginBottom: 18 }}>
            <Stat label="Audience" value={report.stats.total} of={0} />
            <Stat label="Sent" value={report.stats.sent} of={report.stats.total} />
            <Stat label="Opened" value={report.stats.opened} of={report.stats.sent} />
            <Stat label="Clicked" value={report.stats.clicked} of={report.stats.sent} />
            <Stat label="Unsubscribed" value={report.stats.unsubscribed} of={report.stats.sent} />
            <Stat label="Bounced" value={report.stats.bounced} of={report.stats.total} tone="var(--danger)" />
            <Stat label="Failed" value={report.stats.failed} of={report.stats.total} tone="var(--danger)" />
            <Stat label="Pending" value={report.stats.pending} of={report.stats.total} />
          </div>
          <table className="table">
            <thead><tr><th>Recipient</th><th>Route</th><th>Status</th><th>Opens</th><th>Clicks</th><th>Error</th></tr></thead>
            <tbody>
              {report.recipients.map((r) => (
                <tr key={r.id}>
                  <td className="mono">{r.email}<div className="muted">{r.name}</div></td>
                  <td className="muted">{r.sender_name || "—"}</td>
                  <td><span className={`badge ${r.status === "failed" || r.status === "bounced" ? "badge-failed" : r.status === "pending" ? "badge-neutral" : "badge-sent"}`}>{r.status}</span></td>
                  <td className="mono">{r.open_count}</td>
                  <td className="mono">{r.click_count}</td>
                  <td className="muted" style={{ maxWidth: 220, overflow: "hidden", textOverflow: "ellipsis" }}>{r.error || "—"}</td>
                </tr>
              ))}
              {report.recipients.length === 0 && (
                <tr><td colSpan={6}><div className="empty">Nothing sent yet.</div></td></tr>
              )}
            </tbody>
          </table>
        </Modal>
      )}

      {preview && (
        <Modal wide title={`Preview · ${preview.name}`} onClose={() => setPreview(null)}
          footer={<button className="btn btn-primary" onClick={() => setPreview(null)}>Close</button>}>
          <div className="muted" style={{ marginBottom: 4 }}>To</div>
          <div className="mono" style={{ marginBottom: 12 }}>{preview.to}</div>
          <div className="muted" style={{ marginBottom: 4 }}>Subject</div>
          <div style={{ marginBottom: 12 }}>{preview.subject}</div>
          <div className="muted" style={{ marginBottom: 4 }}>Body</div>
          {preview.is_html
            ? <iframe className="html-preview" style={{ height: 380 }} sandbox="" title="Preview" srcDoc={preview.body} />
            : <div className="card card-pad tpl-body" style={{ maxHeight: 380, overflow: "auto" }}>{preview.body}</div>}
        </Modal>
      )}
    </div>
  );
}
