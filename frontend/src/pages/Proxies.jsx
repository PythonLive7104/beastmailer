import { useEffect, useState } from "react";
import { api } from "../api";
import { Icon } from "../icons";
import { Field, Loader, Modal, PageIntro, Switch, useToast } from "../components/ui";

const BLANK = { label: "", kind: "socks5", host: "", port: 1080, username: "", password: "", is_active: true };
const KIND_LABEL = { socks5: "SOCKS5", socks4: "SOCKS4", http: "HTTP" };

export default function Proxies() {
  const [rows, setRows] = useState(null);
  const [editing, setEditing] = useState(null);
  const [results, setResults] = useState({}); // id -> test result
  const [testing, setTesting] = useState(null); // id currently under test
  const toast = useToast();

  const load = () => api.proxies.list().then(setRows);
  useEffect(() => { load(); }, []);

  const save = async () => {
    try {
      const body = { ...editing };
      if (editing.id && !body.password) delete body.password; // keep existing secret
      if (editing.id) await api.proxies.update(editing.id, body);
      else await api.proxies.create(body);
      toast("Proxy saved");
      setEditing(null);
      load();
    } catch (e) { toast(`Save failed: ${JSON.stringify(e.detail)}`, "err"); }
  };

  const remove = async (row) => {
    if (!confirm(`Delete proxy "${row.label}"?`)) return;
    await api.proxies.remove(row.id);
    toast("Deleted");
    load();
  };

  const test = async (row) => {
    setTesting(row.id);
    try {
      const r = await api.proxies.test(row.id);
      setResults((m) => ({ ...m, [row.id]: r }));
      r.ok ? toast(`✓ Exit IP ${r.exit_ip} · ${r.latency_ms}ms`) : toast(`Proxy failed: ${r.error}`, "err");
    } catch (e) { toast(`Test failed: ${e.detail?.error || "error"}`, "err"); }
    finally { setTesting(null); }
  };

  if (!rows) return <Loader />;

  return (
    <div className="grid">
      <PageIntro
        id="proxies"
        lead="Optional, and most people do not need it. Sends your email through different internet connections instead of all from one, which can help when sending large volumes."
      />
      <div className="section-head">
        <div className="spacer" />
        <button className="btn btn-primary" onClick={() => setEditing({ ...BLANK })}><Icon.plus /> Add proxy</button>
      </div>

      <div className="card card-pad" style={{ borderColor: "var(--border-strong)" }}>
        <span className="page-sub">
          <b>Heads-up:</b> proxying only changes the IP you present to your SMTP server. With hosted providers
          (Gmail, Outlook…) recipients still see the provider’s IP, and logging in from many random IPs can
          trigger their anti-fraud. Proxies help most with your own relay or provider-side IP rate limits.
        </span>
      </div>

      <div className="card">
        <table className="table">
          <thead>
            <tr><th>Label</th><th>Type</th><th>Endpoint</th><th>Exit IP</th><th>Status</th><th></th></tr>
          </thead>
          <tbody>
            {rows.map((p) => {
              const res = results[p.id];
              return (
                <tr key={p.id}>
                  <td className="subj">{p.label}</td>
                  <td><span className="badge badge-neutral">{KIND_LABEL[p.kind] || p.kind}</span></td>
                  <td className="mono">{p.host}:{p.port}</td>
                  <td className="mono">
                    {res?.ok ? res.exit_ip : (res ? <span style={{ color: "var(--danger)" }}>failed</span> : "—")}
                  </td>
                  <td>
                    <span className={`badge ${p.is_active ? "badge-sent" : "badge-neutral"}`}>{p.is_active ? "active" : "off"}</span>
                    {p.failure_count > 0 && <span className="badge badge-failed" style={{ marginLeft: 6 }}>{p.failure_count} fails</span>}
                  </td>
                  <td>
                    <div className="row" style={{ justifyContent: "flex-end", gap: 6 }}>
                      <button className="btn btn-sm" onClick={() => test(p)} disabled={testing === p.id}>
                        {testing === p.id ? "Testing…" : "Test"}
                      </button>
                      <button className="btn btn-sm btn-ghost" onClick={() => setEditing({ ...p, password: "" })}><Icon.edit /></button>
                      <button className="btn btn-sm btn-danger" onClick={() => remove(p)}><Icon.trash /></button>
                    </div>
                  </td>
                </tr>
              );
            })}
            {rows.length === 0 && <tr><td colSpan={6}><div className="empty">No proxies yet. Add one to rotate sending IPs.</div></td></tr>}
          </tbody>
        </table>
      </div>

      {editing && (
        <Modal title={editing.id ? "Edit proxy" : "New proxy"} onClose={() => setEditing(null)}
          footer={<>
            <button className="btn" onClick={() => setEditing(null)}>Cancel</button>
            <button className="btn btn-primary" onClick={save}>Save</button>
          </>}>
          <div className="field-row">
            <Field label="Label"><input className="input" value={editing.label} onChange={(e) => setEditing({ ...editing, label: e.target.value })} placeholder="Residential US-1" /></Field>
            <Field label="Type">
              <select className="input" value={editing.kind} onChange={(e) => setEditing({ ...editing, kind: e.target.value })}>
                <option value="socks5">SOCKS5</option>
                <option value="socks4">SOCKS4</option>
                <option value="http">HTTP CONNECT</option>
              </select>
            </Field>
          </div>
          <div className="field-row">
            <Field label="Host"><input className="input" value={editing.host} onChange={(e) => setEditing({ ...editing, host: e.target.value })} placeholder="proxy.provider.com" /></Field>
            <Field label="Port"><input className="input" type="number" value={editing.port} onChange={(e) => setEditing({ ...editing, port: Number(e.target.value) })} /></Field>
          </div>
          <div className="field-row">
            <Field label="Username (optional)"><input className="input" value={editing.username} onChange={(e) => setEditing({ ...editing, username: e.target.value })} /></Field>
            <Field label={editing.id ? "Password (leave blank to keep)" : "Password (optional)"}>
              <input className="input" type="password" value={editing.password} onChange={(e) => setEditing({ ...editing, password: e.target.value })} placeholder="••••••••" />
            </Field>
          </div>
          <div className="row"><Switch checked={editing.is_active} onChange={(v) => setEditing({ ...editing, is_active: v })} /><span className="page-sub">Active (included in rotation)</span></div>
        </Modal>
      )}
    </div>
  );
}
