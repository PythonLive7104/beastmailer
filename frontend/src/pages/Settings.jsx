import { useState } from "react";
import { useNavigate, useOutletContext } from "react-router-dom";
import { useAuth } from "../auth";
import { useTheme } from "../theme";
import { Icon } from "../icons";
import { Field, Modal, Switch, useToast } from "../components/ui";

export default function Settings() {
  const { user, updateProfile, deleteAccount } = useAuth();
  const { theme, toggle } = useTheme();
  const { openGuide } = useOutletContext() || {};
  const nav = useNavigate();
  const toast = useToast();

  const [form, setForm] = useState({
    username: user?.username || "",
    email: user?.email || "",
    first_name: user?.first_name || "",
    last_name: user?.last_name || "",
  });
  const [savingProfile, setSavingProfile] = useState(false);

  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deletePw, setDeletePw] = useState("");
  const [deleting, setDeleting] = useState(false);

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const dirty =
    form.username !== (user?.username || "") ||
    form.email !== (user?.email || "") ||
    form.first_name !== (user?.first_name || "") ||
    form.last_name !== (user?.last_name || "");

  const saveProfile = async () => {
    setSavingProfile(true);
    try {
      await updateProfile(form);
      toast("Profile saved");
    } catch (e) {
      toast(e.detail?.error || e.detail?.detail || "Could not save profile", "err");
    } finally {
      setSavingProfile(false);
    }
  };

  const doDelete = async () => {
    setDeleting(true);
    try {
      await deleteAccount(deletePw);
      toast("Account deleted");
      nav("/login");
    } catch (e) {
      toast(e.detail?.error || e.detail?.detail || "Could not delete account", "err");
      setDeleting(false);
    }
  };

  return (
    <div className="grid" style={{ maxWidth: 760 }}>
      {/* Personal data */}
      <div className="card card-pad">
        <div className="between" style={{ marginBottom: 14 }}>
          <h3><Icon.user style={{ width: 18, height: 18, verticalAlign: "-3px", marginRight: 8 }} />Personal details</h3>
          <span className="page-sub">Your account information</span>
        </div>
        <div className="grid cols-2">
          <Field label="Username"><input className="input" value={form.username} onChange={set("username")} /></Field>
          <Field label="Email"><input className="input" type="email" value={form.email} onChange={set("email")} placeholder="you@example.com" /></Field>
          <Field label="First name"><input className="input" value={form.first_name} onChange={set("first_name")} placeholder="Optional" /></Field>
          <Field label="Last name"><input className="input" value={form.last_name} onChange={set("last_name")} placeholder="Optional" /></Field>
        </div>
        <button className="btn btn-primary" onClick={saveProfile} disabled={savingProfile || !dirty || !form.username.trim()}>
          {savingProfile ? "Saving…" : "Save changes"}
        </button>
        <div className="page-sub" style={{ marginTop: 10 }}>
          To change your password, head to <a onClick={() => nav("/security")} style={{ cursor: "pointer", color: "var(--accent, #7c5cff)" }}>Security</a>.
        </div>
      </div>

      {/* App preferences */}
      <div className="card card-pad">
        <div className="between" style={{ marginBottom: 14 }}>
          <h3><Icon.settings style={{ width: 18, height: 18, verticalAlign: "-3px", marginRight: 8 }} />Preferences</h3>
          <span className="page-sub">App features</span>
        </div>

        <div className="between" style={{ padding: "10px 0", borderBottom: "1px solid var(--border, #ffffff14)" }}>
          <div>
            <div style={{ fontWeight: 600 }}>Dark theme</div>
            <div className="page-sub">Switch between light and dark appearance.</div>
          </div>
          <Switch checked={theme === "dark"} onChange={toggle} />
        </div>

        <div className="between" style={{ padding: "12px 0" }}>
          <div>
            <div style={{ fontWeight: 600 }}>Setup guide</div>
            <div className="page-sub">Replay the step-by-step walkthrough of the whole app.</div>
          </div>
          <button className="btn btn-ghost" onClick={() => openGuide?.()}>
            <Icon.book style={{ width: 16, height: 16 }} /> Open guide
          </button>
        </div>

        {user?.workspace && (
          <div className="between" style={{ padding: "12px 0", borderTop: "1px solid var(--border, #ffffff14)" }}>
            <div>
              <div style={{ fontWeight: 600 }}>Active workspace</div>
              <div className="page-sub">Switch or manage members from the top bar / Team page.</div>
            </div>
            <span className="badge badge-neutral">{user.workspace.name}</span>
          </div>
        )}
      </div>

      {/* Danger zone */}
      <div className="card card-pad" style={{ borderColor: "var(--danger, #ef4444)" }}>
        <h3 style={{ color: "var(--danger, #ef4444)", marginBottom: 6 }}>
          <Icon.trash style={{ width: 18, height: 18, verticalAlign: "-3px", marginRight: 8 }} />Delete account
        </h3>
        <p className="page-sub" style={{ marginBottom: 14 }}>
          Permanently deletes your account. Workspaces you're the last member of — and all their mailboxes,
          rules, templates and mail — are deleted too. This cannot be undone.
        </p>
        <button className="btn" style={{ background: "var(--danger, #ef4444)", color: "#fff", borderColor: "transparent" }} onClick={() => { setDeletePw(""); setConfirmDelete(true); }}>
          Delete my account
        </button>
      </div>

      {confirmDelete && (
        <Modal
          title="Delete account?"
          onClose={() => !deleting && setConfirmDelete(false)}
          footer={
            <>
              <button className="btn btn-ghost" onClick={() => setConfirmDelete(false)} disabled={deleting}>Cancel</button>
              <button
                className="btn"
                style={{ background: "var(--danger, #ef4444)", color: "#fff", borderColor: "transparent" }}
                onClick={doDelete}
                disabled={deleting || !deletePw}
              >
                {deleting ? "Deleting…" : "Permanently delete"}
              </button>
            </>
          }
        >
          <p className="page-sub" style={{ marginBottom: 14 }}>
            This is permanent. Enter your password to confirm you want to delete <b>{user?.username}</b>.
          </p>
          <Field label="Password">
            <input className="input" type="password" value={deletePw} autoFocus
              onChange={(e) => setDeletePw(e.target.value)} placeholder="Your current password" />
          </Field>
        </Modal>
      )}
    </div>
  );
}
