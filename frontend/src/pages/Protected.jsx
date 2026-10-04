import { useEffect, useState } from "react";
import { api, SERVER_ORIGIN } from "../api";
import { Icon } from "../icons";
import { Field, Loader, Modal, PageIntro, Switch, useToast } from "../components/ui";

const BLANK = {
  name: "",
  kind: "page",
  html: "",
  passcode: "",
  clear_passcode: false,
  expires_at: "",
  max_views: "",
  allowed_referrers: "",
  disable_right_click: false,
  disable_copy: false,
  disable_print: false,
  minify: false,
  wrong_passcode_action: "prompt",
  is_active: true,
};

// Reusable helper: turn a Blob into a browser download.
function saveBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = filename;
  document.body.appendChild(a); a.click(); a.remove();
  URL.revokeObjectURL(url);
}

// Trim a stored ISO timestamp down to what <input type="datetime-local"> expects.
const toLocalInput = (iso) => (iso ? iso.slice(0, 16) : "");

export default function Protected() {
  const [rows, setRows] = useState(null);
  const [editing, setEditing] = useState(null);
  const [file, setFile] = useState(null);
  const [assetsFor, setAssetsFor] = useState(null);
  const [logFor, setLogFor] = useState(null);
  const [exportFor, setExportFor] = useState(null);
  const [batchOpen, setBatchOpen] = useState(false);
  const toast = useToast();

  const load = () => api.protectedContent.list().then(setRows);
  useEffect(() => { load(); }, []);

  const openNew = () => { setFile(null); setEditing({ ...BLANK }); };
  const openEdit = (row) => {
    setFile(null);
    setEditing({
      ...BLANK,
      ...row,
      html: "",                       // never round-trips; left blank keeps existing
      passcode: "",
      clear_passcode: false,
      max_views: row.max_views ?? "",
      expires_at: toLocalInput(row.expires_at),
    });
  };

  const save = async () => {
    const e = editing;
    try {
      // A file document with a freshly chosen file → multipart. Otherwise JSON.
      if (e.kind === "file" && file) {
        const fd = new FormData();
        fd.append("upload", file);
        fd.append("name", e.name || file.name);
        if (e.passcode) fd.append("passcode", e.passcode);
        if (e.clear_passcode) fd.append("clear_passcode", "true");
        if (e.max_views !== "") fd.append("max_views", e.max_views);
        if (e.expires_at) fd.append("expires_at", e.expires_at);
        fd.append("allowed_referrers", e.allowed_referrers || "");
        fd.append("disable_right_click", String(e.disable_right_click));
        fd.append("disable_copy", String(e.disable_copy));
        fd.append("disable_print", String(e.disable_print));
        fd.append("wrong_passcode_action", e.wrong_passcode_action);
        fd.append("is_active", String(e.is_active));
        if (e.id) await api.protectedContent.updateFile(e.id, fd);
        else await api.protectedContent.createFile(fd);
      } else {
        const body = {
          name: e.name,
          allowed_referrers: e.allowed_referrers || "",
          max_views: e.max_views === "" ? null : Number(e.max_views),
          expires_at: e.expires_at || null,
          disable_right_click: e.disable_right_click,
          disable_copy: e.disable_copy,
          disable_print: e.disable_print,
          minify: e.minify,
          wrong_passcode_action: e.wrong_passcode_action,
          is_active: e.is_active,
        };
        if (e.kind === "page" && e.html) body.html = e.html;
        if (e.passcode) body.passcode = e.passcode;
        if (e.clear_passcode) body.clear_passcode = true;
        if (e.id) await api.protectedContent.update(e.id, body);
        else {
          if (e.kind === "file") { toast("Choose a file to upload", "err"); return; }
          if (!e.html) { toast("Add some page content", "err"); return; }
          await api.protectedContent.create(body);
        }
      }
      toast("Saved");
      setEditing(null); setFile(null);
      load();
    } catch (err) { toast(`Save failed: ${JSON.stringify(err.detail)}`, "err"); }
  };

  const remove = async (row) => {
    if (!confirm(`Delete "${row.name}"? This cannot be undone.`)) return;
    await api.protectedContent.remove(row.id);
    toast("Deleted"); load();
  };

  const toggleActive = async (row) => {
    if (row.is_active) await api.protectedContent.revoke(row.id);
    else await api.protectedContent.activate(row.id);
    toast(row.is_active ? "Revoked" : "Re-enabled"); load();
  };

  const copy = (text) => { navigator.clipboard?.writeText(text); toast("Link copied"); };

  if (!rows) return <Loader />;

  return (
    <div className="grid">
      <PageIntro
        id="protected"
        lead="Protect a page or file and share it as a link. The content is encrypted and only handed over after your rules pass — passcode, expiry, view limit and allowed sites — all enforced on the server, with every open recorded."
      />
      <div className="section-head">
        <div className="spacer" />
        {rows.some((r) => r.kind === "page") && (
          <button className="btn" onClick={() => setBatchOpen(true)}><Icon.download /> Batch export</button>
        )}
        <button className="btn btn-primary" onClick={openNew}><Icon.plus /> New protected content</button>
      </div>

      <div className="card">
        <table className="table">
          <thead><tr><th>Name</th><th>Type</th><th>Link</th><th>Views</th><th>Protection</th><th>Status</th><th></th></tr></thead>
          <tbody>
            {rows.map((d) => {
              const url = `${SERVER_ORIGIN}${d.public_path}`;
              const guards = [
                d.requires_passcode && "passcode",
                d.expires_at && "expiry",
                d.max_views != null && "view limit",
                d.allowed_referrers && "referrer",
              ].filter(Boolean);
              return (
                <tr key={d.id}>
                  <td className="subj">{d.name}</td>
                  <td><span className="badge badge-neutral">{d.kind === "file" ? "file" : "page"}</span></td>
                  <td><span className="chip" onClick={() => copy(url)} title="Click to copy">{d.public_path}</span></td>
                  <td className="mono">{d.view_count}{d.max_views != null ? ` / ${d.max_views}` : ""}</td>
                  <td className="muted">{guards.length ? guards.join(", ") : "open"}</td>
                  <td><span className={`badge ${d.is_active ? "badge-sent" : "badge-neutral"}`}>{d.is_active ? "active" : "revoked"}</span></td>
                  <td>
                    <div className="row" style={{ justifyContent: "flex-end", gap: 6 }}>
                      {d.kind === "page" && <button className="btn btn-sm btn-ghost" title="Export protected .html" onClick={() => setExportFor(d)}><Icon.download /></button>}
                      {d.kind === "page" && <button className="btn btn-sm btn-ghost" title="Assets" onClick={() => setAssetsFor(d)}><Icon.attachments /></button>}
                      <button className="btn btn-sm btn-ghost" title="Access log" onClick={() => setLogFor(d)}><Icon.listeners /></button>
                      <button className="btn btn-sm btn-ghost" title={d.is_active ? "Revoke" : "Re-enable"} onClick={() => toggleActive(d)}><Icon.security /></button>
                      <button className="btn btn-sm btn-ghost" title="Edit" onClick={() => openEdit(d)}><Icon.edit /></button>
                      <button className="btn btn-sm btn-danger" title="Delete" onClick={() => remove(d)}><Icon.trash /></button>
                    </div>
                  </td>
                </tr>
              );
            })}
            {rows.length === 0 && <tr><td colSpan={7}><div className="empty">Nothing protected yet.</div></td></tr>}
          </tbody>
        </table>
      </div>

      {editing && (
        <Modal title={editing.id ? "Edit protected content" : "New protected content"} onClose={() => { setEditing(null); setFile(null); }}
          footer={<>
            <button className="btn" onClick={() => { setEditing(null); setFile(null); }}>Cancel</button>
            <button className="btn btn-primary" onClick={save}>Save</button>
          </>}>
          <div className="field-row">
            <Field label="Name"><input className="input" value={editing.name} onChange={(e) => setEditing({ ...editing, name: e.target.value })} placeholder="Q4 price list" /></Field>
            <Field label="Type">
              <select className="input" value={editing.kind} disabled={!!editing.id}
                onChange={(e) => setEditing({ ...editing, kind: e.target.value })}>
                <option value="page">Inline page (HTML)</option>
                <option value="file">File download</option>
              </select>
            </Field>
          </div>

          {editing.kind === "page" ? (
            <Field label={editing.id ? "Page HTML (leave blank to keep current)" : "Page HTML"}>
              <textarea className="input" rows={7} style={{ fontFamily: "monospace" }}
                value={editing.html} onChange={(e) => setEditing({ ...editing, html: e.target.value })}
                placeholder="<h1>Hello</h1>" />
            </Field>
          ) : (
            <Field label={editing.id ? "Replace file (leave empty to keep current)" : "File"}>
              <input className="input" type="file" onChange={(e) => setFile(e.target.files?.[0] || null)} />
            </Field>
          )}

          <div className="field-row">
            <Field label={editing.requires_passcode ? "New passcode (blank keeps current)" : "Passcode (optional)"}>
              <input className="input" type="text" value={editing.passcode}
                onChange={(e) => setEditing({ ...editing, passcode: e.target.value })} placeholder="leave blank for none" />
            </Field>
            <Field label="Max views (blank = unlimited)">
              <input className="input" type="number" min="1" value={editing.max_views}
                onChange={(e) => setEditing({ ...editing, max_views: e.target.value })} />
            </Field>
          </div>

          {(editing.requires_passcode || editing.passcode) && (
            <div className="field-row">
              <Field label="On a wrong passcode (hosted link)">
                <select className="input" value={editing.wrong_passcode_action}
                  onChange={(e) => setEditing({ ...editing, wrong_passcode_action: e.target.value })}>
                  <option value="prompt">Show the prompt again with an error</option>
                  <option value="blank">Display a blank page</option>
                  <option value="back">Send the visitor back</option>
                </select>
              </Field>
              {editing.requires_passcode && (
                <Field label=" ">
                  <label className="row" style={{ gap: 6, paddingTop: 8 }}><Switch checked={editing.clear_passcode} onChange={(v) => setEditing({ ...editing, clear_passcode: v })} /><span className="page-sub">Remove passcode</span></label>
                </Field>
              )}
            </div>
          )}

          <div className="field-row">
            <Field label="Expires at (optional)">
              <input className="input" type="datetime-local" value={editing.expires_at}
                onChange={(e) => setEditing({ ...editing, expires_at: e.target.value })} />
            </Field>
            <Field label="Allowed referrers (comma-separated, optional)">
              <input className="input" value={editing.allowed_referrers}
                onChange={(e) => setEditing({ ...editing, allowed_referrers: e.target.value })} placeholder="mysite.com" />
            </Field>
          </div>

          <Field label="Browser deterrents (cosmetic — easily bypassed, not real protection)">
            <div className="row" style={{ gap: 18, flexWrap: "wrap" }}>
              <label className="row" style={{ gap: 6 }}><Switch checked={editing.disable_right_click} onChange={(v) => setEditing({ ...editing, disable_right_click: v })} /><span className="page-sub">No right-click</span></label>
              <label className="row" style={{ gap: 6 }}><Switch checked={editing.disable_copy} onChange={(v) => setEditing({ ...editing, disable_copy: v })} /><span className="page-sub">No copy/select</span></label>
              <label className="row" style={{ gap: 6 }}><Switch checked={editing.disable_print} onChange={(v) => setEditing({ ...editing, disable_print: v })} /><span className="page-sub">No print</span></label>
              {editing.kind === "page" && <label className="row" style={{ gap: 6 }}><Switch checked={editing.minify} onChange={(v) => setEditing({ ...editing, minify: v })} /><span className="page-sub">Minify source</span></label>}
            </div>
          </Field>

          <div className="row"><Switch checked={editing.is_active} onChange={(v) => setEditing({ ...editing, is_active: v })} /><span className="page-sub">Active</span></div>
        </Modal>
      )}

      {assetsFor && <AssetsModal doc={assetsFor} onClose={() => setAssetsFor(null)} copy={copy} toast={toast} />}
      {logFor && <LogModal doc={logFor} onClose={() => setLogFor(null)} />}
      {exportFor && <ExportModal doc={exportFor} onClose={() => setExportFor(null)} toast={toast} />}
      {batchOpen && <BatchExportModal pages={rows.filter((r) => r.kind === "page")} onClose={() => setBatchOpen(false)} toast={toast} />}
    </div>
  );
}

