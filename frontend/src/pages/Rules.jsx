import { useEffect, useState } from "react";
import { api } from "../api";
import { Icon } from "../icons";
import { Field, Loader, Modal, Switch, useToast } from "../components/ui";

const MATCH_TYPES = [
  ["contains", "Subject contains"],
  ["equals", "Subject equals"],
  ["starts_with", "Subject starts with"],
  ["regex", "Subject matches regex"],
];

const BLANK = { name: "", match_type: "contains", match_value: "", case_sensitive: false, template: "", mailboxes: [], attachments: [], is_active: true, priority: 100 };

export default function Rules() {
  const [rows, setRows] = useState(null);
  const [templates, setTemplates] = useState([]);
  const [mailboxes, setMailboxes] = useState([]);
  const [attachments, setAttachments] = useState([]);
  const [editing, setEditing] = useState(null);
  const [tester, setTester] = useState("");
  const [testResult, setTestResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const toast = useToast();

  const load = () => api.rules.list().then(setRows);
  useEffect(() => {
    load();
    api.templates.list().then(setTemplates);
    api.mailboxes.list().then(setMailboxes);
    api.attachments.list().then(setAttachments);
  }, []);

  const save = async () => {
    if (!editing.template) return toast("Pick a reply template", "err");
    setBusy(true);
    try {
      const body = { ...editing, template: Number(editing.template) };
      if (editing.id) await api.rules.update(editing.id, body);
      else await api.rules.create(body);
      toast("Rule saved");
      setEditing(null);
      load();
    } catch (e) { toast(`Save failed: ${JSON.stringify(e.detail)}`, "err"); }
    finally { setBusy(false); }
  };

  const remove = async (row) => {
    if (!confirm(`Delete rule "${row.name}"?`)) return;
    await api.rules.remove(row.id);
    toast("Rule deleted");
    load();
  };

  const runTest = async () => {
    const r = await api.rules.testMatch(tester);
    setTestResult(r);
  };

  if (!rows) return <Loader />;

  return (
    <div className="grid">
      <div className="section-head">
        <span className="page-sub">{rows.length} rule{rows.length !== 1 ? "s" : ""} · first match wins (by priority)</span>
        <button className="btn btn-primary" onClick={() => setEditing({ ...BLANK })}><Icon.plus /> New rule</button>
      </div>

      <div className="card card-pad">
        <div className="row">
          <input className="input" placeholder="Type a subject to test which rule fires…" value={tester} onChange={(e) => setTester(e.target.value)} />
          <button className="btn" onClick={runTest}><Icon.bolt /> Test</button>
        </div>
        {testResult && (
          <div style={{ marginTop: 12 }}>
            {testResult.matched
              ? <span className="badge badge-sent">Matches: {testResult.rule.name} → {testResult.rule.template_name}</span>
              : <span className="badge badge-neutral">No rule matches this subject</span>}
          </div>
        )}
      </div>

      <div className="card">
        <table className="table">
          <thead>
            <tr><th>Priority</th><th>Name</th><th>Condition</th><th>Reply template</th><th>Status</th><th></th></tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td className="mono">{r.priority}</td>
                <td className="subj">{r.name}</td>
                <td className="muted">{r.match_type_display}: <b style={{ color: "var(--text)" }}>{r.match_value}</b></td>
                <td className="muted">{r.template_name}</td>
                <td><span className={`badge ${r.is_active ? "badge-sent" : "badge-neutral"}`}>{r.is_active ? "active" : "off"}</span></td>
                <td>
                  <div className="row" style={{ justifyContent: "flex-end", gap: 6 }}>
                    <button className="btn btn-sm btn-ghost" onClick={() => setEditing({ ...r, template: r.template })}><Icon.edit /></button>
                    <button className="btn btn-sm btn-danger" onClick={() => remove(r)}><Icon.trash /></button>
                  </div>
                </td>
              </tr>
            ))}
            {rows.length === 0 && <tr><td colSpan={6}><div className="empty">No rules yet. Add one to auto-reply based on subjects.</div></td></tr>}
          </tbody>
        </table>
      </div>

      {editing && (
        <Modal title={editing.id ? "Edit rule" : "New rule"} onClose={() => setEditing(null)}
          footer={<>
            <button className="btn" onClick={() => setEditing(null)}>Cancel</button>
            <button className="btn btn-primary" onClick={save} disabled={busy}>{busy ? "Saving…" : "Save"}</button>
          </>}>
          <Field label="Rule name"><input className="input" value={editing.name} onChange={(e) => setEditing({ ...editing, name: e.target.value })} placeholder="Project inquiries" /></Field>
          <div className="field-row">
            <Field label="Match type">
              <select className="input" value={editing.match_type} onChange={(e) => setEditing({ ...editing, match_type: e.target.value })}>
                {MATCH_TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
            </Field>
            <Field label="Priority"><input className="input" type="number" value={editing.priority} onChange={(e) => setEditing({ ...editing, priority: Number(e.target.value) })} /></Field>
          </div>
          <Field label="Subject text / pattern"><input className="input" value={editing.match_value} onChange={(e) => setEditing({ ...editing, match_value: e.target.value })} placeholder="Project Inquiry" /></Field>
          <Field label="Reply with template">
            <select className="input" value={editing.template} onChange={(e) => setEditing({ ...editing, template: e.target.value })}>
              <option value="">— select template —</option>
              {templates.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
            </select>
          </Field>
          <Field label="Limit to mailboxes (none = all)">
            <select className="input" multiple value={editing.mailboxes.map(String)} style={{ minHeight: 90 }}
              onChange={(e) => setEditing({ ...editing, mailboxes: Array.from(e.target.selectedOptions, (o) => Number(o.value)) })}>
              {mailboxes.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
            </select>
          </Field>
          <Field label="Attach files to the reply (optional)">
            {attachments.length === 0
              ? <div className="page-sub">No attachments uploaded yet — add some on the Attachments page.</div>
              : <select className="input" multiple value={(editing.attachments || []).map(String)} style={{ minHeight: 80 }}
                  onChange={(e) => setEditing({ ...editing, attachments: Array.from(e.target.selectedOptions, (o) => Number(o.value)) })}>
                  {attachments.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
                </select>}
          </Field>
          <div className="row" style={{ gap: 24 }}>
            <div className="row"><Switch checked={editing.case_sensitive} onChange={(v) => setEditing({ ...editing, case_sensitive: v })} /><span className="page-sub">Case sensitive</span></div>
            <div className="row"><Switch checked={editing.is_active} onChange={(v) => setEditing({ ...editing, is_active: v })} /><span className="page-sub">Active</span></div>
          </div>
        </Modal>
      )}
    </div>
  );
}
