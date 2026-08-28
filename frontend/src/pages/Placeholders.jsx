import { useEffect, useState } from "react";
import { api } from "../api";
import { Icon } from "../icons";
import { Field, Loader, Modal, PageIntro, Switch, useToast } from "../components/ui";

const BLANK = { key: "", label: "", description: "", static_value: "", is_dynamic: false };

export default function Placeholders() {
  const [rows, setRows] = useState(null);
  const [editing, setEditing] = useState(null);
  const toast = useToast();

  const load = () => api.placeholders.list().then(setRows);
  useEffect(() => { load(); }, []);

  const save = async () => {
    try {
      if (editing.id) await api.placeholders.update(editing.id, editing);
      else await api.placeholders.create(editing);
      toast("Placeholder saved");
      setEditing(null);
      load();
    } catch (e) { toast(`Save failed: ${JSON.stringify(e.detail)}`, "err"); }
  };

  const remove = async (row) => {
    if (!confirm(`Delete {{${row.key}}}?`)) return;
    await api.placeholders.remove(row.id);
    toast("Deleted");
    load();
  };

  if (!rows) return <Loader />;

  return (
    <div className="grid">
      <PageIntro
        id="placeholders"
        lead="Your own reusable snippets of text. Create one here and you can drop it into any reply or campaign by name — useful for anything you type often, like your address, opening hours or phone number. Change it here and it changes in every email that uses it."
      />
      <div className="section-head">
        <div className="spacer" />
        <button className="btn btn-primary" onClick={() => setEditing({ ...BLANK })}><Icon.plus /> New placeholder</button>
      </div>

      <div className="card">
        <table className="table">
          <thead><tr><th>Key</th><th>Label</th><th>Type</th><th>Value / source</th><th></th></tr></thead>
          <tbody>
            {rows.map((p) => (
              <tr key={p.id}>
                <td><span className="chip">{`{{${p.key}}}`}</span></td>
                <td className="subj">{p.label}</td>
                <td><span className={`badge ${p.is_dynamic ? "badge-received" : "badge-neutral"}`}>{p.is_dynamic ? "dynamic" : "static"}</span></td>
                <td className="muted">{p.is_dynamic ? (p.description || "resolved per message") : (p.static_value || "—")}</td>
                <td>
                  <div className="row" style={{ justifyContent: "flex-end", gap: 6 }}>
                    <button className="btn btn-sm btn-ghost" onClick={() => setEditing({ ...p })}><Icon.edit /></button>
                    <button className="btn btn-sm btn-danger" onClick={() => remove(p)}><Icon.trash /></button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {editing && (
        <Modal title={editing.id ? "Edit placeholder" : "New placeholder"} onClose={() => setEditing(null)}
          footer={<>
            <button className="btn" onClick={() => setEditing(null)}>Cancel</button>
            <button className="btn btn-primary" onClick={save}>Save</button>
          </>}>
          <div className="field-row">
            <Field label="Key (letters, numbers, _)"><input className="input" value={editing.key} onChange={(e) => setEditing({ ...editing, key: e.target.value })} placeholder="company" /></Field>
            <Field label="Label"><input className="input" value={editing.label} onChange={(e) => setEditing({ ...editing, label: e.target.value })} placeholder="Company name" /></Field>
          </div>
          <Field label="Description"><input className="input" value={editing.description} onChange={(e) => setEditing({ ...editing, description: e.target.value })} /></Field>
          <div className="row" style={{ marginBottom: 12 }}>
            <Switch checked={editing.is_dynamic} onChange={(v) => setEditing({ ...editing, is_dynamic: v })} />
            <span className="page-sub">Filled in automatically for each email (like the sender's name)</span>
          </div>
          {!editing.is_dynamic && (
            <Field label="Static value"><textarea className="textarea" value={editing.static_value} onChange={(e) => setEditing({ ...editing, static_value: e.target.value })} /></Field>
          )}
        </Modal>
      )}
    </div>
  );
}
