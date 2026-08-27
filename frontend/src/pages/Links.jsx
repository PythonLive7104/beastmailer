import { useEffect, useState } from "react";
import { api, SERVER_ORIGIN } from "../api";
import { Icon } from "../icons";
import { Field, Loader, Modal, PageIntro, Switch, useToast } from "../components/ui";

const BLANK = { name: "", slug: "", url: "", description: "", is_active: true };

export default function Links() {
  const [rows, setRows] = useState(null);
  const [editing, setEditing] = useState(null);
  const toast = useToast();

  const load = () => api.links.list().then(setRows);
  useEffect(() => { load(); }, []);

  const save = async () => {
    try {
      if (editing.id) await api.links.update(editing.id, editing);
      else await api.links.create(editing);
      toast("Link saved");
      setEditing(null);
      load();
    } catch (e) { toast(`Save failed: ${JSON.stringify(e.detail)}`, "err"); }
  };

  const remove = async (row) => {
    if (!confirm(`Delete link "${row.name}"?`)) return;
    await api.links.remove(row.id);
    toast("Deleted");
    load();
  };

  const copy = (text) => { navigator.clipboard?.writeText(text); toast("Copied to clipboard"); };

  if (!rows) return <Loader />;

  return (
    <div className="grid">
      <PageIntro
        id="links"
        lead="Web links you can put into your emails. The app counts how many people click each one, so you can see what people are actually interested in."
      />
      <div className="section-head">
        <div className="spacer" />
        <button className="btn btn-primary" onClick={() => setEditing({ ...BLANK })}><Icon.plus /> New link</button>
      </div>

      <div className="card">
        <table className="table">
          <thead><tr><th>Name</th><th>Destination</th><th>Tracked URL</th><th>Clicks</th><th>Status</th><th></th></tr></thead>
          <tbody>
            {rows.map((l) => {
              const tracked = `${SERVER_ORIGIN}${l.tracking_path}`;
              return (
                <tr key={l.id}>
                  <td className="subj">{l.name}<div className="muted">{l.description}</div></td>
                  <td className="muted" style={{ maxWidth: 220, overflow: "hidden", textOverflow: "ellipsis" }}>{l.url}</td>
                  <td><span className="chip" onClick={() => copy(tracked)} title="Click to copy">{l.tracking_path}</span></td>
                  <td className="mono">{l.clicks}</td>
                  <td><span className={`badge ${l.is_active ? "badge-sent" : "badge-neutral"}`}>{l.is_active ? "active" : "off"}</span></td>
                  <td>
                    <div className="row" style={{ justifyContent: "flex-end", gap: 6 }}>
                      <button className="btn btn-sm btn-ghost" onClick={() => setEditing({ ...l })}><Icon.edit /></button>
                      <button className="btn btn-sm btn-danger" onClick={() => remove(l)}><Icon.trash /></button>
                    </div>
                  </td>
                </tr>
              );
            })}
            {rows.length === 0 && <tr><td colSpan={6}><div className="empty">No links yet.</div></td></tr>}
          </tbody>
        </table>
      </div>

      {editing && (
        <Modal title={editing.id ? "Edit link" : "New link"} onClose={() => setEditing(null)}
          footer={<>
            <button className="btn" onClick={() => setEditing(null)}>Cancel</button>
            <button className="btn btn-primary" onClick={save}>Save</button>
          </>}>
          <div className="field-row">
            <Field label="Name"><input className="input" value={editing.name} onChange={(e) => setEditing({ ...editing, name: e.target.value })} placeholder="Book a call" /></Field>
            <Field label="Slug (for /r/<slug>/)"><input className="input" value={editing.slug} onChange={(e) => setEditing({ ...editing, slug: e.target.value })} placeholder="book" /></Field>
          </div>
          <Field label="Destination URL"><input className="input" value={editing.url} onChange={(e) => setEditing({ ...editing, url: e.target.value })} placeholder="https://…" /></Field>
          <Field label="Description"><input className="input" value={editing.description} onChange={(e) => setEditing({ ...editing, description: e.target.value })} /></Field>
          <div className="row"><Switch checked={editing.is_active} onChange={(v) => setEditing({ ...editing, is_active: v })} /><span className="page-sub">Active</span></div>
        </Modal>
      )}
    </div>
  );
}
