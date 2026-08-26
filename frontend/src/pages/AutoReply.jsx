import { useEffect, useState } from "react";
import { api } from "../api";
import { Icon } from "../icons";
import { Field, Loader, Modal, Switch, useToast } from "../components/ui";

// Mirrors build_context() in apps/automation/engine.py. Adding a tag there means
// adding it here too, or the client never discovers it.
// The first two groups cover almost every template; the rest sit behind "More tags".
const TOKEN_GROUPS = [
  ["Sender", [
    ["sender_name", "Their full name, read from the From header. Falls back to a tidied-up address when they send no name."],
    ["sender_first_name", "Just their first name — Jane."],
    ["sender_last_name", "Just their surname — Doe. Empty if they only gave one name."],
    ["sender_email", "The address they wrote in from — jane.doe@example.com."],
    ["sender_user", "The part of their address before the @ — jane.doe."],
    ["sender_domain", "The part after the @ — example.com. Handy for naming their company."],
  ]],
  ["Their message", [
    ["original_subject", "The subject line exactly as they sent it, Re: and all."],
    ["subject_clean", "The same subject with any Re: or Fwd: stripped off."],
    ["quoted_body", "Their whole message with > in front of every line, the way a normal reply quotes."],
    ["original_body", "Their message as they wrote it, with no quote marks added."],
    ["ticket_id", "An 8-character reference for this conversation. Always the same for the same thread, so it is safe to quote back."],
    ["received_date", "The day their email landed in the mailbox."],
    ["received_time", "The time their email landed."],
    ["message_id", "The raw Message-ID header. Mostly useful for tracing a specific email."],
  ]],
  ["Your side", [
    ["mailbox_name", "The name you gave the mailbox that is doing the replying."],
    ["mailbox_email", "The address this reply is being sent from."],
    ["mailbox_domain", "Your own domain — the part of your address after the @."],
    ["workspace_name", "The name of your workspace."],
    ["rule_name", "The rule that matched this email and triggered the reply."],
    ["template_name", "The name of this template."],
  ]],
  ["Date & time", [
    ["greeting", "Good morning, Good afternoon or Good evening, chosen from the time of day."],
    ["date", "Today written out in full — Wednesday, August 26, 2026."],
    ["date_short", "Today in year-month-day order — 2026-08-26."],
    ["date_us", "Today in US order, month first — 08/26/2026."],
    ["date_eu", "Today in day-first order — 26/08/2026."],
    ["time", "The time the reply is sent, 12-hour — 8:03 PM."],
    ["time_24", "The time the reply is sent, 24-hour — 20:03."],
    ["datetime", "Today's date and the time together, in one line."],
    ["day_name", "The name of today's weekday — Wednesday."],
    ["month_name", "The name of the current month — August."],
    ["year", "The four-digit year — 2026."],
    ["timezone", "The timezone the times above are in — UTC unless you change it."],
  ]],
  ["Deadlines — change the number", [
    ["date_plus_3", "3 days from today. Change the 3 to any number of days."],
    ["date_minus_1", "1 day before today. Change the 1 to any number of days."],
    ["business_day_plus_2", "2 working days from today, skipping Saturday and Sunday. From a Friday this lands on Tuesday."],
  ]],
  ["Random — fresh on every send", [
    ["ran_letter_10", "10 random letters, different in every email you send."],
    ["ran_digit_6", "6 random digits. Change the 6 for a different length."],
    ["ran_alnum_12", "12 random letters and digits mixed together."],
    ["ran_hex_8", "8 random hex characters — 0-9 and a-f."],
    ["uuid", "A one-off unique identifier that is never repeated."],
  ]],
];
const ALWAYS_SHOWN = 2;

const BLANK = {
  name: "",
  subject: "Re: {{original_subject}}",
  body: "Hi {{sender_name}},\n\n",
  is_html: false,
  is_active: true,
};

/* Decide which way a chip's tooltip should open. The palette sits inside a scrolling
   modal, so a bubble anchored left on a chip near the right edge gets clipped. Measure
   the room left in the row on hover and flip the anchor when it won't fit. */
const TIP_WIDTH = 244;
function tipAlign(e) {
  const chip = e.currentTarget;
  const row = chip.parentElement?.getBoundingClientRect();
  if (!row) return;
  const box = chip.getBoundingClientRect();
  chip.dataset.tipAlign = row.right - box.left < TIP_WIDTH ? "end" : "start";
}

// Enough of a signal to offer the toggle, without nagging about an odd < in prose.
const LOOKS_LIKE_HTML = /<(html|body|div|table|p|br|a|span|img|h[1-6])\b[^>]*>/i;

