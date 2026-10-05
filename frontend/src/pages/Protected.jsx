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
  allowed_domains: "",
  block_offline: false,
  break_frames: false,
  disable_right_click: false,
  disable_copy: false,
  disable_print: false,
  block_shortcuts: false,
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
  const [siteOpen, setSiteOpen] = useState(false);
  const [scriptOpen, setScriptOpen] = useState(false);
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
        fd.append("allowed_domains", e.allowed_domains || "");
        fd.append("block_offline", String(e.block_offline));
        fd.append("break_frames", String(e.break_frames));
        fd.append("disable_right_click", String(e.disable_right_click));
        fd.append("disable_copy", String(e.disable_copy));
        fd.append("disable_print", String(e.disable_print));
        fd.append("block_shortcuts", String(e.block_shortcuts));
        fd.append("wrong_passcode_action", e.wrong_passcode_action);
        fd.append("is_active", String(e.is_active));
        if (e.id) await api.protectedContent.updateFile(e.id, fd);
        else await api.protectedContent.createFile(fd);
      } else {
        const body = {
          name: e.name,
          allowed_referrers: e.allowed_referrers || "",
          allowed_domains: e.allowed_domains || "",
          block_offline: e.block_offline,
          break_frames: e.break_frames,
          max_views: e.max_views === "" ? null : Number(e.max_views),
          expires_at: e.expires_at || null,
          disable_right_click: e.disable_right_click,
          disable_copy: e.disable_copy,
          disable_print: e.disable_print,
          block_shortcuts: e.block_shortcuts,
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
        lead="Protect a page or file two ways. A hosted link keeps the content on this server and hands it over only after your rules pass — passcode, expiry, view limit, referrer and domain lock — with every open recorded. An export is a standalone, AES-256-encrypted .html you can host or email: the payload stays encrypted inside the file and only the passcode opens it."
      />
      <div className="section-head">
        <div className="spacer" />
        <button className="btn" onClick={() => setScriptOpen(true)}><Icon.download /> Protect .js/.css</button>
        <button className="btn" onClick={() => setSiteOpen(true)}><Icon.download /> Protect a site (.zip)</button>
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
                      <button className="btn btn-sm btn-ghost" title={d.kind === "file" ? "Open / download" : "Open link"} onClick={() => window.open(url, "_blank")}><Icon.links /></button>
                      <button className="btn btn-sm btn-ghost" title={d.kind === "file" ? "Export encrypted .html wrapper" : "Export protected .html"} onClick={() => setExportFor(d)}><Icon.download /></button>
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
            <>
              <Field label={editing.id ? "Replace file (leave empty to keep current)" : "File"}>
                <input className="input" type="file" onChange={(e) => setFile(e.target.files?.[0] || null)} />
              </Field>
              <p className="page-sub" style={{ marginTop: -4 }}>
                Stored encrypted. The <b>hosted link</b> decrypts and hands over the real file once your
                rules pass — that is what a gate is for, so the download itself is the original.
                To send a file that stays encrypted in transit and at rest, use <b>Export</b>: the
                recipient gets a self-decrypting .html. Upload an <b>.html</b> file and the export
                renders it as the original page — scripts, styles and images all work.
              </p>
            </>
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

          <Field label="Domain lock (comma-separated, optional) — enforced on the hosted link and baked into exports">
            <input className="input" value={editing.allowed_domains}
              onChange={(e) => setEditing({ ...editing, allowed_domains: e.target.value })}
              placeholder="example.com, partner.net — blank = runs anywhere" />
          </Field>

          <Field label="Usage restrictions">
            <div className="row" style={{ gap: 18, flexWrap: "wrap" }}>
              <label className="row" style={{ gap: 6 }}><Switch checked={editing.block_offline} onChange={(v) => setEditing({ ...editing, block_offline: v })} /><span className="page-sub">No offline use (exports refuse to run from a local copy)</span></label>
              <label className="row" style={{ gap: 6 }}><Switch checked={editing.break_frames} onChange={(v) => setEditing({ ...editing, break_frames: v })} /><span className="page-sub">Break out of frames</span></label>
            </div>
          </Field>

          <Field label="Browser deterrents (cosmetic — easily bypassed, not real protection)">
            <div className="row" style={{ gap: 18, flexWrap: "wrap" }}>
              <label className="row" style={{ gap: 6 }}><Switch checked={editing.disable_right_click} onChange={(v) => setEditing({ ...editing, disable_right_click: v })} /><span className="page-sub">No right-click</span></label>
              <label className="row" style={{ gap: 6 }}><Switch checked={editing.disable_copy} onChange={(v) => setEditing({ ...editing, disable_copy: v })} /><span className="page-sub">No copy/select</span></label>
              <label className="row" style={{ gap: 6 }}><Switch checked={editing.disable_print} onChange={(v) => setEditing({ ...editing, disable_print: v })} /><span className="page-sub">No print</span></label>
              <label className="row" style={{ gap: 6 }}><Switch checked={editing.block_shortcuts} onChange={(v) => setEditing({ ...editing, block_shortcuts: v })} /><span className="page-sub">Block F12 / Ctrl+U / Ctrl+S</span></label>
              {editing.kind === "page" && <label className="row" style={{ gap: 6 }}><Switch checked={editing.minify} onChange={(v) => setEditing({ ...editing, minify: v })} /><span className="page-sub">Minify source</span></label>}
            </div>
          </Field>

          <div className="row"><Switch checked={editing.is_active} onChange={(v) => setEditing({ ...editing, is_active: v })} /><span className="page-sub">Active</span></div>
        </Modal>
      )}

      {assetsFor && <AssetsModal doc={assetsFor} onClose={() => setAssetsFor(null)} copy={copy} toast={toast} />}
      {logFor && <LogModal doc={logFor} onClose={() => setLogFor(null)} />}
      {exportFor && <ExportModal doc={exportFor} onClose={() => setExportFor(null)} toast={toast} />}
      {batchOpen && <BatchExportModal pages={rows} onClose={() => setBatchOpen(false)} toast={toast} />}
      {siteOpen && <SiteModal onClose={() => setSiteOpen(false)} toast={toast} />}
      {scriptOpen && <ScriptModal onClose={() => setScriptOpen(false)} toast={toast} />}
    </div>
  );
}

