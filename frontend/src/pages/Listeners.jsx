import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { Icon } from "../icons";
import { Loader, StatusBadge, useToast } from "../components/ui";

export default function Listeners() {
  const [mailboxes, setMailboxes] = useState(null);
  const [messages, setMessages] = useState([]);
  const [filter, setFilter] = useState("");
  const toast = useToast();

  // The 15s refresh and a filter click can be in flight at the same time. Without
  // this counter the slower response wins, so switching to "Sent" could be painted
  // over by an older unfiltered reply — the tab looked filtered but listed everything.
  const reqId = useRef(0);
  const load = () => {
    const id = ++reqId.current;
    const fresh = (setter) => (data) => { if (id === reqId.current) setter(data); };
    api.mailboxes.list().then(fresh(setMailboxes));
    api.messages.list(filter ? { direction: filter } : undefined).then(fresh(setMessages));
  };
  useEffect(() => { load(); const t = setInterval(load, 15000); return () => clearInterval(t); }, [filter]);

  if (!mailboxes) return <Loader />;

  return (
    <div className="grid">
      <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))" }}>
        {mailboxes.map((m) => (
          <div className="card card-pad" key={m.id}>
            <div className="between">
              <div className="row"><span className={`status-dot`} style={{ background: m.is_active ? "var(--success)" : "var(--text-faint)" }} /><b>{m.name}</b></div>
              <button className="btn btn-sm" onClick={async () => { await api.mailboxes.poll(m.id); toast("Polled"); load(); }}><Icon.refresh /></button>
            </div>
            <div className="muted" style={{ marginTop: 6 }}>{m.email_address}</div>
            <div className="page-sub" style={{ marginTop: 8 }}>
              Last poll: {m.last_polled_at ? new Date(m.last_polled_at).toLocaleTimeString() : "never"}
            </div>
            {m.last_error && <div className="badge badge-failed" style={{ marginTop: 8 }}>{m.last_error.slice(0, 40)}</div>}
          </div>
        ))}
      </div>

      <div className="card">
        <div className="card-pad between">
          <div className="row"><h3>Mail feed</h3><span className="badge badge-live"><span className="pulse" />LIVE · 15s</span></div>
          <div className="row">
            {[["", "All"], ["incoming", "Received"], ["outgoing", "Sent"]].map(([v, l]) => (
              <button key={v} className={`btn btn-sm ${filter === v ? "btn-primary" : ""}`} onClick={() => setFilter(v)}>{l}</button>
            ))}
          </div>
        </div>
        <div style={{ maxHeight: 460, overflow: "auto" }}>
          <table className="table">
            <thead><tr><th>Time</th><th>Dir</th><th>Status</th><th>Subject</th><th>Counterparty</th></tr></thead>
            <tbody>
              {messages.map((m) => (
                <tr key={m.id}>
                  <td className="mono">{new Date(m.timestamp).toLocaleString()}</td>
                  <td><span className={`badge ${m.direction === "incoming" ? "badge-received" : "badge-neutral"}`}>{m.direction === "incoming" ? "in" : "out"}</span></td>
                  <td>
                    <StatusBadge status={m.status} />
                    {m.attempt_count > 1 && <span className="muted" style={{ marginLeft: 6, fontSize: 12 }}>· try {m.attempt_count}</span>}
                  </td>
                  <td className="subj">
                    {m.subject}
                    {m.folder && m.folder.toUpperCase() !== "INBOX" && (
                      <span className="badge badge-neutral" style={{ marginLeft: 6 }} title={`Found in ${m.folder}`}>{m.folder}</span>
                    )}
                  </td>
                  <td className="muted">{m.direction === "incoming" ? m.from_addr : m.to_addr}</td>
                </tr>
              ))}
              {messages.length === 0 && <tr><td colSpan={5}><div className="empty">No messages.</div></td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
