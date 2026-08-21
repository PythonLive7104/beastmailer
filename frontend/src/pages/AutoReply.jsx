import { useEffect, useState } from "react";
import { api } from "../api";
import { Icon } from "../icons";
import { Field, Loader, Modal, Switch, useToast } from "../components/ui";

const DYNAMIC_KEYS = [
  ["sender_name", "recipient's name"],
  ["sender_email", "recipient's email"],
  ["original_subject", "subject they sent"],
  ["mailbox_name", "this mailbox's name"],
  ["date", "today's date"],
];
const RANDOM_KEYS = [
  ["ran_letter_10", "10 random letters"],
  ["ran_digit_6", "6 random digits"],
  ["ran_alnum_12", "12 letters + digits"],
  ["ran_hex_8", "8 hex chars"],
];

const BLANK = {
  name: "",
  subject: "Re: {{original_subject}}",
  body: "Hi {{sender_name}},\n\n",
  is_html: false,
  is_active: true,
};

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
            <div className="page-sub" style={{ marginBottom: 6 }}>Dynamic — filled in per message:</div>
            <div className="row" style={{ flexWrap: "wrap", gap: 6 }}>
              {DYNAMIC_KEYS.map(([k, hint]) => <span className="chip" key={k} title={hint} onClick={() => insert(k)}>{`{{${k}}}`}</span>)}
            </div>
            <div className="page-sub" style={{ margin: "10px 0 6px" }}>Random — fresh each send (change the number for length):</div>
            <div className="row" style={{ flexWrap: "wrap", gap: 6 }}>
              {RANDOM_KEYS.map(([k, hint]) => <span className="chip" key={k} title={hint} onClick={() => insert(k)}>{`{{${k}}}`}</span>)}
            </div>
            {placeholders.length > 0 && <>
              <div className="page-sub" style={{ margin: "10px 0 6px" }}>Your placeholders:</div>
              <div className="row" style={{ flexWrap: "wrap", gap: 6 }}>
                {placeholders.map((p) => <span className="chip" key={p.id} onClick={() => insert(p.key)}>{`{{${p.key}}}`}</span>)}
              </div>
            </>}
          </div>
          {links.length > 0 && (
            <div style={{ marginTop: 12 }}>
              <div className="page-sub" style={{ marginBottom: 6 }}>Insert link:</div>
              <div className="row" style={{ flexWrap: "wrap", gap: 6 }}>
                {links.map((l) => <span className="chip" key={l.id} onClick={() => insertText(l.url)} title={l.url}>🔗 {l.name}</span>)}
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