function ScriptModal({ onClose, toast }) {
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const isCss = (file?.name || "").toLowerCase().endsWith(".css");

  const run = async () => {
    if (!file) { toast("Choose a .js or .css file", "err"); return; }
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("upload", file);
      const { blob, filename } = await api.protectedContent.protectScript(fd);
      saveBlob(blob, filename);
      toast("Protected file downloaded");
      onClose();
    } catch (e) { toast(`Failed: ${JSON.stringify(e.detail)}`, "err"); }
    finally { setBusy(false); }
  };

  return (
    <Modal title="Protect a .js / .css file" onClose={onClose}
      footer={<>
        <button className="btn" onClick={onClose}>Cancel</button>
        <button className="btn btn-primary" onClick={run} disabled={busy}>{busy ? "Protecting…" : "Protect & download"}</button>
      </>}>
      <p className="page-sub">Obfuscates a standalone script or stylesheet so its source isn't readable in View Source. This is <b>obfuscation, not encryption</b> — the key ships in the file, so a determined reader can recover it (same as Protware's script protection).</p>
      <Field label="File (.js or .css)"><input className="input" type="file" accept=".js,.css" onChange={(e) => setFile(e.target.files?.[0] || null)} /></Field>
      {isCss && (
        <p className="page-sub" style={{ marginTop: 8 }}>
          A .css becomes a <b>.js loader</b> (stylesheets can't self-decrypt). Reference it with
          {" "}<code>&lt;script src="{file.name}.js"&gt;&lt;/script&gt;</code> instead of the <code>&lt;link&gt;</code> tag.
        </p>
      )}
    </Modal>
  );
}

function SiteModal({ onClose, toast }) {
  const [file, setFile] = useState(null);
  const [passcode, setPasscode] = useState("");
  const [expiresAt, setExpiresAt] = useState("");
  const [minify, setMinify] = useState(false);
  const [domains, setDomains] = useState("");
  const [blockOffline, setBlockOffline] = useState(false);
  const [breakFrames, setBreakFrames] = useState(false);
  const [busy, setBusy] = useState(false);

  const run = async () => {
    if (!file) { toast("Choose a .zip of your site", "err"); return; }
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("upload", file);
      fd.append("passcode", passcode);
      if (expiresAt) fd.append("expires_at", expiresAt);
      fd.append("minify", String(minify));
      fd.append("allowed_domains", domains);
      fd.append("block_offline", String(blockOffline));
      fd.append("break_frames", String(breakFrames));
      const { blob, filename } = await api.protectedContent.protectSite(fd);
      saveBlob(blob, filename);
      toast("Protected site downloaded");
      onClose();
    } catch (e) { toast(`Failed: ${JSON.stringify(e.detail)}`, "err"); }
    finally { setBusy(false); }
  };

  return (
    <Modal title="Protect a whole site (.zip)" onClose={onClose}
      footer={<>
        <button className="btn" onClick={onClose}>Cancel</button>
        <button className="btn btn-primary" onClick={run} disabled={busy}>{busy ? "Protecting…" : "Protect & download .zip"}</button>
      </>}>
      <p className="page-sub">Upload a .zip of a static website. Every .html page is encrypted and made self-contained — its CSS, scripts and images are embedded — while links between pages keep working. You get back a .zip of protected files you can host anywhere. Nothing is stored here.</p>
      <Field label="Site .zip"><input className="input" type="file" accept=".zip" onChange={(e) => setFile(e.target.files?.[0] || null)} /></Field>
      <div className="field-row">
        <Field label="Passcode (recommended)">
          <input className="input" type="text" value={passcode} onChange={(e) => setPasscode(e.target.value)} placeholder="viewers type this to unlock" />
        </Field>
        <Field label="Expires at (optional)">
          <input className="input" type="datetime-local" value={expiresAt} onChange={(e) => setExpiresAt(e.target.value)} />
        </Field>
      </div>
      <Field label="Domain lock (comma-separated, optional)">
        <input className="input" value={domains} onChange={(e) => setDomains(e.target.value)}
          placeholder="example.com — blank = runs anywhere" />
      </Field>
      <div className="row" style={{ gap: 18, flexWrap: "wrap" }}>
        <label className="row" style={{ gap: 6 }}><Switch checked={minify} onChange={setMinify} /><span className="page-sub">Minify source</span></label>
        <label className="row" style={{ gap: 6 }}><Switch checked={blockOffline} onChange={setBlockOffline} /><span className="page-sub">No offline use</span></label>
        <label className="row" style={{ gap: 6 }}><Switch checked={breakFrames} onChange={setBreakFrames} /><span className="page-sub">Break frames</span></label>
      </div>
      <p className="page-sub" style={{ marginTop: 8 }}>
        <b>Works offline</b> — open any page from the .zip straight off disk to check it before
        you host. Once hosted it must be <b>https://</b>; browsers block decryption on plain http://.
      </p>
    </Modal>
  );
}