function BatchExportModal({ pages, onClose, toast }) {
  const [selected, setSelected] = useState(() => new Set(pages.map((p) => p.id)));
  const [passcode, setPasscode] = useState("");
  const [busy, setBusy] = useState(false);

  const toggle = (id) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id); else next.add(id);
    setSelected(next);
  };

  const run = async () => {
    const ids = [...selected];
    if (!ids.length) { toast("Select at least one page", "err"); return; }
    setBusy(true);
    try {
      const { blob, filename } = await api.protectedContent.exportBatch(ids, passcode);
      saveBlob(blob, filename);
      toast("Batch exported");
      onClose();
    } catch (e) { toast(`Batch export failed: ${JSON.stringify(e.detail)}`, "err"); }
    finally { setBusy(false); }
  };

  return (
    <Modal title="Batch export protected .html" onClose={onClose}
      footer={<>
        <button className="btn" onClick={onClose}>Cancel</button>
        <button className="btn btn-primary" onClick={run} disabled={busy}>{busy ? "Building…" : `Download .zip (${selected.size})`}</button>
      </>}>
      <p className="page-sub">Encrypts each selected page into its own standalone HTML file and downloads them as a .zip. One passcode protects every file in the batch.</p>
      <Field label="Passcode for all files (recommended)">
        <input className="input" type="text" value={passcode} onChange={(e) => setPasscode(e.target.value)} placeholder="viewers type this to unlock" />
      </Field>
      <Field label="Pages">
        <div style={{ maxHeight: 220, overflowY: "auto" }}>
          {pages.map((p) => (
            <label key={p.id} className="row" style={{ gap: 8, padding: "4px 0" }}>
              <input type="checkbox" checked={selected.has(p.id)} onChange={() => toggle(p.id)} />
              <span>{p.name}</span>
            </label>
          ))}
        </div>
      </Field>
    </Modal>
  );
}