/** Render an HTML body in a sandboxed iframe: no scripts, no access to this page. */
function HtmlPreview({ html, height }) {
  return (
    <iframe
      className="html-preview"
      style={{ height }}
      sandbox=""
      title="HTML preview"
      srcDoc={html}
    />
  );
}

export default function AutoReply() {
  const [rows, setRows] = useState(null);
  const [placeholders, setPlaceholders] = useState([]);
  const [links, setLinks] = useState([]);
  const [editing, setEditing] = useState(null);
  const [preview, setPreview] = useState(null);
  const [showAllTokens, setShowAllTokens] = useState(false);
  const [busy, setBusy] = useState(false);
  const toast = useToast();

  const load = () => api.templates.list().then(setRows);
  useEffect(() => {
    load();
    api.placeholders.list().then(setPlaceholders);
    api.links.list().then(setLinks);
  }, []);

  const save = async () => {
    setBusy(true);
    try {
      if (editing.id) await api.templates.update(editing.id, editing);
      else await api.templates.create(editing);
      toast("Template saved");
      setEditing(null);
      load();
    } catch (e) { toast(`Save failed: ${JSON.stringify(e.detail)}`, "err"); }
    finally { setBusy(false); }
  };

  const remove = async (row) => {
    if (!confirm(`Delete template "${row.name}"?`)) return;
    try { await api.templates.remove(row.id); toast("Deleted"); load(); }
    catch { toast("Delete failed — it may be used by a rule", "err"); }
  };

  const doPreview = async (row) => {
    const r = await api.templates.preview(row.id);
    setPreview({ ...r, name: row.name });
  };

  const insert = (key) => setEditing((e) => ({ ...e, body: `${e.body}{{${key}}}` }));
  const insertText = (text) => setEditing((e) => ({ ...e, body: `${e.body}${text}` }));

  if (!rows) return <Loader />;

  const htmlHint = editing && !editing.is_html && LOOKS_LIKE_HTML.test(editing.body || "");

  return (
    <div className="grid">
      <div className="section-head">
        <span className="page-sub">{rows.length} reply template{rows.length !== 1 ? "s" : ""}</span>
        <button className="btn btn-primary" onClick={() => setEditing({ ...BLANK })}><Icon.plus /> New template</button>
      </div>

      <div className="grid cols-2">
        {rows.map((t) => (
          <div className="card card-pad" key={t.id}>
            <div className="between">
              <h3 className="tpl-name">{t.name}</h3>
              <div className="row" style={{ gap: 6, flexShrink: 0 }}>
                {t.is_html && <span className="badge badge-neutral">HTML</span>}
                <span className={`badge ${t.is_active ? "badge-sent" : "badge-neutral"}`}>{t.is_active ? "active" : "off"}</span>
              </div>
            </div>
            <div className="muted tpl-subject">{t.subject}</div>
            {/* Bodies can be a single 10k-character line of pasted markup, so the
                preview is always clipped — never allowed to size the card. */}
            {t.is_html
              ? <HtmlPreview html={t.body} height={140} />
              : <div className="tpl-body">{t.body}</div>}
            <div className="row tpl-actions">
              <button className="btn btn-sm" onClick={() => doPreview(t)}>Preview</button>
              <button className="btn btn-sm btn-ghost" onClick={() => setEditing({ ...t })}><Icon.edit /></button>
              <button className="btn btn-sm btn-danger" onClick={() => remove(t)}><Icon.trash /></button>
            </div>
          </div>
        ))}
        {rows.length === 0 && <div className="card empty" style={{ gridColumn: "1 / -1" }}>No templates yet.</div>}
      </div>

      {editing && (
        <Modal
          wide
          title={editing.id ? "Edit template" : "New template"}
          onClose={() => setEditing(null)}
          footer={<>
            <button className="btn" onClick={() => setEditing(null)}>Cancel</button>
            <button className="btn btn-primary" onClick={save} disabled={busy}>{busy ? "Saving…" : "Save"}</button>
          </>}
        >
          <Field label="Template name"><input className="input" value={editing.name} onChange={(e) => setEditing({ ...editing, name: e.target.value })} /></Field>
          <Field label="Subject"><input className="input" value={editing.subject} onChange={(e) => setEditing({ ...editing, subject: e.target.value })} /></Field>

          <div className="row between" style={{ marginBottom: 6 }}>
            <span className="page-sub">Body</span>
            <label className="row" style={{ gap: 8, cursor: "pointer" }}>
              <Switch checked={editing.is_html} onChange={(v) => setEditing({ ...editing, is_html: v })} />
              <span className="page-sub">HTML</span>
            </label>
          </div>
          <textarea
            className={`textarea ${editing.is_html ? "mono" : ""}`}
            style={{ minHeight: editing.is_html ? 280 : 180, width: "100%" }}
            spellCheck={!editing.is_html}
            value={editing.body}
            onChange={(e) => setEditing({ ...editing, body: e.target.value })}
          />
          {htmlHint && (
            <div className="hint-inline">
              That looks like HTML. Turn on the HTML switch or it will be sent as literal text.
            </div>
          )}
          {editing.is_html && (
            <>
              <div className="page-sub" style={{ margin: "14px 0 6px" }}>Live preview</div>
              <HtmlPreview html={editing.body} height={260} />
              <div className="hint-inline">
                Sent as multipart/alternative — a plain-text version is generated automatically
                for clients that refuse HTML. Placeholders work inside markup.
              </div>
            </>
          )}

          <div style={{ marginTop: 16 }}>
            {(showAllTokens ? TOKEN_GROUPS : TOKEN_GROUPS.slice(0, ALWAYS_SHOWN)).map(([label, keys]) => (
              <div key={label}>
                <div className="page-sub" style={{ margin: "10px 0 6px" }}>{label}:</div>
                <div className="row" style={{ flexWrap: "wrap", gap: 6 }}>
                  {keys.map(([k, hint]) => (
                    <span
                      className="chip"
                      key={k}
                      role="button"
                      tabIndex={0}
                      aria-label={`Insert {{${k}}} — ${hint}`}
                      data-tip={hint}
                      onMouseEnter={tipAlign}
                      onFocus={tipAlign}
                      onClick={() => insert(k)}
                      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); insert(k); } }}
                    >{`{{${k}}}`}</span>
                  ))}
                </div>
              </div>
            ))}
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              style={{ marginTop: 10 }}
              onClick={() => setShowAllTokens((v) => !v)}
            >
              {showAllTokens
                ? "Show fewer tags"
                : `More tags — dates, deadlines, random (${TOKEN_GROUPS.slice(ALWAYS_SHOWN).reduce((n, [, k]) => n + k.length, 0)})`}
            </button>
            {placeholders.length > 0 && <>
              <div className="page-sub" style={{ margin: "10px 0 6px" }}>Your placeholders:</div>
              <div className="row" style={{ flexWrap: "wrap", gap: 6 }}>
                {placeholders.map((p) => (
                  <span
                    className="chip"
                    key={p.id}
                    role="button"
                    tabIndex={0}
                    data-tip={p.static_value ? `Your own placeholder. Inserts: ${p.static_value}` : "Your own placeholder. No value set yet — edit it on the Placeholders page."}
                    onMouseEnter={tipAlign}
                    onFocus={tipAlign}
                    onClick={() => insert(p.key)}
                    onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); insert(p.key); } }}
                  >{`{{${p.key}}}`}</span>
                ))}
              </div>
            </>}
          </div>
          {links.length > 0 && (
            <div style={{ marginTop: 12 }}>
              <div className="page-sub" style={{ marginBottom: 6 }}>Insert link:</div>
              <div className="row" style={{ flexWrap: "wrap", gap: 6 }}>
                {links.map((l) => (
                  <span
                    className="chip"
                    key={l.id}
                    role="button"
                    tabIndex={0}
                    data-tip={`Inserts this tracked link: ${l.url}`}
                    onMouseEnter={tipAlign}
                    onFocus={tipAlign}
                    onClick={() => insertText(l.url)}
                    onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); insertText(l.url); } }}
                  >🔗 {l.name}</span>
                ))}
              </div>
            </div>
          )}
          <div className="row" style={{ marginTop: 16 }}>
            <Switch checked={editing.is_active} onChange={(v) => setEditing({ ...editing, is_active: v })} />
            <span className="page-sub">Active</span>
          </div>
        </Modal>
      )}

      {preview && (
        <Modal wide title={`Preview · ${preview.name}`} onClose={() => setPreview(null)}
          footer={<button className="btn btn-primary" onClick={() => setPreview(null)}>Close</button>}>
          <div className="muted" style={{ marginBottom: 4 }}>Subject</div>
          <div className="card card-pad tpl-body" style={{ marginBottom: 14, maxHeight: "none" }}>{preview.subject}</div>
          <div className="muted" style={{ marginBottom: 4 }}>Body</div>
          {preview.is_html
            ? <HtmlPreview html={preview.body} height="min(52vh, 460px)" />
            : <div className="card card-pad tpl-body" style={{ maxHeight: "52vh", overflow: "auto" }}>{preview.body}</div>}
        </Modal>
      )}
    </div>
  );
}
