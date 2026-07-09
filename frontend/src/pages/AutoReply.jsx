import { useEffect, useState } from "react";
import { api } from "../api";
import { Icon } from "../icons";
import { Field, Loader, Modal, Switch, useToast } from "../components/ui";

const BLANK = { name: "", subject: "Re: {{original_subject}}", body: "Hi {{sender_name}},\n\n", is_active: true };

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
              <h3>{t.name}</h3>
              <span className={`badge ${t.is_active ? "badge-sent" : "badge-neutral"}`}>{t.is_active ? "active" : "off"}</span>
            </div>
            <div className="muted" style={{ margin: "8px 0" }}>{t.subject}</div>
            <div style={{ whiteSpace: "pre-wrap", color: "var(--text-muted)", fontSize: 13, maxHeight: 92, overflow: "hidden" }}>{t.body}</div>
            <div className="row" style={{ marginTop: 14, justifyContent: "flex-end" }}>
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
          title={editing.id ? "Edit template" : "New template"}
          onClose={() => setEditing(null)}
          footer={<>
            <button className="btn" onClick={() => setEditing(null)}>Cancel</button>
            <button className="btn btn-primary" onClick={save} disabled={busy}>{busy ? "Saving…" : "Save"}</button>
          </>}
        >
          <Field label="Template name"><input className="input" value={editing.name} onChange={(e) => setEditing({ ...editing, name: e.target.value })} /></Field>
          <Field label="Subject"><input className="input" value={editing.subject} onChange={(e) => setEditing({ ...editing, subject: e.target.value })} /></Field>
          <Field label="Body">
            <textarea className="textarea" style={{ minHeight: 150 }} value={editing.body} onChange={(e) => setEditing({ ...editing, body: e.target.value })} />
          </Field>
          <div>
            <div className="page-sub" style={{ marginBottom: 6 }}>Insert placeholder:</div>
            <div className="row" style={{ flexWrap: "wrap", gap: 6 }}>
              {placeholders.map((p) => <span className="chip" key={p.id} onClick={() => insert(p.key)}>{`{{${p.key}}}`}</span>)}
            </div>
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
        <Modal title={`Preview · ${preview.name}`} onClose={() => setPreview(null)}
          footer={<button className="btn btn-primary" onClick={() => setPreview(null)}>Close</button>}>
          <div className="muted" style={{ marginBottom: 4 }}>Subject</div>
          <div className="card card-pad" style={{ marginBottom: 14 }}>{preview.subject}</div>
          <div className="muted" style={{ marginBottom: 4 }}>Body</div>
          <div className="card card-pad" style={{ whiteSpace: "pre-wrap" }}>{preview.body}</div>
        </Modal>
      )}
    </div>
  );
}