function AssetsModal({ doc, onClose, copy, toast }) {
  const [assets, setAssets] = useState(null);
  const [file, setFile] = useState(null);

  const fetchAssets = async () => setAssets(await api.protectedContent.assets(doc.id));
  useEffect(() => { fetchAssets(); }, [doc.id]);

  const upload = async () => {
    if (!file) { toast("Choose a file", "err"); return; }
    const fd = new FormData();
    fd.append("upload", file);
    fd.append("name", file.name);
    try {
      await api.protectedContent.uploadAsset(doc.id, fd);
      setFile(null); toast("Asset uploaded"); fetchAssets();
    } catch (e) { toast(`Upload failed: ${JSON.stringify(e.detail)}`, "err"); }
  };

  const del = async (a) => {
    if (!confirm(`Delete asset "${a.name}"?`)) return;
    await api.protectedContent.removeAsset(doc.id, a.id);
    toast("Deleted"); fetchAssets();
  };

  return (
    <Modal title={`Assets — ${doc.name}`} onClose={onClose}
      footer={<button className="btn" onClick={onClose}>Close</button>}>
      <p className="page-sub">Upload images, then paste each gated link into your page HTML as the image source. They load only through the gate, so they can't be hotlinked or reached by a direct URL.</p>
      <div className="row" style={{ gap: 8, margin: "12px 0" }}>
        <input className="input" type="file" onChange={(e) => setFile(e.target.files?.[0] || null)} />
        <button className="btn btn-primary" onClick={upload}><Icon.plus /> Upload</button>
      </div>
      {!assets ? <Loader /> : (
        <table className="table">
          <thead><tr><th>Name</th><th>Type</th><th>Gated link</th><th></th></tr></thead>
          <tbody>
            {assets.map((a) => (
              <tr key={a.id}>
                <td className="subj">{a.name}</td>
                <td className="muted">{a.content_type}</td>
                <td><span className="chip" onClick={() => copy(`${SERVER_ORIGIN}${a.gated_path}`)} title="Click to copy">{a.gated_path}</span></td>
                <td><button className="btn btn-sm btn-danger" onClick={() => del(a)}><Icon.trash /></button></td>
              </tr>
            ))}
            {assets.length === 0 && <tr><td colSpan={4}><div className="empty">No assets yet.</div></td></tr>}
          </tbody>
        </table>
      )}
    </Modal>
  );
}

