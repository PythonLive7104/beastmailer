import { useEffect, useState } from "react";
import { api, setToken } from "../api";
import { Field, Loader, useToast } from "../components/ui";

const LEVEL_BADGE = { info: "badge-received", success: "badge-sent", warning: "badge-scheduled", error: "badge-failed" };

export default function Security() {
  const [posture, setPosture] = useState(null);
  const [events, setEvents] = useState([]);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const toast = useToast();

  const load = () => {
    api.security.posture().then(setPosture);
    api.security.events().then(setEvents);
  };
  useEffect(() => { load(); }, []);

  const changePw = async () => {
    setBusy(true);
    try {
      const r = await api.security.changePassword({ current_password: currentPassword, new_password: newPassword });
      if (r.ok) {
        if (r.token) setToken(r.token); // keep this session valid after the rotation
        toast("Password changed");
        setCurrentPassword("");
        setNewPassword("");
        load();
      } else toast(r.error, "err");
    } catch (e) { toast(e.detail?.error || "Failed", "err"); }
    finally { setBusy(false); }
  };

  if (!posture) return <Loader />;

  const cards = [
    { label: "Credential encryption", value: posture.encryption.at_rest ? "Enabled" : "Off", ok: posture.encryption.at_rest, foot: posture.encryption.algorithm },
    { label: "Dedicated key", value: posture.encryption.dedicated_key ? "Configured" : "Dev fallback", ok: posture.encryption.dedicated_key, foot: posture.encryption.dedicated_key ? "MAIL_ENCRYPTION_KEY set" : "Set MAIL_ENCRYPTION_KEY in prod" },
    { label: "Debug mode", value: posture.debug_mode ? "ON" : "OFF", ok: !posture.debug_mode, foot: posture.debug_mode ? "Turn off in production" : "Production-safe" },
    { label: "Recent errors", value: posture.recent_errors, ok: posture.recent_errors === 0, foot: "in the audit log" },
  ];

  return (
    <div className="grid">
      <div className="grid cols-4">
        {cards.map((c) => (
          <div className="card stat-card" key={c.label}>
            <div className="stat-label">{c.label}</div>
            <div className="stat-value" style={{ color: c.ok ? "var(--success)" : "var(--warning)", fontSize: 22 }}>{c.value}</div>
            <div className="stat-foot">{c.foot}</div>
          </div>
        ))}
      </div>

      {posture.mailboxes_missing_password.length > 0 && (
        <div className="card card-pad" style={{ borderColor: "var(--warning)" }}>
          <b>⚠ Mailboxes missing a password:</b>{" "}
          <span className="muted">{posture.mailboxes_missing_password.join(", ")}</span> — polling/sending will fail until set.
        </div>
      )}

      <div className="grid cols-aside">
        <div className="card card-pad">
          <h3 style={{ marginBottom: 14 }}>Change your password</h3>
          <Field label="Current password"><input className="input" type="password" value={currentPassword} onChange={(e) => setCurrentPassword(e.target.value)} placeholder="Your current password" /></Field>
          <Field label="New password"><input className="input" type="password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} placeholder="At least 8 characters" /></Field>
          <button className="btn btn-primary" onClick={changePw} disabled={busy || !currentPassword || !newPassword}>{busy ? "Saving…" : "Update password"}</button>
        </div>

        <div className="card">
          <div className="card-pad between"><h3>Audit log</h3><span className="page-sub">{events.length} recent events</span></div>
          <div style={{ maxHeight: 420, overflow: "auto" }}>
            <table className="table">
              <thead><tr><th>Time</th><th>Level</th><th>Category</th><th>Event</th></tr></thead>
              <tbody>
                {events.map((e) => (
                  <tr key={e.id}>
                    <td className="mono">{new Date(e.created_at).toLocaleString()}</td>
                    <td><span className={`badge ${LEVEL_BADGE[e.level] || "badge-neutral"}`}>{e.level}</span></td>
                    <td className="muted">{e.category}</td>
                    <td className="subj">{e.message}</td>
                  </tr>
                ))}
                {events.length === 0 && <tr><td colSpan={4}><div className="empty">No events logged yet.</div></td></tr>}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
