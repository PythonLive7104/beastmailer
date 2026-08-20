import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { Icon } from "../icons";
import { Loader, StatusBadge, useToast } from "../components/ui";

function useClock() {
  const [now, setNow] = useState(new Date());
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);
  return now;
}

function greeting(h) {
  if (h < 12) return "Good morning";
  if (h < 18) return "Good afternoon";
  return "Good evening";
}

export default function Dashboard() {
  const [data, setData] = useState(null);
  const [running, setRunning] = useState(false);
  const now = useClock();
  const toast = useToast();

  // Same ordering guard as the Listeners feed: "Run now" refreshes while the 30s
  // tick may still be in flight, and the older reply must not repaint stale counts.
  const reqId = useRef(0);
  const load = () => {
    const id = ++reqId.current;
    return api.dashboard()
      .then((d) => { if (id === reqId.current) setData(d); })
      .catch(() => toast("Failed to load dashboard", "err"));
  };
  useEffect(() => {
    load();
    const t = setInterval(load, 30000); // live refresh every 30s
    return () => clearInterval(t);
  }, []);

  const runNow = async () => {
    setRunning(true);
    try {
      const r = await api.runEngine();
      toast(`Engine ran · ${r.ingested} received, ${r.sent} sent`);
      load();
    } catch {
      toast("Engine run failed", "err");
    } finally {
      setRunning(false);
    }
  };

  if (!data) return <Loader label="Loading dashboard…" />;

  const stats = [
    { label: "Mailbox", value: `${data.mailboxes.active} active`, foot: `${data.mailboxes.total} configured`, ok: true },
    { label: "Auto-reply", value: data.auto_reply.enabled ? "Enabled" : "Disabled", foot: `Delay ${data.reply_delay_minutes} min`, ok: data.auto_reply.enabled },
    { label: "Poll interval", value: `${data.poll_interval_seconds}`, foot: "seconds" },
    { label: "Reply delay", value: `${data.reply_delay_minutes}`, foot: "minutes" },
  ];

  return (
    <div className="grid" style={{ gap: 22 }}>
      <section className="hero">
        <h2><Icon.sun style={{ width: 30, height: 30 }} /> {greeting(now.getHours())}</h2>
        <div className="hero-clock">
          <div className="time">{now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}</div>
          <div className="date">{now.toLocaleDateString([], { weekday: "long", year: "numeric", month: "long", day: "numeric" })}</div>
        </div>
      </section>

      <section className="grid cols-4">
        {stats.map((s) => (
          <div className="card stat-card" key={s.label}>
            <div className="stat-label">{s.label}</div>
            <div className={`stat-value ${s.ok ? "ok" : ""}`}>{s.value}</div>
            <div className="stat-foot">{s.foot}</div>
          </div>
        ))}
      </section>

      <section className="grid cols-5">
        {[
          ["Sent", data.counts.sent, "badge-sent"],
          ["Received", data.counts.received, "badge-received"],
          ["Scheduled", data.counts.scheduled, "badge-scheduled"],
          ["Failed", data.counts.failed, "badge-failed"],
          ["Active rules", data.counts.rules, "badge-neutral"],
        ].map(([label, value, cls]) => (
          <div className="card card-pad" key={label} style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <span className={`badge ${cls}`} style={{ alignSelf: "flex-start" }}>{label}</span>
            <div style={{ fontSize: 24, fontWeight: 700 }}>{value}</div>
          </div>
        ))}
      </section>

      <section className="card">
        <div className="card-pad between">
          <div className="row">
            <h3>Recent activity</h3>
            <span className="badge badge-live"><span className="pulse" />LIVE</span>
          </div>
          <div className="row">
            <span className="page-sub">Showing {data.recent_activity.length} of last 50</span>
            <button className="btn btn-primary btn-sm" onClick={runNow} disabled={running}>
              <Icon.play /> {running ? "Running…" : "Run engine"}
            </button>
            <button className="btn btn-sm" onClick={load}><Icon.refresh /> Refresh</button>
          </div>
        </div>
        <div style={{ maxHeight: 420, overflow: "auto" }}>
          <table className="table">
            <thead>
              <tr><th>Time</th><th>Event</th><th>Subject</th><th>From / To</th></tr>
            </thead>
            <tbody>
              {data.recent_activity.map((m) => (
                <tr key={m.id}>
                  <td className="mono">{new Date(m.timestamp).toLocaleString()}</td>
                  <td><StatusBadge status={m.status} /></td>
                  <td>
                    <div className="subj">{m.subject || "—"}</div>
                    <div className="muted">{m.mailbox_name}</div>
                  </td>
                  <td className="muted">{m.direction === "incoming" ? m.from_addr : m.to_addr}</td>
                </tr>
              ))}
              {data.recent_activity.length === 0 && (
                <tr><td colSpan={4}><div className="empty">No activity yet. Connect a mailbox to get started.</div></td></tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