function ExportModal({ doc, onClose, toast }) {
  const [passcode, setPasscode] = useState("");
  const [busy, setBusy] = useState(false);

  const download = async () => {
    setBusy(true);
    try {
      const { blob, filename } = await api.protectedContent.exportHtml(doc.id, passcode);
      saveBlob(blob, filename);
      toast("Protected file downloaded");
      onClose();
    } catch (e) { toast(`Export failed: ${JSON.stringify(e.detail)}`, "err"); }
    finally { setBusy(false); }
  };

  return (
    <Modal title={`Export protected .html — ${doc.name}`} onClose={onClose}
      footer={<>
        <button className="btn" onClick={onClose}>Cancel</button>
        <button className="btn btn-primary" onClick={download} disabled={busy}>{busy ? "Building…" : "Download .html"}</button>
      </>}>
      <p className="page-sub">Downloads a self-contained HTML file you can host on any server. The page is encrypted with AES-256; the viewer enters the passcode to unlock it. The passcode is never stored in the file.</p>
      <Field label="Export passcode (recommended)">
        <input className="input" type="text" value={passcode} onChange={(e) => setPasscode(e.target.value)} placeholder="viewers type this to unlock" autoFocus />
      </Field>
      <p className="page-sub" style={{ marginTop: 8 }}>
        {passcode
          ? "Strong: without this passcode the content cannot be read, even by someone who downloads the file."
          : "⚠ No passcode: the file opens with no prompt and its source can be recovered — this is obfuscation only. Add a passcode for real protection."}
      </p>
    </Modal>
  );
}

function LogModal({ doc, onClose }) {
  const [logs, setLogs] = useState(null);
  useEffect(() => { api.protectedContent.accessLog(doc.id).then(setLogs); }, [doc.id]);
  return (
    <Modal title={`Access log — ${doc.name}`} onClose={onClose}
      footer={<button className="btn" onClick={onClose}>Close</button>}>
      {!logs ? <Loader /> : (
        <table className="table">
          <thead><tr><th>When</th><th>Outcome</th><th>IP</th><th>Referrer</th></tr></thead>
          <tbody>
            {logs.map((l) => (
              <tr key={l.id}>
                <td className="muted">{new Date(l.created_at).toLocaleString()}</td>
                <td><span className={`badge ${l.outcome === "granted" ? "badge-sent" : "badge-neutral"}`}>{l.outcome.replace(/_/g, " ")}</span></td>
                <td className="mono">{l.ip || "—"}</td>
                <td className="muted" style={{ maxWidth: 200, overflow: "hidden", textOverflow: "ellipsis" }}>{l.referrer || "—"}</td>
              </tr>
            ))}
            {logs.length === 0 && <tr><td colSpan={4}><div className="empty">No access yet.</div></td></tr>}
          </tbody>
        </table>
      )}
    </Modal>
  );
}
