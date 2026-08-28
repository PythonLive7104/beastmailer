import { useEffect, useState } from "react";
import { api } from "../api";
import { Icon } from "../icons";
import { Field, Loader, Modal, PageIntro, useToast } from "../components/ui";

const BLANK_CONTACT = { email: "", first_name: "", last_name: "", company: "", status: "subscribed" };
const STATUS_BADGE = {
  subscribed: "badge-sent",
  unsubscribed: "badge-neutral",
  bounced: "badge-failed",
  complained: "badge-failed",
};

const SAMPLE_PLAIN = `jane@example.com
sam@acme.io
lee@corp.com`;

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

  const readFile = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => setImporting((cur) => ({ ...cur, csv: String(reader.result || "") }));
    reader.onerror = () => toast("Could not read that file", "err");
    reader.readAsText(file);
    e.target.value = "";   // let the same file be picked again after an edit
  };

  const runImport = async () => {
    setBusy(true);
    try {
      const r = await api.contacts.importCsv({
        csv: importing.csv,
        list: importing.list && importing.list !== "new" ? importing.list : null,
        list_name: importing.list === "new" ? importing.list_name : "",
      });
      toast(
        `Imported: ${r.created} new, ${r.updated} updated, ${r.skipped} skipped` +
        (r.list ? ` → ${r.list}` : ""),
      );
      if (r.list_id) setFilter((f) => ({ ...f, list: String(r.list_id) }));
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

  // A picker, not a prompt: the old version asked people to type a numeric list id
  // read out of a text blob, which nobody could reasonably do.
  const [listPicker, setListPicker] = useState(null);
  const addToList = () => {
    if (!lists?.length) return toast("Create a list first", "err");
    setListPicker({ list: String(lists[0].id) });
  };
  const confirmAddToList = async () => {
    await bulk("add_to_list", { list: Number(listPicker.list) });
    setListPicker(null);
  };

  const toggle = (id) => setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));
  const allShown = contacts?.length > 0 && selected.length === contacts.length;

  if (!lists || !contacts) return <Loader />;

  return (
    <div className="grid">
      <PageIntro
        id="audience"
        lead="The people your campaigns go to. Add them one by one, or paste in a spreadsheet to add hundreds at once. Anyone who unsubscribes stays on this page marked as such, so they are never emailed again by mistake."
      steps={[
        "Create a list — for example \u201cNewsletter subscribers\u201d.",
        "Use Import CSV to paste your addresses \u2014 one per line is enough, or upload a file.",
        "A campaign then sends to whichever list you choose.",
      ]}
      />
      <div className="section-head">
        <div className="spacer" />
        <div className="row" style={{ gap: 8 }}>
          {/* Preselect only the list being viewed. Silently defaulting to whatever
              list happens to exist would merge a cold-outreach import into, say, a
              newsletter audience — emailing people who never asked for it. */}
          <button className="btn" onClick={() => setImporting({
            csv: "", list: filter.list && filter.list !== "none" ? filter.list : "", list_name: "",
          })}>
            <Icon.plus /> Import contacts
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
            <option value="none">⚠ Not on any list</option>
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
              <tr><td colSpan={6}><div className="empty">
                {filter.list === "none"
                  ? "Good — every contact belongs to at least one list."
                  : "No contacts here yet. Use Import contacts to add some."}
              </div></td></tr>
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
          <Field label="Which list should these go on?">
            <select className="input" value={importing.list}
              onChange={(e) => setImporting({ ...importing, list: e.target.value })}>
              <option value="">Imported contacts (default)</option>
              {lists.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
              <option value="new">+ Create a new list…</option>
            </select>
          </Field>
          {importing.list === "new" && (
            <Field label="Name for the new list">
              <input className="input" autoFocus placeholder="Promotion"
                value={importing.list_name}
                onChange={(e) => setImporting({ ...importing, list_name: e.target.value })} />
            </Field>
          )}
          {!importing.list && (
            <div className="hint-inline">
              Leave this as it is and your contacts go onto a list called
              <b> Imported contacts</b>, ready to use in a campaign straight away.
            </div>
          )}
          <Field label="Email addresses">
            <textarea className="textarea mono" style={{ minHeight: 220, width: "100%" }}
              placeholder={SAMPLE_PLAIN} value={importing.csv}
              onChange={(e) => setImporting({ ...importing, csv: e.target.value })} />
          </Field>
          <div className="row" style={{ gap: 10, alignItems: "center", flexWrap: "wrap" }}>
            <label className="btn btn-sm" style={{ cursor: "pointer" }}>
              Choose a file…
              <input type="file" accept=".csv,.txt,text/csv,text/plain"
                style={{ display: "none" }} onChange={readFile} />
            </label>
            <span className="page-sub">or paste the addresses above</span>
            {importing.csv && (
              <span className="page-sub" style={{ marginLeft: "auto" }}>
                {(importing.csv.match(/@/g) || []).length} address(es) detected
              </span>
            )}
          </div>
          <div className="hint-inline">
            <b>Just addresses is fine.</b> Paste one per line, or separated by commas — that is
            all you need for email marketing to a list of potential clients. Names copied from a
            mail client, like <code>Jane Doe &lt;jane@example.com&gt;</code>, are understood too.
            Duplicates and anything that is not an address are skipped automatically.
          </div>
          <div className="hint-inline">
            <b>Got a spreadsheet with more detail?</b> Paste it with its header row and name the
            address column <code>email</code>. <code>first name</code>, <code>last name</code> and{" "}
            <code>company</code> are recognised; any other column is kept and becomes its own tag —
            a column called <code>city</code> is then usable as <code>{"{{city}}"}</code> in a campaign.
          </div>
          <div className="hint-inline">
            Re-importing an address updates it rather than duplicating it, and never resubscribes
            someone who opted out. If you only have addresses, avoid <code>{"{{first_name}}"}</code> in
            your campaign — it falls back to “there”.
          </div>
        </Modal>
      )}

      {listPicker && (
        <Modal title={`Add ${selected.length} contact(s) to a list`} onClose={() => setListPicker(null)}
          footer={<>
            <button className="btn" onClick={() => setListPicker(null)}>Cancel</button>
            <button className="btn btn-primary" onClick={confirmAddToList}>Add to list</button>
          </>}>
          <Field label="List">
            <select className="input" value={listPicker.list}
              onChange={(e) => setListPicker({ list: e.target.value })}>
              {lists.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
            </select>
          </Field>
          <div className="hint-inline">
            A contact can be on several lists. Adding them again changes nothing.
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
