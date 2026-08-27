import { useEffect, useState } from "react";
import { api } from "../api";
import { Icon } from "../icons";
import { Field, Loader, Modal, useToast } from "../components/ui";

const BLANK_CONTACT = { email: "", first_name: "", last_name: "", company: "", status: "subscribed" };
const STATUS_BADGE = {
  subscribed: "badge-sent",
  unsubscribed: "badge-neutral",
  bounced: "badge-failed",
  complained: "badge-failed",
};

const SAMPLE_CSV = `email,first name,last name,company
jane@example.com,Jane,Doe,Example Ltd
sam@acme.io,Sam,Reed,Acme`;

export default function Audience() {
  const [lists, setLists] = useState(null);
  const [contacts, setContacts] = useState(null);
  const [filter, setFilter] = useState({ list: "", status: "", search: "" });
  const [selected, setSelected] = useState([]);
  const [editing, setEditing] = useState(null);
  const [listEditing, setListEditing] = useState(null);
  const [importing, setImporting] = useState(null);
  const [busy, setBusy] = useState(false);
  const toast = useToast();

  const loadLists = () => api.contactLists.list().then(setLists);
  const loadContacts = () => {
    const params = {};
    if (filter.list) params.list = filter.list;
    if (filter.status) params.status = filter.status;
    if (filter.search) params.search = filter.search;
    api.contacts.list(params).then((rows) => { setContacts(rows); setSelected([]); });
  };

  useEffect(() => { loadLists(); }, []);
  // Refetch whenever a filter changes — the server does the filtering so large
  // audiences never have to be held in the browser.
  useEffect(() => { loadContacts(); }, [filter.list, filter.status, filter.search]);

  const saveContact = async () => {
    setBusy(true);
    try {
      if (editing.id) await api.contacts.update(editing.id, editing);
      else await api.contacts.create(editing);
      toast("Contact saved");
      setEditing(null);
      loadContacts();
      loadLists();
    } catch (e) { toast(`Save failed: ${JSON.stringify(e.detail)}`, "err"); }
    finally { setBusy(false); }
  };

  const saveList = async () => {
    setBusy(true);
    try {
      if (listEditing.id) await api.contactLists.update(listEditing.id, listEditing);
      else await api.contactLists.create(listEditing);
      toast("List saved");
      setListEditing(null);
      loadLists();
    } catch (e) { toast(`Save failed: ${JSON.stringify(e.detail)}`, "err"); }
    finally { setBusy(false); }
  };

  const removeList = async (row) => {
    if (!confirm(`Delete list "${row.name}"? The contacts themselves are kept.`)) return;
    await api.contactLists.remove(row.id);
    toast("List deleted");
    loadLists();
  };

  const runImport = async () => {
    setBusy(true);
    try {
      const r = await api.contacts.importCsv({ csv: importing.csv, list: importing.list || null });
      toast(`Imported: ${r.created} new, ${r.updated} updated, ${r.skipped} skipped`);
      setImporting(null);
      loadContacts();
      loadLists();
    } catch (e) { toast(`Import failed: ${e.detail?.detail || JSON.stringify(e.detail)}`, "err"); }
    finally { setBusy(false); }
  };

  const bulk = async (op, extra = {}) => {
    if (!selected.length) return;
    if (op === "delete" && !confirm(`Permanently delete ${selected.length} contact(s)?`)) return;
    await api.contacts.bulk({ ids: selected, op, ...extra });
    toast(`${selected.length} contact(s) updated`);
    loadContacts();
    loadLists();
  };

  const addToList = () => {
    if (!lists?.length) return toast("Create a list first", "err");
    const name = prompt(`Add ${selected.length} contact(s) to which list?\n\n${lists.map((l) => `${l.id} — ${l.name}`).join("\n")}`);
    if (name) bulk("add_to_list", { list: Number(name) });
  };

  const toggle = (id) => setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));
  const allShown = contacts?.length > 0 && selected.length === contacts.length;

  if (!lists || !contacts) return <Loader />;

  return (
    <div className="grid">
      <div className="section-head">
        <span className="page-sub">
          Contacts and the lists campaigns send to. Unsubscribed and bounced addresses stay on
          file so a re-import can never bring them back.
        </span>
        <div className="row" style={{ gap: 8 }}>
          <button className="btn" onClick={() => setImporting({ csv: "", list: "" })}>
            <Icon.plus /> Import CSV
          </button>
          <button className="btn" onClick={() => setListEditing({ name: "", description: "" })}>
            <Icon.plus /> New list
          </button>
          <button className="btn btn-primary" onClick={() => setEditing({ ...BLANK_CONTACT })}>
            <Icon.plus /> New contact
          </button>
        </div>
      </div>

      <div className="card">
        <div className="page-sub" style={{ padding: "14px 16px 0" }}>Lists</div>
        <table className="table">
          <thead><tr><th>List</th><th>Contacts</th><th>Mailable</th><th></th></tr></thead>
          <tbody>
            {lists.map((l) => (
              <tr key={l.id}>
                <td className="subj">{l.name}<div className="muted">{l.description}</div></td>
                <td className="mono">{l.contact_count}</td>
                <td className="mono">{l.mailable_count}</td>
                <td>
                  <div className="row" style={{ justifyContent: "flex-end", gap: 6 }}>
                    <button className="btn btn-sm btn-ghost" onClick={() => setFilter({ ...filter, list: String(l.id) })}>
                      View
                    </button>
                    <button className="btn btn-sm btn-ghost" onClick={() => setListEditing({ ...l })}><Icon.edit /></button>
                    <button className="btn btn-sm btn-danger" onClick={() => removeList(l)}><Icon.trash /></button>
                  </div>
                </td>
              </tr>
            ))}
            {lists.length === 0 && (
              <tr><td colSpan={4}><div className="empty">No lists yet. A campaign sends to one or more lists.</div></td></tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="card">
        <div className="row" style={{ padding: "14px 16px", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
          <input className="input" style={{ maxWidth: 240 }} placeholder="Search name, email, company…"
            value={filter.search} onChange={(e) => setFilter({ ...filter, search: e.target.value })} />
          <select className="input" style={{ maxWidth: 180 }} value={filter.list}
            onChange={(e) => setFilter({ ...filter, list: e.target.value })}>
            <option value="">All lists</option>
            {lists.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
          </select>
          <select className="input" style={{ maxWidth: 170 }} value={filter.status}
            onChange={(e) => setFilter({ ...filter, status: e.target.value })}>
            <option value="">Any status</option>
            <option value="subscribed">Subscribed</option>
            <option value="unsubscribed">Unsubscribed</option>
            <option value="bounced">Bounced</option>
            <option value="complained">Complained</option>
          </select>
          {selected.length > 0 && (
            <div className="row" style={{ gap: 6, marginLeft: "auto" }}>
              <span className="page-sub">{selected.length} selected</span>
              <button className="btn btn-sm" onClick={addToList}>Add to list</button>
              <button className="btn btn-sm" onClick={() => bulk("unsubscribe")}>Unsubscribe</button>
              <button className="btn btn-sm" onClick={() => bulk("resubscribe")}>Resubscribe</button>
              <button className="btn btn-sm btn-danger" onClick={() => bulk("delete")}>Delete</button>
            </div>
          )}
        </div>
        <table className="table">
          <thead>
            <tr>
              <th style={{ width: 34 }}>
                <input type="checkbox" checked={allShown}
                  onChange={(e) => setSelected(e.target.checked ? contacts.map((c) => c.id) : [])} />
              </th>
              <th>Email</th><th>Name</th><th>Company</th><th>Status</th><th></th>
            </tr>
          </thead>
          <tbody>
            {contacts.map((c) => (
              <tr key={c.id}>
                <td><input type="checkbox" checked={selected.includes(c.id)} onChange={() => toggle(c.id)} /></td>
                <td className="mono">{c.email}</td>
                <td>{c.full_name || <span className="muted">—</span>}</td>
                <td className="muted">{c.company || "—"}</td>
                <td>
                  <span className={`badge ${STATUS_BADGE[c.status] || "badge-neutral"}`}>{c.status}</span>
                  {c.status_reason && <div className="muted" style={{ fontSize: 11 }}>{c.status_reason.slice(0, 60)}</div>}
                </td>
                <td>
                  <div className="row" style={{ justifyContent: "flex-end", gap: 6 }}>
                    <button className="btn btn-sm btn-ghost" onClick={() => setEditing({ ...c })}><Icon.edit /></button>
                  </div>
                </td>
              </tr>
            ))}
            {contacts.length === 0 && (
              <tr><td colSpan={6}><div className="empty">No contacts match. Import a CSV to get started.</div></td></tr>
            )}
          </tbody>
        </table>
      </div>

      {importing && (
        <Modal wide title="Import contacts" onClose={() => setImporting(null)}
          footer={<>
            <button className="btn" onClick={() => setImporting(null)}>Cancel</button>
            <button className="btn btn-primary" onClick={runImport} disabled={busy}>
              {busy ? "Importing…" : "Import"}
            </button>
          </>}>
          <Field label="Add to list (optional)">
            <select className="input" value={importing.list}
              onChange={(e) => setImporting({ ...importing, list: e.target.value })}>
              <option value="">Don't add to a list</option>
              {lists.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
            </select>
          </Field>
          <Field label="CSV — needs an 'email' column">
            <textarea className="textarea mono" style={{ minHeight: 220, width: "100%" }}
              placeholder={SAMPLE_CSV} value={importing.csv}
              onChange={(e) => setImporting({ ...importing, csv: e.target.value })} />
          </Field>
          <div className="hint-inline">
            <code>email</code>, <code>first name</code>, <code>last name</code> and <code>company</code> map
            to real fields. Any other column is kept and becomes its own template tag — a
            column called <code>city</code> is usable as <code>{"{{city}}"}</code> in a campaign.
            Re-importing an address updates it rather than duplicating, and never resubscribes
            someone who opted out.
          </div>
        </Modal>
      )}

      {listEditing && (
        <Modal title={listEditing.id ? "Edit list" : "New list"} onClose={() => setListEditing(null)}
          footer={<>
            <button className="btn" onClick={() => setListEditing(null)}>Cancel</button>
            <button className="btn btn-primary" onClick={saveList} disabled={busy}>Save</button>
          </>}>
          <Field label="Name">
            <input className="input" value={listEditing.name} placeholder="Newsletter subscribers"
              onChange={(e) => setListEditing({ ...listEditing, name: e.target.value })} />
          </Field>
          <Field label="Description">
            <input className="input" value={listEditing.description || ""}
              onChange={(e) => setListEditing({ ...listEditing, description: e.target.value })} />
          </Field>
        </Modal>
      )}

      {editing && (
        <Modal title={editing.id ? "Edit contact" : "New contact"} onClose={() => setEditing(null)}
          footer={<>
            <button className="btn" onClick={() => setEditing(null)}>Cancel</button>
            <button className="btn btn-primary" onClick={saveContact} disabled={busy}>Save</button>
          </>}>
          <Field label="Email">
            <input className="input" value={editing.email}
              onChange={(e) => setEditing({ ...editing, email: e.target.value })} />
          </Field>
          <div className="field-row">
            <Field label="First name">
              <input className="input" value={editing.first_name}
                onChange={(e) => setEditing({ ...editing, first_name: e.target.value })} />
            </Field>
            <Field label="Last name">
              <input className="input" value={editing.last_name}
                onChange={(e) => setEditing({ ...editing, last_name: e.target.value })} />
            </Field>
          </div>
          <div className="field-row">
            <Field label="Company">
              <input className="input" value={editing.company}
                onChange={(e) => setEditing({ ...editing, company: e.target.value })} />
            </Field>
            <Field label="Status">
              <select className="input" value={editing.status}
                onChange={(e) => setEditing({ ...editing, status: e.target.value })}>
                <option value="subscribed">Subscribed</option>
                <option value="unsubscribed">Unsubscribed</option>
                <option value="bounced">Bounced</option>
                <option value="complained">Complained</option>
              </select>
            </Field>
          </div>
        </Modal>
      )}
    </div>
  );
}