function BatchExportModal({ pages, onClose, toast }) {
  const [selected, setSelected] = useState(() => new Set(pages.map((p) => p.id)));
  const [passcode, setPasscode] = useState("");
  const [expiresAt, setExpiresAt] = useState("");
  const [busy, setBusy] = useState(false);

  const toggle = (id) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id); else next.add(id);
    setSelected(next);
  };

  const run = async () => {
    const ids = [...selected];
    if (!ids.length) { toast("Select at least one document", "err"); return; }
    setBusy(true);
    try {
      const { blob, filename } = await api.protectedContent.exportBatch(ids, passcode, expiresAt);
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
      <p className="page-sub">Encrypts each selected page or file into its own standalone HTML file and downloads them as a .zip. One passcode protects every file in the batch.</p>
      <div className="field-row">
        <Field label="Passcode for all files (recommended)">
          <input className="input" type="text" value={passcode} onChange={(e) => setPasscode(e.target.value)} placeholder="viewers type this to unlock" />
        </Field>
        <Field label="Expires at (optional)">
          <input className="input" type="datetime-local" value={expiresAt} onChange={(e) => setExpiresAt(e.target.value)} />
        </Field>
      </div>
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
  const [expiresAt, setExpiresAt] = useState("");
  const [busy, setBusy] = useState(false);

  const download = async () => {
    setBusy(true);
    try {
      const { blob, filename } = await api.protectedContent.exportHtml(doc.id, passcode, expiresAt);
      saveBlob(blob, filename);
      toast("Protected file downloaded");
      onClose();
    } catch (e) { toast(`Export failed: ${JSON.stringify(e.detail)}`, "err"); }
    finally { setBusy(false); }
  };

  return (
    <Modal title={`${doc.kind === "file" ? "Export encrypted file" : "Export protected .html"} — ${doc.name}`} onClose={onClose}
      footer={<>
        <button className="btn" onClick={onClose}>Cancel</button>
        <button className="btn btn-primary" onClick={download} disabled={busy}>{busy ? "Building…" : "Download .html"}</button>
      </>}>
      <p className="page-sub">{doc.kind === "file"
        ? "Downloads a self-decrypting .html wrapper around your file. The recipient opens it and types the passcode; an HTML file renders as the original page, a PDF, image or text file is shown in the page, and anything else is saved under its real name. Nothing to install, and the plaintext never leaves this server."
        : "Downloads a self-contained HTML file you can host on any server. Its images are embedded and encrypted inside the file. The page is encrypted with AES-256; the viewer enters the passcode to unlock it, and the passcode is never stored in the file."}</p>
      <div className="field-row">
        <Field label="Export passcode (recommended)">
          <input className="input" type="text" value={passcode} onChange={(e) => setPasscode(e.target.value)} placeholder="viewers type this to unlock" autoFocus />
        </Field>
        <Field label="Expires at (optional)">
          <input className="input" type="datetime-local" value={expiresAt} onChange={(e) => setExpiresAt(e.target.value)} />
        </Field>
      </div>
      <p className="page-sub" style={{ marginTop: 8 }}>
        {passcode
          ? "Strong: without this passcode the content cannot be read, even by someone who downloads the file."
          : "⚠ No passcode: the file opens with no prompt and the key is embedded in it, so the content can be recovered — this is obfuscation only. Add a passcode for real protection."}
      </p>
      <p className="page-sub" style={{ marginTop: 6 }}>
        <b>Works offline.</b> Double-click the downloaded file and it opens in your browser —
        no server, no internet. A local preview server (VS Code Live Preview, Live Server) works too.
        The one place it can&apos;t run is a plain <b>http://</b> site: browsers block decryption there,
        so host over <b>https://</b>.
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
