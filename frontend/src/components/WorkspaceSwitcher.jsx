import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { Icon } from "../icons";

export default function WorkspaceSwitcher({ current }) {
  const [open, setOpen] = useState(false);
  const [workspaces, setWorkspaces] = useState([]);
  const ref = useRef();
  const nav = useNavigate();

  const load = () => api.workspaces.list().then(setWorkspaces);
  useEffect(() => { load(); }, []);

  useEffect(() => {
    const onClick = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  const switchTo = async (ws) => {
    if (ws.is_current) { setOpen(false); return; }
    await api.workspaces.switch(ws.id);
    // Reload so every page re-fetches data for the newly active workspace.
    window.location.reload();
  };

  return (
    <div className="ws-switcher" ref={ref}>
      <button className="btn ws-trigger" onClick={() => { setOpen((o) => !o); load(); }}>
        <span className="ws-avatar">{(current?.name || "?")[0].toUpperCase()}</span>
        <span className="ws-name">{current?.name || "Workspace"}</span>
        <Icon.chevron />
      </button>
      {open && (
        <div className="ws-menu">
          <div className="ws-menu-label">Workspaces</div>
          {workspaces.map((ws) => (
            <button key={ws.id} className={`ws-menu-item ${ws.is_current ? "active" : ""}`} onClick={() => switchTo(ws)}>
              <span className="ws-avatar sm">{ws.name[0].toUpperCase()}</span>
              <span style={{ flex: 1, textAlign: "left", minWidth: 0 }}>
                <div className="ws-item-name">{ws.name}</div>
                <div className="ws-item-meta">{ws.role} · {ws.member_count} member{ws.member_count !== 1 ? "s" : ""}</div>
              </span>
              {ws.is_current && <Icon.check />}
            </button>
          ))}
          <div className="ws-menu-sep" />
          <button className="ws-menu-item" onClick={() => { setOpen(false); nav("/team"); }}>
            <span className="ws-avatar sm ghost"><Icon.team /></span>
            <span style={{ flex: 1, textAlign: "left" }}>Manage team & workspaces</span>
          </button>
        </div>
      )}
    </div>
  );
}
