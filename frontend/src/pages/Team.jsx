import { useEffect, useState } from "react";
import { api, SERVER_ORIGIN } from "../api";
import { useAuth } from "../auth";
import { Icon } from "../icons";
import { Field, Loader, Modal, PageIntro, useToast } from "../components/ui";

const ROLE_BADGE = { owner: "badge-sent", admin: "badge-received", member: "badge-neutral" };

export default function Team() {
  const { user, refreshUser } = useAuth();
  const [workspaces, setWorkspaces] = useState(null);
  const [members, setMembers] = useState([]);
  const [myRole, setMyRole] = useState(null);
  const [invite, setInvite] = useState({ identifier: "", role: "member" });
  const [inviteResult, setInviteResult] = useState(null);
  const [newWs, setNewWs] = useState(null);
  const [joinCode, setJoinCode] = useState("");
  const toast = useToast();

  const currentId = user?.workspace?.id;
  const canManage = myRole === "owner" || myRole === "admin";

  const loadMembers = () => currentId && api.workspaces.members(currentId).then((d) => {
    setMembers(d.members);
    setMyRole(d.my_role);
  });
  const loadWorkspaces = () => api.workspaces.list().then(setWorkspaces);

  useEffect(() => { loadWorkspaces(); loadMembers(); }, [currentId]);

  const sendInvite = async () => {
    if (!invite.identifier.trim()) return;
    try {
      const r = await api.workspaces.invite(currentId, invite);
      if (r.added) { toast(`${r.username} added to the workspace`); setInvite({ identifier: "", role: "member" }); loadMembers(); }
      else { setInviteResult(r.invite); toast("Invite code created"); }
    } catch (e) { toast(e.detail?.error || "Invite failed", "err"); }
  };

  const changeRole = async (m, role) => {
    try { await api.workspaces.setRole(currentId, m.id, role); toast("Role updated"); loadMembers(); }
    catch (e) { toast(e.detail?.error || "Failed", "err"); }
  };

  const removeMember = async (m) => {
    const self = m.user === user.id;
    if (!confirm(self ? "Leave this workspace?" : `Remove ${m.username}?`)) return;
    try {
      await api.workspaces.removeMember(currentId, m.id);
      if (self) { await refreshUser(); window.location.reload(); }
      else loadMembers();
    } catch (e) { toast(e.detail?.error || "Failed", "err"); }
  };

  const createWorkspace = async () => {
    try { await api.workspaces.create({ name: newWs }); toast("Workspace created"); window.location.reload(); }
    catch (e) { toast(e.detail?.error || "Failed", "err"); }
  };

  const joinByCode = async () => {
    try { await api.workspaces.acceptInvite(joinCode.trim()); toast("Joined workspace"); window.location.reload(); }
    catch (e) { toast(e.detail?.error || "Invalid code", "err"); }
  };

  const copy = (t) => { navigator.clipboard?.writeText(t); toast("Copied"); };

  if (!workspaces) return <Loader />;

  return (
    <div className="grid" style={{ gap: 22 }}>
      <PageIntro id="team" lead="The people who share this workspace with you. Everyone here sees the same mailboxes, replies and campaigns." />
      {/* Members of the current workspace */}
      <div className="card">
        <div className="card-pad between">
          <div>
            <h3>{user?.workspace?.name} · members</h3>
            <div className="page-sub">You are {myRole ? <b>{myRole}</b> : "a member"} here</div>
          </div>
          <span className="badge badge-neutral">{members.length} member{members.length !== 1 ? "s" : ""}</span>
        </div>
        <table className="table">
          <thead><tr><th>Member</th><th>Email</th><th>Role</th><th></th></tr></thead>
          <tbody>
            {members.map((m) => (
              <tr key={m.id}>
                <td className="row" style={{ gap: 10 }}>
                  <span className="ws-avatar sm">{m.username[0].toUpperCase()}</span>
                  <b>{m.username}{m.user === user.id ? " (you)" : ""}</b>
                </td>
                <td className="muted">{m.email || "—"}</td>
                <td>
                  {canManage && m.role !== "owner" ? (
                    <select className="input" style={{ width: 120, padding: "4px 8px" }} value={m.role} onChange={(e) => changeRole(m, e.target.value)}>
                      <option value="admin">admin</option>
                      <option value="member">member</option>
                    </select>
                  ) : <span className={`badge ${ROLE_BADGE[m.role]}`}>{m.role}</span>}
                </td>
                <td style={{ textAlign: "right" }}>
                  {m.role !== "owner" && (m.user === user.id || canManage) && (
                    <button className="btn btn-sm btn-danger" onClick={() => removeMember(m)}>
                      {m.user === user.id ? "Leave" : "Remove"}
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Invite */}
      {canManage && (
        <div className="card card-pad">
          <h3 style={{ marginBottom: 4 }}>Invite people</h3>
          <div className="page-sub" style={{ marginBottom: 14 }}>
            Existing users join instantly. New emails get a shareable invite code.
          </div>
          <div className="row" style={{ alignItems: "flex-end", gap: 12 }}>
            <div style={{ flex: 1 }}>
              <Field label="Username or email">
                <input className="input" value={invite.identifier} onChange={(e) => setInvite({ ...invite, identifier: e.target.value })} placeholder="jane or jane@company.com" />
              </Field>
            </div>
            <Field label="Role">
              <select className="input" style={{ width: 130 }} value={invite.role} onChange={(e) => setInvite({ ...invite, role: e.target.value })}>
                <option value="member">Member</option>
                <option value="admin">Admin</option>
              </select>
            </Field>
            <button className="btn btn-primary" style={{ marginBottom: 14 }} onClick={sendInvite}><Icon.plus /> Invite</button>
          </div>
          {inviteResult && (
            <div className="card card-pad" style={{ marginTop: 6, background: "var(--surface-2)" }}>
              <div className="page-sub" style={{ marginBottom: 6 }}>Share this invite link — they can redeem it under Team → Join after signing up:</div>
              <div className="row">
                <code className="chip" style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis" }}>{inviteResult.code}</code>
                <button className="btn btn-sm" onClick={() => copy(inviteResult.code)}><Icon.copy /> Copy code</button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Workspaces + join */}
      <div className="grid cols-2">
        <div className="card card-pad">
          <div className="between" style={{ marginBottom: 12 }}>
            <h3>Your workspaces</h3>
            <button className="btn btn-sm" onClick={() => setNewWs("")}><Icon.plus /> New</button>
          </div>
          {workspaces.map((ws) => (
            <div key={ws.id} className="row between" style={{ padding: "8px 0", borderBottom: "1px solid var(--border)" }}>
              <div className="row">
                <span className="ws-avatar sm">{ws.name[0].toUpperCase()}</span>
                <div>
                  <div style={{ fontWeight: 550 }}>{ws.name} {ws.is_current && <span className="badge badge-sent" style={{ marginLeft: 4 }}>current</span>}</div>
                  <div className="ws-item-meta">{ws.role} · {ws.member_count} member{ws.member_count !== 1 ? "s" : ""}</div>
                </div>
              </div>
              {!ws.is_current && <button className="btn btn-sm" onClick={async () => { await api.workspaces.switch(ws.id); window.location.reload(); }}>Switch</button>}
            </div>
          ))}
        </div>

        <div className="card card-pad">
          <h3 style={{ marginBottom: 4 }}>Join a workspace</h3>
          <div className="page-sub" style={{ marginBottom: 14 }}>Got an invite code? Paste it here.</div>
          <Field label="Invite code"><input className="input" value={joinCode} onChange={(e) => setJoinCode(e.target.value)} placeholder="paste code…" /></Field>
          <button className="btn btn-primary" onClick={joinByCode} disabled={!joinCode.trim()}>Join</button>
        </div>
      </div>

      {newWs !== null && (
        <Modal title="Create workspace" onClose={() => setNewWs(null)}
          footer={<>
            <button className="btn" onClick={() => setNewWs(null)}>Cancel</button>
            <button className="btn btn-primary" onClick={createWorkspace} disabled={!newWs.trim()}>Create & switch</button>
          </>}>
          <Field label="Workspace name"><input className="input" autoFocus value={newWs} onChange={(e) => setNewWs(e.target.value)} placeholder="Acme Team" /></Field>
          <div className="page-sub">You'll be the owner and can invite others.</div>
        </Modal>
      )}
    </div>
  );
}
